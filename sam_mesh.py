"""
Impact-frame mesh enrichment for padel analyzer Modal apps.

When SAM3D_ENABLED=1 and the HuggingFace SAM 3D Body model loads, runs real inference.
Otherwise builds a mesh-proxy 128-dim vector from MediaPipe landmarks (z + biomechanical angles)
so the server pipeline and admin tests can be wired before the heavy model is deployed.
"""

from __future__ import annotations

import math
import os
import time
from typing import Any

MESH_SPEC_VERSION = "sam_v1"
MESH_FEATURE_DIM = 128

# MediaPipe PoseLandmark names used for mesh-proxy features (subset + derived)
_KEY_JOINTS = (
    "LEFT_SHOULDER",
    "RIGHT_SHOULDER",
    "LEFT_ELBOW",
    "RIGHT_ELBOW",
    "LEFT_WRIST",
    "RIGHT_WRIST",
    "LEFT_HIP",
    "RIGHT_HIP",
    "LEFT_KNEE",
    "RIGHT_KNEE",
)


def _env_bool(name: str, default: bool = False) -> bool:
    value = str(os.getenv(name, "")).strip().lower()
    if not value:
        return default
    return value in ("1", "true", "yes", "on")


def _env_int(name: str, default: int, min_v: int, max_v: int) -> int:
    raw = str(os.getenv(name, "")).strip()
    if not raw:
        return default
    try:
        out = int(raw)
    except Exception:
        return default
    return max(min_v, min(max_v, out))


# Default number of impact-window frames to mesh-enrich (sequence matching needs several).
MESH_IMPACT_WINDOW_DEFAULT = 10


def _pt(landmarks: dict, name: str) -> tuple[float, float, float]:
    p = landmarks.get(name) or {}
    x = float(p.get("x", 0.5))
    y = float(p.get("y", 0.5))
    z = float(p.get("z", 0.0))
    return x, y, z


def _l2_normalize(vec: list[float]) -> list[float]:
    s = sum(x * x for x in vec)
    n = math.sqrt(s) + 1e-8
    return [x / n for x in vec]


def _angle_cosine(a: tuple[float, float, float], b: tuple[float, float, float], c: tuple[float, float, float]) -> float:
    """Cosine of angle at vertex b between segments ba and bc."""
    v1 = (a[0] - b[0], a[1] - b[1], a[2] - b[2])
    v2 = (c[0] - b[0], c[1] - b[1], c[2] - b[2])
    n1 = math.sqrt(sum(x * x for x in v1)) + 1e-8
    n2 = math.sqrt(sum(x * x for x in v2)) + 1e-8
    dot = sum(v1[i] * v2[i] for i in range(3)) / (n1 * n2)
    return max(-1.0, min(1.0, dot))


def mesh_proxy_feature_vector(landmarks: dict) -> list[float]:
    """
    128-dim L2-normalized vector from 2.5D landmarks (MediaPipe x,y,z).
    Mirrors server meshEmbedding.ts for consistent k-NN when SAM model is not loaded.
    """
    lh = _pt(landmarks, "LEFT_HIP")
    rh = _pt(landmarks, "RIGHT_HIP")
    ls = _pt(landmarks, "LEFT_SHOULDER")
    rs = _pt(landmarks, "RIGHT_SHOULDER")
    hip_mid = ((lh[0] + rh[0]) / 2, (lh[1] + rh[1]) / 2, (lh[2] + rh[2]) / 2)
    shoulder_mid = ((ls[0] + rs[0]) / 2, (ls[1] + rs[1]) / 2, (ls[2] + rs[2]) / 2)
    scale = math.hypot(shoulder_mid[0] - hip_mid[0], shoulder_mid[1] - hip_mid[1]) + 1e-4

    raw: list[float] = []
    for name in _KEY_JOINTS:
        x, y, z = _pt(landmarks, name)
        raw.extend([(x - hip_mid[0]) / scale, (y - hip_mid[1]) / scale, z / scale])

    # Arm angles (right + left)
    for side in ("RIGHT", "LEFT"):
        sh = _pt(landmarks, f"{side}_SHOULDER")
        el = _pt(landmarks, f"{side}_ELBOW")
        wr = _pt(landmarks, f"{side}_WRIST")
        raw.append(_angle_cosine(sh, el, wr))

    # Torso lean (shoulder mid vs hip mid, z delta)
    raw.append((shoulder_mid[2] - hip_mid[2]) / scale)

    # Wrist height vs hips
    for side in ("RIGHT", "LEFT"):
        wr = _pt(landmarks, f"{side}_WRIST")
        raw.append((wr[1] - hip_mid[1]) / scale)

    while len(raw) < MESH_FEATURE_DIM:
        raw.append(0.0)
    return _l2_normalize(raw[:MESH_FEATURE_DIM])


def _mesh_confidence_from_landmarks(landmarks: dict) -> float:
    """Aggregate visibility / presence for mesh quality floor (server uses ≥ 0.4)."""
    vis_keys = (
        "LEFT_WRIST",
        "RIGHT_WRIST",
        "LEFT_SHOULDER",
        "RIGHT_SHOULDER",
        "LEFT_ELBOW",
        "RIGHT_ELBOW",
    )
    scores: list[float] = []
    for name in vis_keys:
        p = landmarks.get(name) or {}
        v = p.get("visibility")
        if isinstance(v, (int, float)):
            scores.append(float(v))
        elif "x" in p and "y" in p:
            scores.append(0.75)
    if not scores:
        return 0.5
    return sum(scores) / len(scores)


def _landmarks_3d_subset(landmarks: dict) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    for name in _KEY_JOINTS:
        x, y, z = _pt(landmarks, name)
        out[name] = {"x": round(x, 6), "y": round(y, 6), "z": round(z, 6)}
    return out


_sam3d_ready: bool | None = None


def _sam3d_available() -> bool:
    global _sam3d_ready
    if _sam3d_ready is not None:
        return _sam3d_ready
    if not _env_bool("SAM3D_ENABLED", False):
        _sam3d_ready = False
        return False
    try:
        from sam3d_inference import load_sam_estimator

        est, err = load_sam_estimator()
        _sam3d_ready = est is not None
        if err and not _sam3d_ready:
            print(f"[Mesh] SAM3D not available: {err}")
    except Exception as e:
        print(f"[Mesh] SAM3D check failed: {e}")
        _sam3d_ready = False
    return _sam3d_ready


def _run_sam3d_on_frame(rgb_frame, landmarks: dict) -> tuple[list[float], float, dict, bool]:
    """Returns (feature_vector, mesh_confidence, landmarks_3d, used_real_sam)."""
    used_sam = False
    if _sam3d_available():
        try:
            from sam3d_inference import infer_sam_landmarks

            sam_lm, sam_conf, err = infer_sam_landmarks(rgb_frame)
            if sam_lm and sam_conf >= 0.4:
                used_sam = True
                vec = mesh_proxy_feature_vector(sam_lm)
                return vec, sam_conf, _landmarks_3d_subset(sam_lm), used_sam
            if err:
                print(f"[Mesh] SAM inference fallback to proxy: {err}")
        except Exception as e:
            print(f"[Mesh] SAM inference error, using proxy: {e}")

    vec = mesh_proxy_feature_vector(landmarks)
    conf = _mesh_confidence_from_landmarks(landmarks)
    return vec, conf, _landmarks_3d_subset(landmarks), used_sam


def _contiguous_window(center: int, window: int, frame_count: int) -> list[int]:
    """`window` contiguous frame indices containing `center`, clamped to [0, frame_count-1]."""
    if frame_count <= 0:
        return []
    win = max(1, min(window, frame_count))
    half = win // 2
    start = center - half
    end = start + win - 1
    last = frame_count - 1
    if start < 0:
        end -= start
        start = 0
    if end > last:
        start -= end - last
        end = last
    start = max(0, start)
    return list(range(start, end + 1))


def pick_impact_candidate_frames(
    frame_count: int,
    yolo_rows: list[dict],
    explicit_indices: list[int] | None = None,
    window: int = 1,
) -> list[int]:
    """
    Impact window policy. `window` = how many frames to mesh-enrich (sequence matching
    wants several around impact, not one).

    - explicit_indices given: caller pre-selected the exact sampled frames (e.g. training
      passes the last N stride-sampled frames near contact) -> clamp/dedupe/limit to `window`.
    - else: YOLO ball∩racket contact center, else clip center, expanded to a contiguous
      `window`-frame band (inference has dense per-frame pose so contiguous works).
    """
    win = max(1, window)

    if explicit_indices:
        valid = sorted(
            {max(0, min(frame_count - 1, i)) for i in explicit_indices if isinstance(i, int)}
        )
        return valid[-win:] if win > 1 else valid[:5]

    if frame_count <= 0:
        return []

    ball_frames = {r["frame"] for r in yolo_rows if r.get("label") == "sports_ball"}
    racket_frames = {r["frame"] for r in yolo_rows if r.get("label") == "racket"}
    contact = sorted(ball_frames & racket_frames)
    center = contact[len(contact) // 2] if contact else frame_count // 2

    if win <= 1:
        if contact:
            return sorted({max(0, center - 1), center, min(frame_count - 1, center + 1)})
        return [center]

    return _contiguous_window(center, win, frame_count)


def enrich_impact_frames(
    video_path: str,
    frame_indices: list[int],
    pose_by_frame: dict[int, dict],
    *,
    trigger: str = "impact_always",
) -> dict[str, Any]:
    """
    Run mesh enrichment on selected frames. Reads video with OpenCV for SAM path;
    uses pose_by_frame landmarks for proxy path.
    """
    import cv2

    t0 = time.time()
    sam_loaded = _sam3d_available()
    any_real_sam = False
    frames_out: list[dict] = []

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return {
            "provider": "sam3d",
            "spec_version": MESH_SPEC_VERSION,
            "trigger": trigger,
            "sam_model_loaded": sam_loaded,
            "error": "video_open_failed",
            "frames": [],
            "latency_ms": 0,
        }

    index_set = set(frame_indices)
    frame_idx = 0
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
        if frame_idx in index_set:
            landmarks = pose_by_frame.get(frame_idx)
            if landmarks:
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                vec, conf, lm3d, used_sam = _run_sam3d_on_frame(rgb, landmarks)
                if used_sam:
                    any_real_sam = True
                frames_out.append(
                    {
                        "frame": frame_idx,
                        "mesh_confidence": round(conf, 6),
                        "feature_vector": [round(x, 8) for x in vec],
                        "landmarks_3d": lm3d,
                        "occluded_parts": [],
                        "inference": "sam3d" if used_sam else "mesh_proxy",
                    }
                )
        frame_idx += 1
    cap.release()

    latency_ms = int((time.time() - t0) * 1000)
    print(
        f"[Mesh] enrich_impact_frames frames={len(frames_out)} "
        f"sam_loaded={sam_loaded} latency_ms={latency_ms}"
    )

    return {
        "provider": "sam3d",
        "spec_version": MESH_SPEC_VERSION,
        "trigger": trigger,
        "sam_model_loaded": sam_loaded and any_real_sam,
        "sam_estimator_ready": sam_loaded,
        "frames": frames_out,
        "latency_ms": latency_ms,
    }
