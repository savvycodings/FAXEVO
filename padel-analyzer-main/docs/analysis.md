# How Video Analysis Works

This document explains the technical details of how Padel Analyzer processes videos and generates AI-powered feedback.

## Overview

The analysis pipeline consists of three stages:

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Frame     │────▶│    Pose     │────▶│     AI      │
│ Extraction  │     │  Detection  │     │  Analysis   │
└─────────────┘     └─────────────┘     └─────────────┘
```

---

## Stage 1: Frame Extraction

**Tool:** OpenCV (cv2)

Videos are processed frame-by-frame. To balance accuracy with performance, we sample every 15th frame:

```
Frame 0   → Analyze
Frame 15  → Analyze
Frame 30  → Analyze
...
```

**Why every 15th frame?**
- At 30fps, this gives ~2 samples per second
- Captures movement changes without excessive processing
- Reduces API costs and processing time

---

## Stage 2: Pose Detection

**Tool:** MediaPipe Pose Landmarker

MediaPipe detects **33 body landmarks** in each frame:

```
                    0: nose
                   /   \
           11,12: shoulders
          /    |    \
    13,14: elbows    23,24: hips
         |                  |
    15,16: wrists    25,26: knees
         |                  |
    17-22: hands     27,28: ankles
                          |
                     29-32: feet
```

Each landmark has:
- `x`: Horizontal position (0.0 = left, 1.0 = right)
- `y`: Vertical position (0.0 = top, 1.0 = bottom)
- `visibility`: Confidence score (0.0 to 1.0)

**Landmark Mapping:**
| Index | Body Part |
|-------|-----------|
| 0 | Nose |
| 11, 12 | Left/Right Shoulder |
| 13, 14 | Left/Right Elbow |
| 15, 16 | Left/Right Wrist |
| 23, 24 | Left/Right Hip |
| 25, 26 | Left/Right Knee |
| 27, 28 | Left/Right Ankle |

---

## Stage 3: AI Analysis

**Tool:** Anthropic Claude Sonnet 4 (claude-sonnet-4-20250514)

### Data Preparation

We format pose data into a structured summary for Claude:

```json
{
  "frame": 45,
  "shoulders": {
    "left": {"x": 0.35, "y": 0.28},
    "right": {"x": 0.65, "y": 0.29}
  },
  "elbows": { ... },
  "wrists": { ... },
  "hips": { ... },
  "knees": { ... },
  "ankles": { ... }
}
```

We send up to **10 frames** of data to keep the context manageable.

### The Prompt

Claude receives this system prompt:

> You are an expert padel coach analyzing player technique from pose landmark data.
> Each frame contains x,y coordinates (0-1 normalized) for key body parts.
> 
> Analyze the poses and provide:
> 1. **rating**: "excellent", "good", "needs_improvement", or "poor"
> 2. **diagnosis**: One-sentence summary of technique quality
> 3. **observations**: 2-4 specific things you noticed about form
> 4. **recommendations**: 2-4 actionable training tips

### What Claude Analyzes

From the coordinate data, Claude infers:

| Aspect | What It Looks At |
|--------|------------------|
| **Posture** | Are shoulders level? Spine alignment? |
| **Footwork** | Stance width (hip-ankle distance), knee bend depth |
| **Arm Mechanics** | Elbow angles, wrist position during swing |
| **Balance** | Weight distribution based on hip position relative to feet |
| **Consistency** | How positions change across frames |

### Example Output

```json
{
  "score": 7,
  "rating": "good",
  "en": {
    "diagnosis": "Solid foundation with room for improvement in follow-through",
    "observations": [
      "Good knee bend providing strong base for power generation",
      "Shoulders slightly uneven during the swing motion",
      "Elbow position drops too early in the backswing",
      "Weight transfers well from back to front foot"
    ],
    "recommendations": [
      "Practice mirror drills focusing on keeping shoulders level",
      "Use shadow swings to maintain elbow height through contact",
      "Work on explosive hip rotation for added power",
      "Consider video recording from side angle for self-review"
    ]
  },
  "es": {
    "diagnosis": "Buena base con margen de mejora en el seguimiento del golpe",
    "observations": [
      "Buena flexión de rodillas para generación de potencia",
      "Hombros ligeramente desnivelados durante el swing",
      "El codo baja demasiado pronto en el backswing",
      "Buena transferencia de peso de pie trasero a delantero"
    ],
    "recommendations": [
      "Practicar frente al espejo para mantener los hombros nivelados",
      "Usar swings en sombra para mantener el codo alto durante el contacto",
      "Trabajar la rotación explosiva de caderas para más potencia",
      "Grabar desde un ángulo lateral para auto-revisión"
    ]
  }
}
```

---

## Limitations & Future Improvements

### Current Limitations

1. **No temporal analysis** — We analyze static poses, not movement velocity or acceleration
2. **2D only** — MediaPipe gives us 2D positions; depth perception is limited
3. **Single player** — Multiple players in frame may confuse detection
4. **Camera angle** — Best results with frontal or side-on camera views

### Planned Improvements

- **Motion tracking** — Analyze velocity and acceleration patterns
- **Shot detection** — Identify specific shots (forehand, backhand, serve)
- **Comparison mode** — Compare your technique to pros
- **3D analysis** — Use depth estimation for true 3D pose reconstruction
- **Video overlay** — Show skeleton overlay on the original video

---

## Performance Metrics

| Metric | Value |
|--------|-------|
| Processing time | ~15-30 seconds for 10-second video |
| Frames analyzed | ~20 frames for 10-second video |
| AI response time | ~2-3 seconds |
| Accuracy | Best with clear, well-lit footage |

---

## Technical Details

### MediaPipe Configuration

```python
mp_pose = mp.solutions.pose
mp_pose_obj = mp_pose.Pose(
    static_image_mode=False,
    model_complexity=0,
    enable_segmentation=False,
    min_detection_confidence=0.5
)
```

We use `model_complexity=0` (lightweight) for faster processing. Set to `1` or `2` for higher accuracy at the cost of speed.

### Claude Configuration

```python
client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=2048,
    messages=[{"role": "user", "content": prompt}]
)
```

The prompt enforces strict JSON output (no markdown, bilingual EN+ES) so the response can be parsed directly without post-processing.
