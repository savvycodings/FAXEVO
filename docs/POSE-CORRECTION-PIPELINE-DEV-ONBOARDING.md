# Pose Correction Pipeline (Landmarks -> Corrected Images)

This doc explains the current implementation used by XEVO to transform pose landmarks into corrected comparison images, and where each part lives in the codebase.

---

## What this feature does

After a technique analysis is completed, the app can generate pose-correction images:

- `originalImage`: extracted frame from the uploaded video.
- `correctedImage`: AI-regenerated version of the same frame, with posture adjustments based on coaching recommendations.

Both are returned as data URIs (`data:image/...;base64,...`) and rendered directly in the UI.

---

## High-level flow

1. User uploads video.
2. Server analyzes video with Modal/MediaPipe and stores:
   - `pose_data` (frame + landmarks),
   - `ai_analysis` (diagnosis, recommendations).
3. Client calls correction endpoint with `analysisId`.
4. Server:
   - validates ownership/session,
   - reads `pose_data` + `ai_analysis`,
   - translates recommendations into landmark deltas (GPT),
   - extracts source frames from video (ffmpeg),
   - generates corrected images (Gemini image model),
   - returns and caches results in analysis metrics.

---

## File map (where everything is)

- Client trigger/UI:
  - `app/src/screens/technique.tsx`
- API routes and orchestration:
  - `server/src/technique/techniqueRouter.ts`
- Frame extraction:
  - `server/src/technique/frameExtractor.ts`
- Recommendation -> landmark deltas + image generation prompting:
  - `server/src/technique/correctionPrompt.ts`
- Auth/session resolution used by routes:
  - `server/src/technique/techniqueRouter.ts` (`resolveUserId()`)

---

## Data contract you should know

### `pose_data` shape (stored in `techniqueAnalysis.metrics`)

Each entry represents one sampled frame:

```json
{
  "frame": 15,
  "landmarks": {
    "LEFT_SHOULDER": { "x": 0.42, "y": 0.57 },
    "RIGHT_SHOULDER": { "x": 0.33, "y": 0.57 }
  }
}
```

Notes:

- Coordinates are normalized 0..1.
- Origin is top-left.
- `x`: left -> right, `y`: top -> bottom.

### Deltas shape (`LandmarkDelta`)

Produced by GPT from recommendations:

```json
{
  "landmark": "LEFT_KNEE",
  "axis": "y",
  "direction": "decrease",
  "magnitude": "moderate",
  "reason": "more bend through contact"
}
```

---

## Step-by-step: backend pipeline

## 1) Analysis endpoint stores landmarks + coaching output

Route: `POST /technique/analyze` in `server/src/technique/techniqueRouter.ts`

- Calls Modal webhook for pose metrics.
- Calls OpenAI for structured AI coaching output.
- Stores combined metrics:
  - raw pose metrics (`pose_data`, frame counts),
  - `ai_analysis` (score/rating/en/es diagnosis + observations + recommendations).

This is the prerequisite for correction-image generation.

---

## 2) Correction endpoint entry point

Route: `POST /technique/correction-images` in `server/src/technique/techniqueRouter.ts`

Request body:

```json
{
  "analysisId": "uuid",
  "frameIndices": [0, 15, 30]
}
```

Behavior:

- Validates auth and analysis ownership.
- Verifies analysis status is `completed`.
- Returns cached `metrics.correction_images` if present.
- Loads:
  - `poseData` from `metrics.pose_data`,
  - `enAnalysis` from `metrics.ai_analysis.en`.

If either is missing, responds with `400`.

---

## 3) Translate recommendations -> concrete landmark deltas

Function: `translateRecommendationsToDeltas(...)` in `server/src/technique/correctionPrompt.ts`

Inputs:

- English recommendations (`enAnalysis.recommendations`)
- English diagnosis (`enAnalysis.diagnosis`)
- A sample frame's landmarks (first requested frame)

What it does:

- Sends a GPT prompt asking for strictly structured biomechanical deltas.
- Parses returned JSON (`parsed` or `parsed.deltas`).
- Returns `LandmarkDelta[]`.

Important implementation detail:

- Deltas are computed once per request and reused across frames.

---

## 4) Extract source frames from uploaded video

Function: `extractFrame(videoPath, frameNumber)` in `server/src/technique/frameExtractor.ts`

How:

- Uses `ffmpeg-static` binary when available (or `FFMPEG_PATH`, else `ffmpeg`).
- Extracts PNG from exact frame using:
  - `select=eq(n\,frameNumber)`
- Falls back to:
  - `select=gte(n\,frameNumber)`
- Returns PNG `Buffer`.

Video path resolution:

- `resolveVideoPath()` converts stored path into absolute path if needed.

---

## 5) Generate corrected image from original frame

Function: `generateCorrectedImage(...)` in `server/src/technique/correctionPrompt.ts`

Inputs:

- Original frame base64
- Frame landmarks
- Computed deltas
- Diagnosis + recommendations

Prompting strategy:

- Instruct Gemini to keep everything identical (person, outfit, court, camera, lighting).
- Apply only body-position corrections from landmark delta instructions.
- No overlays/text labels.

Gemini call:

- Model: `gemini-2.5-flash-image`
- API: `...:generateContent`
- `contents.parts` includes:
  - text prompt,
  - inline image data.
- `generationConfig.responseModalities = ["IMAGE"]`

Output:

- Extracts returned image part (`inlineData`/`inline_data`).
- Returns `data:<mime>;base64,<data>`.

---

## 6) Concurrency and caching

In `server/src/technique/techniqueRouter.ts`:

- `MAX_CONCURRENT_FRAMES = 3`.
- Frames are processed in batches with `Promise.all`.
- Each successful frame returns:
  - `frame`,
  - `originalImage`,
  - `correctedImage`.
- Final array is cached into `techniqueAnalysis.metrics.correction_images`.

If caching fails, request still returns generated corrections (cache failure is non-fatal).

---

## Client-side integration

In `app/src/screens/technique.tsx`:

- Trigger: `generateCorrectionImages()` calls `/technique/correction-images` with `analysisId`.
- Stores response in `correctionImages`.
- UI supports two compare modes:
  - drag/wipe compare,
  - side-by-side compare.
- Thumbnails select active frame and reset split.

Expected client payload per frame:

```json
{
  "frame": 30,
  "originalImage": "data:image/png;base64,...",
  "correctedImage": "data:image/png;base64,..."
}
```

---

## Error and fallback behavior

- Missing/invalid session -> `401`.
- Analysis not found or not owned by user -> `404`.
- Analysis not completed -> `400`.
- Missing `pose_data` or `ai_analysis` -> `400`.
- Missing video file on disk -> `404`.
- Frame-level failures are skipped (other frames continue).
- If no corrected image returned by Gemini for a frame, code falls back to original image.

---

## Environment + dependencies

Required env vars:

- `OPENAI_API_KEY` (deltas + analysis)
- `GEMINI_API_KEY` (image generation)
- `MODAL_WEBHOOK_URL` (pose extraction during analyze)
- `BETTER_AUTH_*` + database vars (auth/session + DB)

Key package:

- `ffmpeg-static` (server-side frame extraction binary)

---

## Practical onboarding tips for new devs

1. Start in `techniqueRouter.ts`, not the UI.
2. Follow this order:
   - `/analyze` (source metrics),
   - `/correction-images` (orchestration),
   - `frameExtractor.ts`,
   - `correctionPrompt.ts`,
   - finally `app/src/screens/technique.tsx`.
3. When debugging quality issues, inspect:
   - generated deltas log,
   - frame hash logs,
   - Gemini no-image fallback logs.
4. If signup/session issues appear during correction generation, first validate `resolveUserId()` path (cookie vs bearer token).
