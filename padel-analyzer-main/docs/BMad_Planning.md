# BMad Phase 2: Planning - Padel Video Analyzer

## Scope: The MVP "Serve Doctor"
To ensure success, we limit MVP to **The Serve**. It is static, self-paced, and easy to record.

## User Stories
1.  **Upload:** As a player, I want to upload a 10s video of my serve so I can get feedback.
2.  **Processing:** As a system, I need to validate the video contains a person before burning GPU credits.
3.  **Feedback:** As a player, I want to see a side-by-side comparison: "My Serve" vs "Pro Serve" with synchronized playback.
4.  **History:** As a player, I want to track my "Serve Score" over time.

## Architecture Specification
*   **Frontend:** Next.js 15 (Vercel).
*   **Backend (AI):** Modal (Python). Handling MediaPipe & OpenAI/Google requests.
*   **Database:** Supabase (PostgreSQL).
*   **Storage:** Supabase Storage (Videos).

## Database Schema (Draft)

### `profiles`
*   `id` (UUID)
*   `skill_level` (Beginner/Intermediate/Pro)
*   `handedness` (Left/Right)

### `analyses`
*   `id` (UUID)
*   `user_id` (FK)
*   `video_url` (Storage Path)
*   `shot_type` (Serve, Forehand, Backhand) - *Default: Serve*
*   `score` (0-100)
*   `feedback_summary` (Text)
*   `processing_status` (Pending, Processing, Completed, Failed)
*   `metadata` (JSONB) - Stores frame-by-frame landmarks.

## API Interface (Modal)

### `POST /analyze_serve`
**Input:**
```json
{
  "video_url": "supabase://...",
  "user_id": "123"
}
```
**Output:**
```json
{
  "job_id": "abc-123",
  "status": "queued"
}
```

### `GET /job_status/{job_id}`
Returns analysis result or current state.

## Implementation Roadmap (Sprints)
1.  **Week 1:** Infra Setup (Next.js + Supabase Auth/Storage).
2.  **Week 2:** Modal Pipeline (MediaPipe Skeleton extraction).
3.  **Week 3:** "Rule Engine" (Defining the math for a good serve).
4.  **Week 4:** UI/UX (Video player with overlays).
