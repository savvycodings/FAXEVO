# Technique Page: Stack & Padel Model Integration

This document describes the **xevo** app stack and how we integrate the **Padel Analyzer** model (from `padel-analyzer-main`) into the new Technique screen (`app/src/screens/technique.tsx`).

---

## 1. Our Stack (xevo)

### App (Expo / React Native)

| Tech | Purpose |
|------|---------|
| **Expo 54** | React Native framework, managed workflow |
| **React 19** | UI library |
| **React Navigation** | Bottom tabs (Chat, Technique, Images, Settings) |
| **NativeWind** | Tailwind-style styling for RN |
| **expo-image-picker** | Pick video from gallery |
| **expo-document-picker** | Pick video from filesystem |
| **expo-av** | Video playback |
| **react-native-svg** | Gradients, icons, UI elements |
| **Better Auth** | Authentication (session, user) |

### Server (Express / Node)

| Tech | Purpose |
|------|---------|
| **Express** | HTTP API |
| **Drizzle ORM** | PostgreSQL queries |
| **Neon** | PostgreSQL database (hosted) |
| **Cloudinary** | Video storage (technique uploads) |
| **Multer** | Multipart file uploads |
| **Better Auth** | Session validation |

### Database (Neon + Drizzle)

| Table | Purpose |
|-------|---------|
| `user`, `session`, `account`, `verification` | Better Auth |
| `technique_video` | Video metadata (Cloudinary refs) |

**`technique_video` schema:**
- `id`, `userId`, `cloudinaryPublicId`, `cloudinaryUrl`, `secureUrl`, `bytes`, `format`, `createdAt`

---

## 2. Padel Analyzer Stack (Reference from Other Devs)

### Web App (Next.js)

| Tech | Purpose |
|------|---------|
| **Next.js 15** | App Router, API routes |
| **Supabase** | Storage (videos bucket) + PostgreSQL (`analyses` table) |
| **Framer Motion** | Animations |
| **Tailwind** | Styling |

### Backend (Modal)

| Tech | Purpose |
|------|---------|
| **Modal** | Serverless Python, GPU |
| **MediaPipe** | Pose detection (33 landmarks per frame) |
| **OpenCV** | Frame extraction (every 15th frame) |
| **Anthropic Claude** | Technique analysis from pose data |

### Data Flow (Web)

```
1. User uploads video → Supabase Storage
2. Create record in analyses (status: 'uploading')
3. POST /api/analyze → Modal webhook
4. Modal: download video → MediaPipe poses → Claude analysis → update Supabase
5. Frontend polls analyses → /analysis/[id] shows results
```

---

## 3. What We Bring Into technique.tsx

### From Our App

| Item | Location | Use |
|------|----------|-----|
| Video pick | `technique.tsx` | `ImagePicker`, `DocumentPicker` |
| Upload | `technique.tsx` → `POST /technique/upload` | Multer + Cloudinary |
| Auth | `techniqueRouter.ts` | `auth.api.getSession()` |
| DB | `techniqueVideo` | Store video metadata |

### From Padel Analyzer (Web)

| Item | Source | Adaptation |
|------|--------|------------|
| Upload flow | `VideoUpload.tsx` | Replace Supabase with our `/technique/upload` |
| Analyze API | `app/api/analyze/route.ts` | New server route `/technique/analyze` |
| Results UI | `app/analysis/[id]/page.tsx` | New Step 3 in technique.tsx or separate screen |
| Modal model | `backend/modal_app.py` | Call Modal webhook with `video_url` + `analysis_id` |

---

## 4. Integration Architecture

### Current Flow (technique.tsx)

```
Step 1: Pick video → POST /technique/upload
        → Cloudinary stores video
        → technique_video row in Neon
        → Returns { id, url, publicId }

Step 2: Select impact frames (max 20s) — UI in progress

Step 3: Results — placeholder only
```

### Target Flow (With Padel Model)

```
Step 1: Pick video → POST /technique/upload (unchanged)
        → Cloudinary URL available

Step 2: User selects segment(s) or confirms clip
        → We need a public video URL for Modal to download

Step 3: POST /technique/analyze
        → Create analysis record (new table or extend technique_video)
        → Call Modal webhook: { video_url, analysis_id, supabase_url, supabase_key, anthropic_api_key }
        → Modal runs MediaPipe + Claude
        → Modal updates our DB (or we poll Modal and then update)

Step 4: Show results (rating, score, diagnosis, observations, recommendations)
```

---

## 5. Key Differences: Web vs Our App

| Aspect | Web (Padel Analyzer) | Our App (xevo) |
|--------|----------------------|----------------|
| Storage | Supabase Storage | Cloudinary |
| DB | Supabase PostgreSQL (`analyses`) | Neon PostgreSQL (`technique_video`) |
| Auth | Optional | Better Auth (required for upload) |
| Frontend | Next.js, browser | Expo, React Native |
| API | Next.js API route | Express route |

---

## 6. What We Need to Implement

### Server

1. **`/technique/analyze`** (new route)
   - Input: `video_url`, `analysis_id` (or derive from technique_video)
   - Call Modal webhook (same contract as `padel-analyzer-main/app/api/analyze/route.ts`)
   - Env: `MODAL_WEBHOOK_URL`, `ANTHROPIC_API_KEY`
   - Optional: Supabase URL/key if Modal writes to Supabase; or we add a new `technique_analysis` table in Neon and have Modal call our webhook to update it

2. **Analysis storage**
   - Option A: New table `technique_analysis` in Neon (id, techniqueVideoId, status, metrics, feedback_text, etc.) — Modal would need a way to update it (e.g. our webhook)
   - Option B: Use Supabase for analyses only (like web) — requires Supabase project + `analyses` table
   - Option C: Modal returns results in webhook response; we store in Neon and poll from client

### App (technique.tsx)

1. **Step 2**
   - Frame selection UI (align with “impact of the ball” instructions)
   - Max 20s clip constraint
   - Produce final `video_url` (Cloudinary URL is public)

2. **Step 3**
   - Call `POST /technique/analyze` with `video_url` and `analysis_id`
   - Poll for status (`uploading` → `processing` → `completed` / `failed`)
   - Render: rating, score, diagnosis, observations, recommendations (bilingual if desired)

### Environment

| Variable | Purpose |
|----------|---------|
| `MODAL_WEBHOOK_URL` | Modal `analyze_video` endpoint URL |
| `ANTHROPIC_API_KEY` | Claude analysis (passed to Modal) |
| `CLOUDINARY_*` | Already used for uploads |

---

## 7. Padel Model Contract (modal_app.py)

**Request body:**
```json
{
  "video_url": "https://...",
  "analysis_id": "uuid",
  "supabase_url": "...",
  "supabase_key": "...",
  "anthropic_api_key": "..."
}
```

**Behavior:**
1. Download video from `video_url`
2. Extract poses with MediaPipe (every 15th frame)
3. Send pose summary to Claude
4. Update Supabase `analyses` row: `status`, `metrics`, `feedback_text`

**Metrics structure:**
```json
{
  "total_frames": 300,
  "analyzed_frames": 20,
  "pose_data": [...],
  "ai_analysis": {
    "score": 7,
    "rating": "good",
    "en": { "diagnosis": "...", "observations": [...], "recommendations": [...] },
    "es": { "diagnosis": "...", "observations": [...], "recommendations": [...] }
  }
}
```

---

## 8. File Reference Map

| Purpose | Web (padel-analyzer-main) | Our App (xevo) |
|---------|---------------------------|-----------------|
| Upload UI | `VideoUpload.tsx` | `app/src/screens/technique.tsx` |
| Upload API | Supabase Storage | `server/src/technique/techniqueRouter.ts` |
| Analyze API | `app/api/analyze/route.ts` | To add: `server/src/technique/analyzeRouter.ts` or similar |
| Results UI | `app/analysis/[id]/page.tsx` | Step 3 in `technique.tsx` (or new screen) |
| Model | `backend/modal_app.py` | External (Modal deployment) |
| Docs | `docs/architecture.md`, `docs/analysis.md` | This file |

---

## 9. server/src/files (Current State)

- `upload-file.ts`: Stub for OpenAI file upload (assistant chat); **not mounted**
- `fileRouter.ts`: Defines `/upload-file`; **not mounted** in `server/src/index.ts`

**Technique uploads** use `server/src/technique/techniqueRouter.ts` (`POST /technique/upload`), not `server/src/files`. The `files` module is for a different use case (OpenAI assistants).

---

## 10. Next Steps

1. Decide storage for analysis results: Neon `technique_analysis` vs Supabase `analyses`
2. Add `POST /technique/analyze` route that calls Modal webhook
3. Extend or add DB schema for analysis status and metrics
4. Wire Step 2 in technique.tsx (frame selection, 20s max)
5. Wire Step 3: call analyze, poll status, render AI results (rating, score, diagnosis, observations, recommendations)
