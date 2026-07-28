## Comfy correction images (under the hood)

- **Entry (app → API)**: App calls `POST /technique/correction-images` with `analysisId` (and optional `frameIndices`, `forceRegenerate`, `regenerationFeedback`). Server reads `technique_analysis.metrics` and writes back `metrics.correction_images_comfy` + `metrics.correction_context_comfy` (URLs + small context only).

```mermaid
flowchart LR
  App-->CorrApi["POST /technique/correction-images"]-->Analysis[(technique_analysis.metrics)]
  CorrApi-->Cache["metrics.correction_images_comfy + correction_context_comfy"]
  CorrApi-->RegenFb[(technique_correction_regeneration_feedback)]
```

- **Pose landmarks source**: Landmarks come from `metrics.pose_data[]` (MediaPipe pose per video frame) plus `metrics.user_clips` / `metrics.impact_pose_sequence` if present. If the impact sequence is missing but clips exist, the server rebuilds it from pose rows inside the clip window.

```mermaid
flowchart LR
  PoseData["metrics.pose_data"]-->FramePick["selectPoseFramesForCorrections()"]
  UserClips["metrics.user_clips"]-->FramePick
  ImpactSeq["metrics.impact_pose_sequence"]-->FramePick
  FramePick-->Frames["PoseFrameRow[] (frame+landmarks)"]
```

- **Which frames get images**: Server samples up to `XEVO_CORRECTION_MAX_FRAMES` across the selected motion (prefers frames near impact when available). If the client requests specific `frameIndices`, it uses those and only generates missing frames (cached frames are reused).

```mermaid
flowchart LR
  Request["frameIndices?"]-->Pick
  CacheCheck["metrics.correction_images_comfy cache"]-->Pick
  Pick-->GenerateList["framesToGenerate[]"]
```

- **Still extraction (video → PNG)**: For each chosen `frame`, the server uses ffmpeg `extractFrame(videoPath, frameNumber)` to get a PNG buffer from the original uploaded mp4. Those extracted stills are the “before” images.

```mermaid
flowchart LR
  Vid[(technique_video.cloudinaryPublicId)]-->FFmpeg["extractFrame()"]
  FFmpeg-->Png["originalFrame.png (Buffer)"]
```

- **AI “suggestions” → joint targets**: The correction job turns the AI Coach text (`en.diagnosis`, `en.recommendations`, plus a detection hint) into **joint deltas** (`LandmarkDelta[]`). It computes a robust fallback delta set from the impact frame, then tries per-frame deltas and falls back to impact deltas if a per-frame delta call fails.

```mermaid
flowchart LR
  CoachText["metrics.ai_analysis.en (diagnosis+recommendations)"]-->DeltaLLM["translateRecommendationsToDeltas()"]
  ImpactLandmarks-->DeltaLLM-->ImpactDeltas["impactDeltas[]"]
  FrameLandmarks-->FrameDeltas["per-frame deltas or fallback"]
```

- **Shot + handedness (for prompt correctness)**: The server classifies shot type + handedness (LLM) and then merges it with higher-trust hints: user profile dominant hand + pose-based `racket_hand` consensus. This prevents mirrored corrections and keeps the prompt aligned with the actual striker hand.

```mermaid
flowchart LR
  Classify["classifyShotAndHandedness()"]-->Merge["mergeCorrectionShotAndHandedness()"]
  Profile[(user_profile.dominantHand)]-->Merge
  Geometry["pose_data.racket_hand consensus"]-->Merge
  Merge-->ShotHand["ShotAndHandedness (effective)"]
```

- **Optional pro-library target (makes “ideal” concrete)**: If retrieval has a top neighbor, the server loads pro pose sequence (`train_sample.poseSequence`) and can pull a pro reference frame from the pro video. Pro landmarks produce extra “pro gap” deltas which are merged into the coach deltas (so the edit moves toward a real pro exemplar).

```mermaid
flowchart LR
  Retrieval["metrics.retrieval.neighbors[0]"]-->TrainSample[(train_sample.poseSequence)]
  TrainSample-->ProDeltas["proGapToLandmarkDeltas()"]
  CoachDeltas-->MergeDeltas["mergeLandmarkDeltas()"]
  ProDeltas-->MergeDeltas-->FinalDeltas["LandmarkDelta[]"]
```

- **Prompt that drives the edit (Qwen workflow)**: For Comfy “qwen” workflows, the server builds a long structured prompt including: scene invariants, top priority moves, diagnosis/recommendations, shot/handedness, raw landmark JSON, and per-joint `current → target` deltas. This is the “brain” that tells the image model what to change while keeping identity/background fixed.

```mermaid
flowchart LR
  FinalDeltas-->Prompt["buildQwenCorrectionPrompt()"]
  ShotHand-->Prompt
  Landmarks-->Prompt
  CoachText-->Prompt
```

- **Mask (where to inpaint)**: Server creates an inpaint mask from pose landmarks (convex hull → dilation → blur) so Comfy edits mostly the player silhouette, not the court/background. Mask size is matched to the workflow’s megapixels scaling so the mask aligns with the latent resolution.

```mermaid
flowchart LR
  Landmarks-->Hull["convexHull + dilateHull"]-->MaskPng["buildCoachingInpaintMaskPng()"]
  WorkflowScale["ImageScaleToTotalPixels megapixels"]-->MaskDims["dimensionsForMegapixels()"]-->MaskPng
```

- **Workflow template + node patching**: The server loads a Comfy API workflow JSON (e.g. `server/workflows/qwen_image_edit_plus_gguf_correction.api.json`) then patches specific node IDs from env: load-image nodes, prompt node, optional mask node, openpose/controlnet strength, ksampler denoise, and megapixels. It then uploads the frame image (and optional ref + mask) to Comfy and queues the workflow.

```mermaid
flowchart LR
  ApiJson["*.api.json workflow template"]-->Patch["patch nodes (ids+inputs)"]
  Png-->Upload["comfyUploadImage()"]-->Patch
  MaskPng-->UploadMask["comfyUploadImage(mask)"]-->Patch
  Prompt-->Patch-->Queue["comfyQueuePrompt()"]-->Wait["comfyWaitForOutputImage()"]
```

- **Output handling + storage**: Comfy returns a generated image which the server fetches and converts to a data URI, then normalizes/persists it to disk under `/uploads/technique-corrections/<analysisId>/...`. The URL pairs are cached back into `technique_analysis.metrics.correction_images_comfy` so future requests can return instantly.

```mermaid
flowchart LR
  Wait-->Out["output filename/subfolder"]-->Fetch["comfyImageToDataUri()"]
  Fetch-->Persist["persistCorrectionImageUri()"]-->Uploads["/uploads/technique-corrections/..."]
  Persist-->CacheBack["metrics.correction_images_comfy"]
```

- **User feedback capture (regen)**: When the user types feedback in the regen modal, the server stores it in `technique_correction_regeneration_feedback.message` with a coaching snapshot (diagnosis, shot_context, recs, frame_indices).

```mermaid
flowchart LR
  AppFeedback["regenerationFeedback.message"]-->Save[(technique_correction_regeneration_feedback)]
  Save-->Link["techniqueAnalysisId -> technique_analysis.id"]
```

