# AI Image Generation End-to-End Flow

This document explains exactly how image generation works in this app, end to end.

It covers two flows:
- Flow A: generic image generation screen (`Images` tab).
- Flow B: technique results pose-correction generation (video frame -> corrected frame).

---

## Where This Is Implemented

### Client
- `app/src/screens/images.tsx`
- `app/src/screens/technique.tsx`

### Server
- `server/src/images/imagesRouter.ts`
- `server/src/images/gemini.ts`
- `server/src/technique/techniqueRouter.ts`
- `server/src/technique/frameExtractor.ts`
- `server/src/technique/correctionPrompt.ts`

---

## Flow A: Generic Image Generation (`/images/gemini`)

### 1) User action
User opens `Images` screen, types a prompt (optionally selects an image), taps Create.

### 2) Client request
`images.tsx` sends one of:

1. JSON request (text-only):
```json
POST /images/gemini
Content-Type: application/json

{
  "prompt": "Create a futuristic padel court at sunset",
  "model": "nanoBanana"
}
```

2. Multipart request (text + image edit):
```http
POST /images/gemini
Content-Type: multipart/form-data

file: <image binary>
prompt: "Keep same person, make racket neon blue"
model: "nanoBananaPro"
```

### 3) Server model mapping
`server/src/images/gemini.ts` maps:
- `nanoBanana` -> `gemini-2.5-flash-image`
- `nanoBananaPro` -> `gemini-3-pro-image-preview`

### 4) Gemini API call
Server calls:
`https://generativelanguage.googleapis.com/v1beta/models/<model>:generateContent`

Request body:
```json
{
  "contents": [
    {
      "parts": [
        { "text": "<prompt>" },
        { "inline_data": { "mime_type": "image/jpeg", "data": "<base64>" } }
      ]
    }
  ],
  "generationConfig": {
    "responseModalities": ["TEXT", "IMAGE"]
  }
}
```

### 5) Server response back to app
Server extracts image from `candidates[0].content.parts[].inlineData.data`, returns:
```json
{
  "image": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAA..."
}
```

### 6) Client render
`images.tsx` stores that `data:` URI and renders:
```tsx
<Image source={{ uri: v.image }} />
```

---

## Flow B: Technique Pose-Correction Images (`/technique/correction-images`)

This is the new flow that turns pose analysis output into corrected visuals.

## High-level pipeline

1. Upload video.
2. Analyze video (MediaPipe + GPT coaching analysis).
3. Generate correction images from analyzed frames.

### Step 1: Upload
Client (`technique.tsx`) calls:
```http
POST /api/auth/technique/upload
Content-Type: multipart/form-data
video: <mp4/mov>
```

Server stores file to disk (example):
`server/uploads/technique/<videoId>.mp4`

### Step 2: Analyze
Client calls:
```json
POST /api/auth/technique/analyze
{
  "techniqueVideoId": "<videoId>"
}
```

Server:
- Calls Modal webhook for MediaPipe pose extraction.
- Calls OpenAI for coaching analysis text/score.
- Saves merged metrics in `technique_analysis.metrics`.

Metrics shape example:
```json
{
  "pose_data": [
    { "frame": 0, "landmarks": { "LEFT_KNEE": { "x": 0.41, "y": 0.70 } } },
    { "frame": 15, "landmarks": { "LEFT_KNEE": { "x": 0.36, "y": 0.68 } } }
  ],
  "ai_analysis": {
    "score": 7,
    "rating": "good",
    "en": {
      "diagnosis": "Good timing but unstable base...",
      "recommendations": [
        "Maintain a wider base through contact",
        "Increase knee bend",
        "Improve shoulder coil"
      ]
    }
  }
}
```

### Step 3: Generate correction images
Client calls:
```json
POST /api/auth/technique/correction-images
{
  "analysisId": "e89e164f-536f-4b9e-a07b-b263f8d77a0d"
}
```

Optional:
```json
{
  "analysisId": "<id>",
  "frameIndices": [0, 15, 30]
}
```

### Step 4: Server correction logic
`techniqueRouter.ts` does:

1. Auth + ownership checks.
2. If cached corrections exist in `metrics.correction_images`, returns them immediately.
3. Loads `pose_data` + `ai_analysis.en`.
4. Resolves video path and extracts each frame using `frameExtractor.ts`.
   - Uses ffmpeg-static binary fallback.
   - Tries `select=eq(n\,frame)` then fallback `select=gte(n\,frame)`.
5. Calls GPT (`translateRecommendationsToDeltas`) once to convert text coaching into structured landmark deltas.
6. Calls Gemini (`generateCorrectedImage`) per frame with:
   - original frame image (base64)
   - frame landmarks
   - diagnosis + recommendations
   - landmark delta instructions
7. Returns array of:
   - `frame`
   - `originalImage` (`data:image/png;base64,...`)
   - `correctedImage` (`data:image/png;base64,...`)
8. Caches results back into `metrics.correction_images`.

### Step 5: Client display
`technique.tsx` stores `correctionImages` and renders:
- Frame selector pills (`Frame 0`, `Frame 15`, ...)
- Side-by-side comparison:
  - Current (original)
  - Corrected (AI output)

State reset is done on new upload / start over to prevent stale frames from previous videos.

---

## Example End-to-End Input -> Output

## Example input to `/technique/correction-images`
```json
{
  "analysisId": "e89e164f-536f-4b9e-a07b-b263f8d77a0d"
}
```

## Example server-internal GPT deltas output
```json
{
  "deltas": [
    {
      "landmark": "LEFT_KNEE",
      "axis": "y",
      "direction": "decrease",
      "magnitude": "moderate",
      "reason": "increase knee bend while staying balanced"
    },
    {
      "landmark": "LEFT_SHOULDER",
      "axis": "x",
      "direction": "increase",
      "magnitude": "small",
      "reason": "improve shoulder coil"
    }
  ]
}
```

## Example output from `/technique/correction-images`
```json
{
  "corrections": [
    {
      "frame": 0,
      "originalImage": "data:image/png;base64,iVBORw0KGgoAAA...",
      "correctedImage": "data:image/png;base64,iVBORw0KGgoBBB..."
    },
    {
      "frame": 15,
      "originalImage": "data:image/png;base64,iVBORw0KGgoCCC...",
      "correctedImage": "data:image/png;base64,iVBORw0KGgoDDD..."
    }
  ]
}
```

---

## Logging You Should See (Healthy Run)

Server logs should include:
- `Correction-images request received`
- `Generating correction images { frameCount, frames }`
- `GPT landmark deltas { deltaCount, ... }`
- `Extracting frame <n> from video`
- `Extracted frame hash { frame, hash, bytes }`
- `Generating corrected image for frame <n>`
- `Correction images generated { successCount, totalFrames }`

If frame hashes are different across frames, extraction is working correctly.

---

## Common Failure Modes and Fixes

1. `spawn ffmpeg ENOENT`
- Cause: ffmpeg binary not found.
- Fix: already handled with `ffmpeg-static`; optional override with `FFMPEG_PATH`.

2. Same frame appears repeatedly
- Potential causes:
  - stale client state (old correction images not reset)
  - extraction filter fallback behavior
- Fixes:
  - reset correction state on new upload / start over
  - frame extraction now uses exact + fallback strategy
  - frame hash logging added for validation

3. Empty `corrections` response
- Cause: extraction or Gemini step failing per frame.
- Check logs around `Failed to process frame`.

4. Slow generation
- Cause: image generation per frame is expensive.
- Current setting: `MAX_CONCURRENT_FRAMES = 3`.
- Tuning options: reduce frame count, lower concurrency, or pre-cache asynchronously.

---

## Environment Variables Required

- `GEMINI_API_KEY` (required)
- `OPENAI_API_KEY` (required for landmark deltas and technique analysis text)
- `MODAL_WEBHOOK_URL` (required for pose extraction)
- `PUBLIC_VIDEO_BASE_URL` / `PUBLIC_BASE_URL` (must be publicly reachable for Modal)
- optional: `FFMPEG_PATH` (if you want to force a specific ffmpeg binary)

---

## Notes on Caching

`/technique/correction-images` caches output in:
- `technique_analysis.metrics.correction_images`

This means:
- first request for an analysisId does full generation.
- later requests for same analysisId return cached images quickly.

If you need fresh corrections for the same analysisId, you must clear that cached key or create a new analysis.

