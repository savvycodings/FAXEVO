## Technique Results UI Structure

This document describes the sections we render on the `Technique` screen after a video has been analyzed. It mirrors the data structure we get back from the backend (`metrics.ai_analysis`) and is meant to guide both design and implementation.

- **Technique Rating**
  - **Source**: `metrics.ai_analysis.score`, `metrics.ai_analysis.rating`, `metrics.ai_analysis.en.diagnosis`.
  - **Purpose**: Quick, high-level summary of the player’s overall technique quality.
  - **Content**:
    - Numeric score \(0–10\).
    - Rating label: `"excellent" | "good" | "needs_improvement" | "poor"`.
    - Short English diagnosis (2–3 sentences).
  - **UI**:
    - Accordion with title **Technique Rating**.
    - When expanded, shows:
      - Big numeric score.
      - Rating label (e.g. “Needs Improvement”).
      - Short diagnosis paragraph.

- **Observations**
  - **Source**: `metrics.ai_analysis.en.observations` (string[]).
  - **Purpose**: Call out what the model is seeing in the player’s movement.
  - **Content**:
    - 3–5 bullet points, e.g. stance, racket prep, footwork timing, etc.
  - **UI**:
    - Accordion with title **Observations**.
    - When expanded, shows bullet list of the English observations.

- **Recommendations**
  - **Source**: `metrics.ai_analysis.en.recommendations` (string[]).
  - **Purpose**: Give actionable coaching advice and drills.
  - **Content**:
    - 3–5 bullet points with concrete actions / drills.
  - **UI**:
    - Accordion with title **Recommendations**.
    - When expanded, shows bullet list of the English recommendations.

- **Video Playback Card**
  - **Source**: `uploadedVideoUrl` and the original technique video metadata.
  - **Purpose**: Let the user re‑watch the analyzed clip while reading the feedback.
  - **Content**:
    - Video player using the uploaded technique video.
    - Short title, e.g. “Forehand”.
    - Optional supporting bullet points (can mirror key recommendations).
  - **UI**:
    - Full‑width card under the three accordions.
    - Embedded video with play controls.
    - 2–3 bullet points summarising key things to watch for in this clip.

### Notes

- We currently prioritize **English** (`en`) for on‑screen text, but the raw JSON also includes a full **Spanish** (`es`) section, which we can surface later (e.g. language toggle).
- All sections should degrade gracefully if some fields are missing (e.g. show only metrics, or just `feedbackText`).

