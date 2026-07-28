## Screens (app) → routes → DB

- **AI Coach (`app/src/screens/technique.tsx`)**: `POST /technique/upload` → `POST /technique/analyze` → `GET /technique/analysis/:id` + `GET /technique/analysis/:id/correction-images`. Stores upload in `technique_video`; stores analysis in `technique_analysis` (`metrics`, `feedbackText`); regen feedback in `technique_correction_regeneration_feedback`; coach queue (optional) in `coach_video_review`.

```mermaid
flowchart LR
  TechniqueScreen-->Upload["POST /technique/upload"]-->TechniqueVideo[(technique_video)]
  TechniqueScreen-->Analyze["POST /technique/analyze"]-->TechniqueAnalysis[(technique_analysis)]
  TechniqueScreen-->Corr["POST/GET correction-images"]-->Corrections["metrics.correction_images + technique_correction_regeneration_feedback"]
```

- **Activities list (`app/src/screens/Activities.tsx` + `app/src/context/SessionDataContext.tsx`)**: `GET /technique/activities`. Reads from `technique_analysis` (+ joins/lookup for coach review status via `coach_video_review`).

```mermaid
flowchart LR
  ActivitiesScreen-->ActivitiesApi["GET /technique/activities"]-->TechniqueAnalysis[(technique_analysis)]
  ActivitiesApi-->CoachReview[(coach_video_review)]
```

- **Activities detail (`app/src/screens/ActivitiesVideoAnalysis.tsx`)**: `GET /technique/analysis/:id` + `/pose-overlay` + `/correction-images`. Reads from `technique_analysis.metrics` (pose overlay derived) and correction images embedded in `metrics` (normalized to `/uploads/technique-corrections/...`).

```mermaid
flowchart LR
  ActivitiesDetail-->Analysis["GET /technique/analysis/:id"]-->TechniqueAnalysis[(technique_analysis.metrics)]
  ActivitiesDetail-->Overlay["GET /pose-overlay"]-->PoseOverlay["derived from metrics.pose_data"]
  ActivitiesDetail-->Corr["GET /correction-images"]-->Images["metrics.correction_images (urls)"]
```

- **My Coach (students) (`app/src/screens/MyCoachScreen.tsx`)**: `GET /profile/coach-students`. Reads coach/student links and pending review ids (backed by `coach_student` + `coach_video_review`).

```mermaid
flowchart LR
  MyCoachScreen-->CoachStudents["GET /profile/coach-students"]-->CoachStudent[(coach_student)]
  CoachStudents-->CoachReview[(coach_video_review)]
```

- **Student coach review (`app/src/screens/StudentCoachReviewScreen.tsx`)**: `GET /coach/review/:id`. Reads `coach_video_review` + latest `technique_analysis` for that video; annotations from `coach_review_annotation`.

```mermaid
flowchart LR
  StudentReviewScreen-->GetReview["GET /coach/review/:id"]-->CoachReview[(coach_video_review)]
  GetReview-->TechniqueAnalysis[(technique_analysis)]
  GetReview-->Annotations[(coach_review_annotation)]
```

- **Coach review editor (`app/src/screens/CoachReviewEditorScreen.tsx`)**: `GET /coach/review/:id` + `POST /coach/review/:id/submit`. Writes `coach_video_review.coachFeedbackText` / `submittedAt` and `coach_review_annotation` rows (per frame comment/markup).

```mermaid
flowchart LR
  CoachReviewEditor-->Load["GET /coach/review/:id"]-->CoachReview[(coach_video_review)]
  CoachReviewEditor-->Submit["POST /coach/review/:id/submit"]-->CoachReviewWrite[(coach_video_review)]
  Submit-->AnnotationWrite[(coach_review_annotation)]
```

- **Admin Train (`app/src/screens/AdminTrain.tsx`)**: `POST /train/upload` + `GET /train/video/:id` + `GET /train/sample/:id` + `GET /train/admin/pose-landmarks-coverage`. Stores labeled clip in `train_video` (`strokeLabel` is the human title, `strokePreset` is the enum bucket); extraction in `train_sample`; k-NN vector in `train_sample_embedding`.

```mermaid
flowchart LR
  AdminTrainScreen-->TrainUpload["POST /train/upload"]-->TrainVideo[(train_video)]
  AdminTrainScreen-->TrainSample["GET /train/sample/:id"]-->TrainSampleTable[(train_sample)]
  TrainSampleTable-->Embedding[(train_sample_embedding)]
```

- **Neon-friendly analysis overview (SQL view)**: query `public.technique_analysis_overview` to inspect `feedbackText`, chosen shot label/preset, correction image urls, and latest regen feedback without downloading huge `metrics`.

```mermaid
flowchart LR
  NeonQuery-->OverviewView[(technique_analysis_overview)]
  OverviewView-->TechniqueAnalysis[(technique_analysis)]
  OverviewView-->RegenFeedback[(technique_correction_regeneration_feedback)]
```

