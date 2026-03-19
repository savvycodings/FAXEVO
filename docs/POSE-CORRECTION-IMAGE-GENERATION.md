# Pose-Correction Image Generation — Technical Runbook

## Overview

Generate "corrected pose" images for every 15-frame interval of the user's Padel video.
The images should depict **the exact same player** but with their body repositioned into the biomechanically correct posture, based on the AI coach's recommendations.

---

## 1 — How NanoBanana (Gemini) Image Generation Works Today

### Client → Server → Gemini pipeline

```
images.tsx                 imagesRouter.ts              gemini.ts
───────────                ──────────────               ─────────
POST /images/gemini  ───►  multer (optional file)  ───► Gemini API
 • prompt (string)         upload.single('file')        generateContent
 • model (string)                                       ▼
 • file  (optional)                                     candidates[0].content.parts[]
                                                        find part with inlineData
                                                        ▼
                                                        { image: "data:<mime>;base64,..." }
```

### Model mapping

| Client key       | Gemini model ID                 |
|------------------|---------------------------------|
| `nanoBanana`     | `gemini-2.5-flash-image`        |
| `nanoBananaPro`  | `gemini-3-pro-image-preview`    |

### Gemini generateContent request body

```json
{
  "contents": [{
    "parts": [
      { "text": "<prompt>" },
      { "inline_data": { "mime_type": "image/jpeg", "data": "<base64>" } }
    ]
  }],
  "generationConfig": {
    "responseModalities": ["TEXT", "IMAGE"]
  }
}
```

- The `parts` array accepts **text + image together** — this is the key capability we leverage.
- When an image part is included, Gemini treats it as a reference / source and the text part as the editing instruction.
- Response returns a new image as `inlineData.data` (base64).

### How `images.tsx` displays the result

```tsx
<Image source={{ uri: response.image }} style={styles.image} />
```

The `response.image` is a `data:image/png;base64,...` data-URI. React Native renders it directly.

---

## 2 — How Technique Analysis Produces Pose Data

### Pipeline

```
technique.tsx               techniqueRouter.ts            Modal (MediaPipe)       GPT
─────────────               ──────────────────            ────────────────        ───
1. Upload video ──────────► POST /technique/upload
                            ▼ save to disk, DB row
2. Analyze ───────────────► POST /technique/analyze
                            ▼ build public video URL
                            POST MODAL_WEBHOOK_URL  ────► MediaPipe pose
                            ◄─── { metrics }              detection
                            ▼                              ▼
                            Send pose_data to GPT  ──────► AI analysis JSON
                            ◄─── { score, rating,          (diagnosis,
                                   observations,            observations,
                                   recommendations }        recommendations)
                            ▼
                            Store combined metrics
                            in techniqueAnalysis table

3. Poll GET /analysis/:id ◄─── { status, metrics, feedbackText }
```

### What the metrics object contains

```json
{
  "pose_data": [
    {
      "frame": 0,
      "landmarks": {
        "NOSE":           { "x": 0.38, "y": 0.54 },
        "LEFT_SHOULDER":  { "x": 0.42, "y": 0.57 },
        "RIGHT_SHOULDER": { "x": 0.33, "y": 0.57 },
        "LEFT_ELBOW":     { "x": 0.43, "y": 0.61 },
        "LEFT_WRIST":     { "x": 0.41, "y": 0.63 },
        "LEFT_HIP":       { "x": 0.39, "y": 0.65 },
        "LEFT_KNEE":      { "x": 0.41, "y": 0.70 },
        "LEFT_ANKLE":     { "x": 0.40, "y": 0.76 },
        "...33 landmarks total per frame..."
      }
    },
    { "frame": 15, "landmarks": { "..." } },
    { "frame": 30, "landmarks": { "..." } },
    { "frame": 45, "landmarks": { "..." } },
    { "frame": 60, "landmarks": { "..." } }
  ],
  "ai_analysis": {
    "score": 7,
    "rating": "good",
    "en": {
      "diagnosis": "...",
      "observations": ["...", "...", "..."],
      "recommendations": ["...", "...", "..."]
    },
    "es": { "..." }
  },
  "total_frames": 69,
  "analyzed_frames": 5
}
```

Key points:
- Landmarks are **normalized 0→1** (0,0 = top-left of video frame).
- Sampled every **15 frames** (`frame: 0, 15, 30, 45, 60`).
- 33 MediaPipe body landmarks per frame (nose, eyes, ears, shoulders, elbows, wrists, hips, knees, ankles, heels, foot index, etc.).

---

## 3 — The Goal: Corrected-Pose Image Generation

For each sampled frame (every 15 frames), produce an image showing:

1. **The same person** (appearance, clothing, environment, camera angle).
2. **The corrected body position** as recommended by the AI coach.

### Why this is valuable

- Players see a side-by-side: "what you did" vs. "what you should do".
- Much more intuitive than text-only recommendations.
- Reinforces muscle memory by providing a visual reference.

---

## 4 — Proposed Architecture

### 4.1 New server endpoint

```
POST /technique/correction-images
```

**Request body:**

```json
{
  "analysisId": "uuid",
  "frameIndices": [0, 15, 30, 45, 60]
}
```

If `frameIndices` is omitted, default to all frames in `pose_data`.

**Processing steps:**

1. Fetch `techniqueAnalysis` row by `analysisId` → get `metrics`.
2. Extract `pose_data` and `ai_analysis` from metrics.
3. For each requested frame:
   a. Extract the video frame as an image (use `ffmpeg` on the server to grab the exact frame from the stored video file).
   b. Build a Gemini prompt that includes: the extracted frame image (as `inline_data`), the current pose landmarks, the AI recommendations, and instructions to redraw the person with corrected positioning.
   c. Call Gemini `generateContent` with `responseModalities: ["IMAGE"]`.
   d. Collect the returned base64 image.
4. Return all corrected images.

**Response:**

```json
{
  "corrections": [
    {
      "frame": 0,
      "originalImage": "data:image/png;base64,...",
      "correctedImage": "data:image/png;base64,..."
    },
    { "frame": 15, "..." },
    { "frame": 30, "..." }
  ]
}
```

### 4.2 Frame extraction with ffmpeg

```bash
# Extract frame N from video file
ffmpeg -i /path/to/video.mp4 -vf "select=eq(n\\,FRAME_NUMBER)" -frames:v 1 -f image2pipe -vcodec png pipe:1
```

Server-side (Node.js):

```ts
import { execFile } from "child_process";

function extractFrame(videoPath: string, frameNumber: number): Promise<Buffer> {
  return new Promise((resolve, reject) => {
    const args = [
      "-i", videoPath,
      "-vf", `select=eq(n\\,${frameNumber})`,
      "-frames:v", "1",
      "-f", "image2pipe",
      "-vcodec", "png",
      "pipe:1",
    ];
    const proc = execFile("ffmpeg", args, { maxBuffer: 10 * 1024 * 1024 });
    const chunks: Buffer[] = [];
    proc.stdout?.on("data", (chunk) => chunks.push(chunk));
    proc.on("close", (code) => {
      if (code === 0) resolve(Buffer.concat(chunks));
      else reject(new Error(`ffmpeg exited with code ${code}`));
    });
    proc.on("error", reject);
  });
}
```

### 4.3 Building the Gemini prompt

This is the most critical piece. The prompt must:
- Tell Gemini to keep the person's identity, clothing, and environment intact.
- Provide the current landmark positions so Gemini understands the current pose.
- Provide the target/corrected landmark positions (computed from the AI recommendations).
- Ask it to regenerate the image with only the body repositioned.

#### Prompt template

```
You are a sports biomechanics visualization engine.

I am providing you with a single frame from a Padel tennis video.
The player currently has these body landmark positions (normalized 0-1, origin top-left):

CURRENT POSE (frame {frameNumber}):
{JSON.stringify(currentLandmarks, null, 2)}

An expert Padel coach analyzed this frame and recommends these corrections:
{recommendations.join("\n")}

The overall diagnosis is:
{diagnosis}

TASK:
Regenerate this EXACT image — same person, same clothing, same court, same camera angle, same lighting — but adjust ONLY the player's body position to reflect the coach's recommendations. Specifically:
- {specific correction 1, e.g. "Widen the stance: move LEFT_ANKLE and RIGHT_ANKLE further apart laterally"}
- {specific correction 2, e.g. "Increase shoulder coil: rotate LEFT_SHOULDER back and RIGHT_SHOULDER forward"}
- {specific correction 3, e.g. "Bend knees more: lower LEFT_KNEE and RIGHT_KNEE y-coordinates"}

Keep everything else identical. The output should look like a real photograph, not a drawing or diagram.
```

#### Auto-computing specific corrections from AI recommendations

The AI analysis text is human-readable ("maintain a wider base", "increase knee bend"). We can use a secondary GPT call to translate these into **landmark delta instructions**:

```
POST /v1/chat/completions (GPT)

Prompt:
Given these AI padel coach recommendations:
1. "Maintain a wider, stable base through contact"
2. "Increase knee bend and drive through the front leg"
3. "Improve torso/shoulder coil before the swing"

And the current landmarks:
{ ... }

Output a JSON array of specific landmark adjustments:
[
  { "landmark": "LEFT_ANKLE", "axis": "x", "direction": "decrease", "magnitude": "moderate", "reason": "wider base" },
  { "landmark": "RIGHT_ANKLE", "axis": "x", "direction": "increase", "magnitude": "moderate", "reason": "wider base" },
  { "landmark": "LEFT_KNEE", "axis": "y", "direction": "increase", "magnitude": "small", "reason": "more knee bend" },
  ...
]
```

These structured deltas get folded into the Gemini image prompt for precision.

### 4.4 Client-side: displaying corrections in technique.tsx

On Step 3 (results), add a new accordion section:

```
┌─────────────────────────────────────────┐
│  Pose Corrections                    ▼  │
│  5 frames analyzed                      │
├─────────────────────────────────────────┤
│                                         │
│  Frame 0                                │
│  ┌──────────┐  ┌──────────┐             │
│  │ Original │  │Corrected │             │
│  │          │  │          │             │
│  └──────────┘  └──────────┘             │
│                                         │
│  Frame 15                               │
│  ┌──────────┐  ┌──────────┐             │
│  │ Original │  │Corrected │             │
│  │          │  │          │             │
│  └──────────┘  └──────────┘             │
│                                         │
│  ...                                    │
└─────────────────────────────────────────┘
```

Or as a swipeable carousel with before/after slider for each frame.

---

## 5 — Implementation Steps

### Phase 1: Server-side frame extraction
1. Install `ffmpeg` on the server / ensure it's available in the Railway container.
2. Create `server/src/technique/frameExtractor.ts` with `extractFrame(videoPath, frameNum)`.
3. Test: extract a single frame from an uploaded video, return as base64.

### Phase 2: Correction prompt engineering
1. Create `server/src/technique/correctionPrompt.ts`.
2. Build the GPT "recommendation → landmark deltas" translation call.
3. Build the Gemini "image + pose + corrections → corrected image" prompt.
4. Test with a single frame end-to-end.

### Phase 3: API endpoint
1. Add `POST /technique/correction-images` to `techniqueRouter.ts`.
2. Validate `analysisId`, fetch metrics, loop frames.
3. For each frame: extract → build prompt → call Gemini → collect result.
4. Return array of `{ frame, originalImage, correctedImage }`.
5. Consider: run frames in parallel (Promise.all with concurrency limit of 3) for speed.

### Phase 4: Client UI
1. In `technique.tsx` Step 3, add state: `correctionImages`, `correctionsLoading`.
2. Trigger correction generation after analysis completes (or on button press).
3. Render side-by-side original/corrected images in a new accordion or carousel.
4. Add loading skeleton while images generate.

### Phase 5: Caching & optimization
1. Store generated correction images on disk (like videos) with a DB reference.
2. On subsequent views, serve cached images instead of re-generating.
3. Consider generating corrections asynchronously (background job) and polling for completion.

---

## 6 — Key Considerations

### Image quality & consistency
- Gemini image editing works best with **clear, well-lit source frames**.
- The `gemini-3-pro-image-preview` (nanoBananaPro) model produces higher quality but is slower/costlier.
- For production, consider using `nanoBananaPro` for correction images since quality matters.

### Latency
- Each frame: ~2-4s for ffmpeg extraction + ~5-15s for Gemini image generation.
- 5 frames = ~35-95s total if sequential.
- With parallelism (3 concurrent): ~12-30s.
- **Recommendation**: generate asynchronously and show a progress indicator.

### Cost
- Gemini image generation costs per call (text + image input + image output).
- 5 frames per analysis = 5 Gemini calls + 1 GPT call for landmark deltas.
- Consider offering this as a "premium" feature or limiting to 3 key frames.

### Pose accuracy limitations
- Gemini is a generative model, not a biomechanics engine — it interprets correction instructions creatively.
- Results are "directionally correct" illustrations, not pixel-perfect biomechanical simulations.
- For the best results, provide very specific visual instructions ("widen stance by 20%", "bend knees 30 degrees more") rather than vague ones.

### Alternative: skeleton overlay approach
Instead of (or in addition to) full image regeneration, consider:
1. Draw the **current pose skeleton** on the original frame (using the landmark coordinates).
2. Draw the **corrected pose skeleton** as a semi-transparent overlay in a different color.
3. This is deterministic, fast, cheap, and precise — but less visually impressive.

This can be implemented entirely client-side using `react-native-svg`:
```tsx
<Svg width={frameWidth} height={frameHeight}>
  {/* Original pose in red */}
  <Line x1={nose.x * w} y1={nose.y * h} x2={leftShoulder.x * w} y2={leftShoulder.y * h} stroke="red" />
  {/* Corrected pose in green */}
  <Line x1={correctedNose.x * w} y1={correctedNose.y * h} ... stroke="green" />
</Svg>
```

---

## 7 — Example Flow (End to End)

```
1. User uploads Padel video
2. Modal/MediaPipe extracts pose_data every 15 frames
3. GPT analyzes poses → score, observations, recommendations
4. User views results on Step 3
5. User taps "Show Corrections" button
6. Client: POST /technique/correction-images { analysisId }
7. Server:
   a. Fetch analysis metrics from DB
   b. For frame 0:
      - ffmpeg extracts frame 0 as PNG buffer
      - GPT translates recommendations → landmark deltas for frame 0
      - Gemini receives: original frame image + correction prompt
      - Gemini returns: corrected frame image
   c. Repeat for frames 15, 30, 45, 60
8. Server responds with all original + corrected image pairs
9. Client renders side-by-side comparisons in accordion/carousel
10. User swipes through frames seeing "what you did" vs "what to do"
```

---

## 8 — Environment Variables Required

| Variable | Purpose | Where |
|----------|---------|-------|
| `GEMINI_API_KEY` | Already exists — used for NanoBanana | Railway |
| `OPENAI_API_KEY` | Already exists — used for GPT analysis | Railway |
| `MODAL_WEBHOOK_URL` | Already exists — MediaPipe pose detection | Railway |
| — | `ffmpeg` binary must be available in `$PATH` | Railway container |

No new env vars needed. `ffmpeg` is pre-installed on most Railway Docker images, but verify with:
```bash
railway run ffmpeg -version
```

---

## 9 — Database Changes

Optional: add a `correctionImages` JSON column to `techniqueAnalysis` to cache generated images and avoid re-generation on subsequent views.

```sql
ALTER TABLE technique_analysis
ADD COLUMN correction_images JSONB;
```

Schema:
```json
[
  {
    "frame": 0,
    "originalImage": "/technique/correction/abc123-f0-original.png",
    "correctedImage": "/technique/correction/abc123-f0-corrected.png"
  }
]
```
