# Architecture Overview

Padel Analyzer uses a modern serverless architecture with three main components:

## System Diagram

```
┌────────────────────────────────────────────────────────────────────────┐
│                              USER                                       │
│                         (Browser/Mobile)                                │
└────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                         VERCEL (Frontend)                               │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                     │
│  │  Next.js    │  │   Upload    │  │  Analysis   │                     │
│  │   App       │  │   Page      │  │   Results   │                     │
│  └─────────────┘  └─────────────┘  └─────────────┘                     │
│                          │                                              │
│                    /api/analyze                                         │
│                    (API Route)                                          │
└────────────────────────────────────────────────────────────────────────┘
                                    │
                 ┌──────────────────┴──────────────────┐
                 ▼                                     ▼
┌────────────────────────────┐       ┌────────────────────────────────────┐
│       MODAL (Backend)       │       │          SUPABASE                  │
│  ┌──────────────────────┐  │       │  ┌────────────┐  ┌─────────────┐  │
│  │   analyze_video()    │  │       │  │  Storage   │  │  Database   │  │
│  │                      │  │       │  │  (Videos)  │  │  (analyses) │  │
│  │  • Download video    │  │◄─────▶│  └────────────┘  └─────────────┘  │
│  │  • MediaPipe poses   │  │       │                                    │
│  │  • Claude analysis   │  │       │  Row Level Security (RLS)         │
│  │  • Save results      │  │       │  • Videos: public read/write      │
│  └──────────────────────┘  │       │  • Analyses: public read/write    │
└────────────────────────────┘       └────────────────────────────────────┘
                 │
                 ▼
┌────────────────────────────┐
│     ANTHROPIC (Claude)     │
│  ┌──────────────────────┐  │
│  │  Technique Analysis  │  │
│  │  • Rating            │  │
│  │  • Observations      │  │
│  │  • Recommendations   │  │
│  └──────────────────────┘  │
└────────────────────────────┘
```

---

## Components

### Vercel (Frontend)
**Technology:** Next.js 15 with App Router

| File | Purpose |
|------|---------|
| `app/page.tsx` | Home page with video upload UI |
| `app/analysis/[id]/page.tsx` | Results page showing AI analysis |
| `app/api/analyze/route.ts` | API route that triggers Modal |
| `lib/supabase.ts` | Supabase client configuration |

**Responsibilities:**
- Serve the web application
- Handle video uploads to Supabase Storage
- Create analysis records in the database
- Trigger the Modal backend for processing
- Display real-time status updates and results

---

### Supabase (Storage + Database)
**Technology:** PostgreSQL + S3-compatible storage

#### Storage Bucket: `videos`
- Stores uploaded video files
- Public access for reading (videos are viewed in browser)

#### Database Table: `analyses`
| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID | Primary key |
| `user_id` | UUID | Owner (nullable, reserved for auth) |
| `video_url` | TEXT | Public URL to video in storage |
| `thumbnail_url` | TEXT | Video thumbnail URL (optional) |
| `status` | TEXT | `uploading`, `processing`, `completed`, `failed` |
| `metrics` | JSONB | Pose data + AI analysis results (bilingual) |
| `feedback_text` | TEXT | Plaintext markdown summary (optional) |
| `created_at` | TIMESTAMPTZ | Record creation time |
| `updated_at` | TIMESTAMPTZ | Last update time |

**Row Level Security (RLS):**
Currently configured with permissive policies for development. In production, you should restrict access to authenticated users only.

---

### Modal (Backend Processing)
**Technology:** Python serverless functions with GPU support

**File:** `backend/modal_app.py`

**Image Configuration:**
- Base: Debian Slim with GLIBC 2.17+
- Dependencies: `mediapipe`, `opencv-python-headless`, `numpy`, `anthropic`, `supabase`
- Pre-downloaded: MediaPipe Pose Landmarker model

**Function:** `analyze_video()`
1. Receives request with `video_url`, `analysis_id`, API keys
2. Downloads video from Supabase Storage
3. Processes frames with MediaPipe (every 15th frame)
4. Sends pose data to Claude for technique analysis
5. Updates database with results

---

### Anthropic Claude (AI Analysis)
**Model:** claude-sonnet-4-20250514 (Claude Sonnet 4)

**Input:** Structured pose landmark data (shoulders, elbows, wrists, hips, knees, ankles)

**Output:**
```json
{
  "score": 7,
  "rating": "good",
  "en": {
    "diagnosis": "Solid foundation with room for improvement in follow-through",
    "observations": [
      "Good knee bend for power generation",
      "Shoulders slightly uneven during swing"
    ],
    "recommendations": [
      "Practice mirror drills for shoulder alignment",
      "Focus on completing the follow-through"
    ]
  },
  "es": {
    "diagnosis": "Buena base con margen de mejora en el seguimiento del golpe",
    "observations": [
      "Buena flexión de rodillas para generación de potencia",
      "Hombros ligeramente desnivelados durante el swing"
    ],
    "recommendations": [
      "Practicar frente al espejo para alinear los hombros",
      "Completar el seguimiento del golpe"
    ]
  }
}
```

---

## Data Flow

```
1. User uploads video
   └─▶ Video saved to Supabase Storage
   └─▶ Analysis record created (status: 'uploading')

2. Frontend calls /api/analyze
   └─▶ API route sends request to Modal webhook

3. Modal downloads video from Supabase
   └─▶ Updates status to 'processing'
   └─▶ Extracts pose landmarks with MediaPipe

4. Modal sends poses to Claude
   └─▶ Claude returns technique analysis

5. Modal saves results to Supabase
   └─▶ Updates status to 'completed'
   └─▶ Stores AI analysis in metrics.ai_analysis

6. Frontend polls for updates
   └─▶ Displays results when completed
```

---

## Environment Variables

### Vercel
| Variable | Source |
|----------|--------|
| `NEXT_PUBLIC_SUPABASE_URL` | Supabase Dashboard → Settings → API |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Supabase Dashboard → Settings → API |
| `MODAL_WEBHOOK_URL` | Modal deployment output |
| `ANTHROPIC_API_KEY` | Anthropic Console |

### Modal
Environment variables are passed in the request body from the frontend, so no Modal secrets are needed.

---

## Security Considerations

1. **API Keys:** Never expose `ANTHROPIC_API_KEY` in frontend code. It's passed server-side through the API route.
2. **RLS Policies:** The current setup uses permissive policies. For production, implement proper user authentication.
3. **Video Access:** Consider making video URLs time-limited with signed URLs for sensitive content.
