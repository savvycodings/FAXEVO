"""
Optional SAM 3D Body inference for impact-frame mesh enrichment.

Requires Modal image with /opt/sam-3d-body on PYTHONPATH, PyTorch, HF_TOKEN for gated
checkpoints (facebook/sam-3d-body-dinov3). See modal_app.py `sam3d_image` and INSTALL.md:
https://github.com/facebookresearch/sam-3d-body
"""

from __future__ import annotations

import os
import sys
import tempfile
from typing import Any

# MHR70 keypoint indices (facebook/sam-3d-body, sam_3d_body.metadata.mhr70).
# IMPORTANT: MHR70 is NOT COCO ordering. Body chain is shoulders(5,6) -> elbows(7,8) ->
# hips(9,10) -> knees(11,12) -> ankles(13,14); the WRISTS are the hand-root joints
# (left=62, right=41), confirmed via the SAM3D skeleton edges (arm edge 7->62, 8->41 and
# hand fans anchored at 62/41). The previous COCO-style mapping put wrists onto the hips,
# which corrupted every mesh feature. Override with SAM3D_MHR_JOINT_MAP (JSON) if a future
# checkpoint changes the ordering.
_MHR_TO_MP_DEFAULT = {
    "LEFT_SHOULDER": 5,
    "RIGHT_SHOULDER": 6,
    "LEFT_ELBOW": 7,
    "RIGHT_ELBOW": 8,
    "LEFT_WRIST": 62,
    "RIGHT_WRIST": 41,
    "LEFT_HIP": 9,
    "RIGHT_HIP": 10,
    "LEFT_KNEE": 11,
    "RIGHT_KNEE": 12,
}


def _load_joint_map() -> dict:
    raw = (os.getenv("SAM3D_MHR_JOINT_MAP") or "").strip()
    if not raw:
        return dict(_MHR_TO_MP_DEFAULT)
    try:
        import json

        parsed = json.loads(raw)
        out = {}
        for name, idx in parsed.items():
            if isinstance(name, str) and isinstance(idx, int) and idx >= 0:
                out[name] = idx
        return out or dict(_MHR_TO_MP_DEFAULT)
    except Exception as e:
        print(f"[SAM3D] SAM3D_MHR_JOINT_MAP parse failed, using default mapping: {e}")
        return dict(_MHR_TO_MP_DEFAULT)


_MHR_TO_MP = _load_joint_map()

_sam_estimator: Any = None
_sam_load_error: str | None = None


def _env_bool(name: str, default: bool = False) -> bool:
    value = str(os.getenv(name, "")).strip().lower()
    if not value:
        return default
    return value in ("1", "true", "yes", "on")


def _ensure_sam_path() -> None:
    for p in ("/opt/sam-3d-body", os.getenv("SAM3D_REPO_PATH", "")):
        if p and os.path.isdir(p) and p not in sys.path:
            sys.path.insert(0, p)


def load_sam_estimator():
    """Lazy-load SAM3DBodyEstimator; returns (estimator, error_message)."""
    global _sam_estimator, _sam_load_error
    if _sam_estimator is not None:
        return _sam_estimator, None
    if _sam_load_error:
        return None, _sam_load_error
    if not _env_bool("SAM3D_ENABLED", False):
        return None, "SAM3D_ENABLED off"

    hf_token = (os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACE_HUB_TOKEN") or "").strip()
    if hf_token:
        os.environ["HF_TOKEN"] = hf_token
        os.environ["HUGGINGFACE_HUB_TOKEN"] = hf_token

    _ensure_sam_path()
    try:
        from sam_3d_body import load_sam_3d_body_hf, SAM3DBodyEstimator
        from tools.build_detector import HumanDetector
        from tools.build_fov_estimator import FOVEstimator
    except ImportError as e:
        _sam_load_error = f"sam_3d_body import failed: {e}"
        print(f"[SAM3D] {_sam_load_error}")
        return None, _sam_load_error

    repo_id = (os.getenv("SAM3D_HF_REPO") or "facebook/sam-3d-body-dinov3").strip()
    device = "cuda" if _env_bool("SAM3D_FORCE_CPU", False) is False else "cpu"
    try:
        import torch

        if device == "cuda" and not torch.cuda.is_available():
            device = "cpu"
        print(f"[SAM3D] Loading {repo_id} on {device}...")
        model, model_cfg = load_sam_3d_body_hf(repo_id, device=device)
        human_detector = HumanDetector(name="vitdet", device=device)
        fov_estimator = FOVEstimator(name="moge2", device=device)
        _sam_estimator = SAM3DBodyEstimator(
            sam_3d_body_model=model,
            model_cfg=model_cfg,
            human_detector=human_detector,
            human_segmentor=None,
            fov_estimator=fov_estimator,
        )
        print("[SAM3D] Estimator ready")
        return _sam_estimator, None
    except Exception as e:
        _sam_load_error = str(e)
        print(f"[SAM3D] Load failed: {e}")
        return None, _sam_load_error


def _keypoints_to_landmarks(keypoints_2d, img_w: int, img_h: int) -> dict:
    """Map MHR70 2D keypoints to MediaPipe-like normalized landmark dict."""
    landmarks: dict = {}
    if keypoints_2d is None:
        return landmarks
    try:
        import numpy as np

        kps = np.asarray(keypoints_2d)
    except Exception:
        return landmarks
    if kps.ndim != 2 or kps.shape[1] < 2:
        return landmarks
    w = max(float(img_w), 1.0)
    h = max(float(img_h), 1.0)
    for name, idx in _MHR_TO_MP.items():
        if idx >= len(kps):
            continue
        x, y = float(kps[idx, 0]), float(kps[idx, 1])
        # Normalize: SAM keypoints are typically pixel coords
        nx = x / w if x > 1.0 or y > 1.0 else x
        ny = y / h if x > 1.0 or y > 1.0 else y
        z = float(kps[idx, 2]) if kps.shape[1] > 2 else 0.0
        landmarks[name] = {
            "x": max(0.0, min(1.0, nx)),
            "y": max(0.0, min(1.0, ny)),
            "z": z,
            "visibility": 0.9,
        }
    return landmarks


def infer_sam_landmarks(rgb_frame) -> tuple[dict | None, float, str | None]:
    """
    Run SAM 3D Body on one RGB frame (H,W,3).
    Returns (landmarks_dict, confidence, error).
    """
    estimator, err = load_sam_estimator()
    if estimator is None:
        return None, 0.0, err

    import cv2

    h, w = rgb_frame.shape[:2]
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
        path = tmp.name
        cv2.imwrite(path, cv2.cvtColor(rgb_frame, cv2.COLOR_RGB2BGR))

    try:
        outputs = estimator.process_one_image(path)
    except Exception as e:
        return None, 0.0, str(e)
    finally:
        try:
            os.remove(path)
        except OSError:
            pass

    if not outputs:
        return None, 0.0, "no_person_detected"

    person = outputs[0]
    kps = person.get("pred_keypoints_2d") or person.get("pred_keypoints_3d")
    landmarks = _keypoints_to_landmarks(kps, w, h)
    if not landmarks:
        return None, 0.0, "no_keypoints"

    conf_raw = person.get("confidence")
    if isinstance(conf_raw, (int, float)):
        conf = float(conf_raw)
    else:
        conf = 0.85
    return landmarks, min(1.0, max(0.0, conf)), None
