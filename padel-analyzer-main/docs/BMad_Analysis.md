# BMad Phase 1: Analysis - Padel Video Analyzer

## Vision Model Trade-off Analysis

### Option A: Hybrid (MediaPipe + OpenAI Vision)
**Architecture:** Client-side pose extraction (MediaPipe) → LLM Reasoning (OpenAI)
*   **Pros:**
    *   **Cost:** Ultra-low. MediaPipe runs locally/free. Only pay OpenAI for text analysis of coordinates + keyframes.
    *   **Speed:** Instant feedback on pose alignment.
    *   **Privacy:** Raw video doesn't necessarily leave device if only coordinates are sent (though keyframes might).
*   **Cons:**
    *   **Ball Tracking:** MediaPipe is poor at small, fast objects (padel ball).
    *   **Complex Motion:** Struggles with occlusion (body blocking arm).
*   **Verdict:** Best for "Form" (static angles), weak for "Result" (ball speed/trajectory).

### Option B: Google Cloud Vision / Video Intelligence
**Architecture:** Server-side Video Processing (Vertex AI)
*   **Pros:**
    *   **Temporal Understanding:** `Video Intelligence API` understands time/flow, not just frames.
    *   **Object Tracking:** Superior built-in models for tracking small objects (ball) across frames.
    *   **AutoML:** Can train a custom model specifically on "Correct Padel Serve" vs "Incorrect" if we label data.
*   **Cons:**
    *   **Cost:** Higher. Processed per minute of video.
    *   **Latency:** Upload -> Process -> Result cycle is slower than local inference.
*   **Verdict:** Best for "Game Physics" and professional deep-dives.

### Recommendation: **Tiered Approach**
1.  **MVP (Free/Fast):** MediaPipe for instant posture feedback (knees bent? arm height?).
2.  **Premium:** Google Video Intelligence for full swing/ball tracking analysis.

## Padel-Specific Metrics (The "What")

To diagnose technique, we must track:
1.  **Preparation Height:** Racket head above wrist?
2.  **Contact Point:** In front of body?
3.  **Knee Flexion:** Angle of knee at impact.
4.  **Follow-through:** Does racket finish across opposite shoulder?

## Next Steps
*   Define API schema for sending video/coordinates.
*   Select one specific shot (e.g., "The Serve") for MVP to limit scope.
