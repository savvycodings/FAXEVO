import modal
import os
import sys
from pydantic import BaseModel, Field
from typing import Literal, Optional

if "/root" not in sys.path:
    sys.path.insert(0, "/root")

from sam_mesh import enrich_impact_frames, pick_impact_candidate_frames

# Define image with dependencies (local files last with copy=True for sam3d_image extension)
image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install(
        "libgl1",
        "libglib2.0-0",
        "libsm6",
        "libxext6",
        "libxrender1",
        "libgomp1",
    )
    .pip_install("fastapi[standard]")
    .pip_install("mediapipe==0.10.14")
    .pip_install("ultralytics")
    .pip_install("opencv-python-headless")
    .pip_install("numpy")
    .pip_install("requests")
    # Inference parity config (set in code, not secrets). The Modal secret can still override
    # at runtime; sensitive keys (HF_TOKEN, SAM3D_ENABLED) stay in the secret.
    .env(
        {
            "POSE_MODEL_COMPLEXITY": "1",
            "MESH_ENRICHMENT_ENABLED": "1",
            "MESH_IMPACT_WINDOW": "10",
            "YOLO_DETECTION_ENABLED": "1",
        }
    )
    .add_local_file("sam_mesh.py", "/root/sam_mesh.py", copy=True)
    .add_local_file("sam3d_inference.py", "/root/sam3d_inference.py", copy=True)
)

# Heavy image for real SAM 3D Body (facebook/sam-3d-body-dinov3). Deploy with analyzer_image = sam3d_image.
# Secret: SAM3D_ENABLED=1, HF_TOKEN=<gated HF access>, optional SAM3D_HF_REPO=facebook/sam-3d-body-dinov3
sam3d_image = (
    image.pip_install(
        "torch",
        "torchvision",
        "huggingface_hub",
        "einops",
        "timm",
        "yacs",
        "roma",
        "fvcore",
        "hydra-core",
        "omegaconf",
        "pytorch-lightning",
        "scikit-image",
        "pandas",
        "rich",
        "loguru",
    )
    .apt_install("git", "build-essential")
    .run_commands(
        "git clone --depth 1 https://github.com/facebookresearch/sam-3d-body /opt/sam-3d-body",
        "pip install -e /opt/sam-3d-body",
        "pip install 'git+https://github.com/facebookresearch/detectron2.git@a1ce2f9' --no-build-isolation --no-deps || true",
        "pip install 'git+https://github.com/microsoft/MoGe.git' || true",
    )
    .env({"PYTHONPATH": "/opt/sam-3d-body", "SAM3D_REPO_PATH": "/opt/sam-3d-body"})
)

# Production default: real SAM 3D Body image (heavy). The SAM model only actually loads at
# runtime when the Modal secret has SAM3D_ENABLED=1 + HF_TOKEN with gated access; otherwise
# sam_mesh.py safely falls back to the MediaPipe mesh proxy. Set ANALYZER_USE_SAM3D_IMAGE=0
# at deploy time to build the lighter image (no torch/detectron2) for local/dev.
_USE_SAM3D_IMAGE = str(os.getenv("ANALYZER_USE_SAM3D_IMAGE", "1")).strip().lower() not in (
    "0",
    "false",
    "no",
    "off",
)
analyzer_image = sam3d_image if _USE_SAM3D_IMAGE else image

# A10G (or better) is required for real SAM 3D Body; "any" is fine for the proxy-only image.
ANALYZER_GPU = os.getenv("ANALYZER_GPU", "A10G" if _USE_SAM3D_IMAGE else "any").strip() or "any"

app = modal.App("padel-analyzer")

# `modal secret create xevo-analyzer-env YOLO_DETECTION_CONFIDENCE=0.08 SAM3D_ENABLED=1 HF_TOKEN=...`
ANALYZER_MODAL_SECRET_NAME = "xevo-analyzer-env"

AllowedModels = Literal["mediapipe"]
DEFAULT_MODEL = "mediapipe"


class AnalyzeRequest(BaseModel):
    video_url: str
    analysis_id: str
    model: AllowedModels = Field(default=DEFAULT_MODEL)
    """Optional impact frames for mesh enrichment (server can pass after YOLO resolve)."""
    impact_frame_indices: Optional[list[int]] = None


def _env_bool(name: str, default: bool = False) -> bool:
    value = str(os.getenv(name, "")).strip().lower()
    if not value:
        return default
    return value in ("1", "true", "yes", "on")


def _env_float(name: str, default: float) -> float:
    raw = str(os.getenv(name, "")).strip()
    if not raw:
        return default
    try:
        out = float(raw)
    except Exception:
        return default
    if out < 0:
        return 0.0
    if out > 1:
        return 1.0
    return out


def _env_int(name: str, default: int, min_v: int, max_v: int) -> int:
    raw = str(os.getenv(name, "")).strip()
    if not raw:
        return default
    try:
        out = int(raw)
    except Exception:
        return default
    return max(min_v, min(max_v, out))


def _bbox_iou(a, b):
    ax1, ay1, aw, ah = a
    bx1, by1, bw, bh = b
    ax2, ay2 = ax1 + aw, ay1 + ah
    bx2, by2 = bx1 + bw, by1 + bh
    inter_x1 = max(ax1, bx1)
    inter_y1 = max(ay1, by1)
    inter_x2 = min(ax2, bx2)
    inter_y2 = min(ay2, by2)
    if inter_x2 <= inter_x1 or inter_y2 <= inter_y1:
        return 0.0
    inter = (inter_x2 - inter_x1) * (inter_y2 - inter_y1)
    union = aw * ah + bw * bh - inter
    if union <= 0:
        return 0.0
    return float(inter / union)


def _assign_track_id(label, bbox_norm, prev_tracks, next_track_num):
    best_id = None
    best_iou = 0.0
    for tid, prev in prev_tracks.items():
        if prev["label"] != label:
            continue
        iou = _bbox_iou(bbox_norm, prev["bbox"])
        if iou > best_iou:
            best_iou = iou
            best_id = tid
    if best_id and best_iou >= 0.2:
        prev_tracks[best_id] = {"label": label, "bbox": bbox_norm}
        return best_id, next_track_num
    tid = f"{label[:2]}_{next_track_num}"
    prev_tracks[tid] = {"label": label, "bbox": bbox_norm}
    return tid, next_track_num + 1


def _maybe_load_yolo():
    enabled = _env_bool("YOLO_DETECTION_ENABLED", True)
    if not enabled:
        return None, False
    try:
        from ultralytics import YOLO

        model = YOLO("yolov8n.pt")
        print("[PadelAnalyzer] YOLOv8n loaded")
        return model, True
    except Exception as e:
        print(f"[PadelAnalyzer] YOLO load failed, continuing without detections: {e}")
        return None, False


def _run_yolo_on_frame(
    yolo_model,
    frame,
    frame_idx: int,
    *,
    yolo_conf_thres: float,
    yolo_racket_conf_thres: float,
    yolo_ball_conf_thres: float,
    yolo_iou_thres: float,
    yolo_imgsz: int,
    yolo_logs: bool,
    prev_tracks: dict,
    next_track_num: int,
    stats: dict,
):
    """COCO cls 32=sports ball, 38=tennis racket (used as padel racket proxy)."""
    rows = []
    try:
        infer = yolo_model(
            frame,
            verbose=False,
            classes=[32, 38],
            conf=min(yolo_conf_thres, yolo_racket_conf_thres, yolo_ball_conf_thres),
            iou=yolo_iou_thres,
            imgsz=yolo_imgsz,
            max_det=24,
        )
    except Exception as e:
        if yolo_logs:
            print(f"[PadelAnalyzer][YOLO] inference failed at frame {frame_idx}: {e}")
        return rows, prev_tracks, next_track_num

    if not infer:
        return rows, prev_tracks, next_track_num

    item = infer[0]
    boxes = getattr(item, "boxes", None)
    if boxes is None or getattr(boxes, "xyxy", None) is None:
        return rows, prev_tracks, next_track_num

    h, w = frame.shape[:2]
    frame_had_raw = False
    frame_raw_racket = 0
    frame_acc_racket = 0

    for idx in range(len(boxes.xyxy)):
        cls_id = int(boxes.cls[idx].item())
        if cls_id not in (32, 38):
            continue
        frame_had_raw = True
        stats["raw_detected_frames"].add(frame_idx)
        if cls_id == 32:
            stats["raw_ball_candidates"] += 1
        else:
            stats["raw_racket_candidates"] += 1
            frame_raw_racket += 1

        conf = float(boxes.conf[idx].item())
        class_conf_thres = yolo_ball_conf_thres if cls_id == 32 else yolo_racket_conf_thres
        if conf < class_conf_thres:
            continue

        x1, y1, x2, y2 = boxes.xyxy[idx].tolist()
        bw = max(0.0, float(x2 - x1))
        bh = max(0.0, float(y2 - y1))
        if bw <= 0 or bh <= 0 or w <= 0 or h <= 0:
            continue

        nx = max(0.0, min(1.0, float(x1 / w)))
        ny = max(0.0, min(1.0, float(y1 / h)))
        nw = max(0.0, min(1.0, float(bw / w)))
        nh = max(0.0, min(1.0, float(bh / h)))
        label = "sports_ball" if cls_id == 32 else "racket"
        track_id, next_track_num = _assign_track_id(
            label, (nx, ny, nw, nh), prev_tracks, next_track_num
        )
        rows.append(
            {
                "frame": frame_idx,
                "label": label,
                "confidence": round(conf, 6),
                "bbox": {"x": round(nx, 6), "y": round(ny, 6), "w": round(nw, 6), "h": round(nh, 6)},
                "track_id": track_id,
            }
        )
        stats["det_frame_set"].add(frame_idx)
        stats["conf_sum"] += conf
        stats["conf_n"] += 1
        if label == "sports_ball":
            stats["ball_count"] += 1
            stats["accepted_ball"] += 1
        else:
            stats["racket_count"] += 1
            stats["accepted_racket"] += 1
            frame_acc_racket += 1

    if yolo_logs and frame_had_raw:
        print(
            f"[PadelAnalyzer][YOLO] frame={frame_idx} raw_racket={frame_raw_racket} accepted_racket={frame_acc_racket}"
        )

    return rows, prev_tracks, next_track_num


@app.function(
    image=analyzer_image,
    gpu=ANALYZER_GPU,  # A10G+ for real SAM 3D Body; "any" for proxy-only image
    timeout=900,
    secrets=[modal.Secret.from_name(ANALYZER_MODAL_SECRET_NAME)],
)
@modal.fastapi_endpoint(method="POST")
def analyze_video(req: AnalyzeRequest):
    print(f"=== Starting analysis for {req.analysis_id} ===")
    print(
        f"Request data: video_url={req.video_url}, analysis_id={req.analysis_id}, model={req.model}"
    )

    if not req.video_url or not req.analysis_id:
        return {"status": "error", "message": "Missing video_url or analysis_id"}

    try:
        print("Step 1: Downloading video...")
        import tempfile as tf
        import requests as dl
        import cv2

        with tf.NamedTemporaryFile(delete=False, suffix=".mp4") as tmp_video:
            download_response = dl.get(req.video_url, stream=True, timeout=60)
            if download_response.status_code != 200:
                return {
                    "status": "error",
                    "message": f"Failed to download video: {download_response.status_code}",
                }

            for chunk in download_response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    tmp_video.write(chunk)
            video_path = tmp_video.name
            print(f"Video downloaded to {video_path}")

        print("Step 2: Running MediaPipe + YOLO (every frame)...")
        metrics = run_video_analysis(
            video_path,
            impact_frame_indices=req.impact_frame_indices,
        )

        try:
            os.remove(video_path)
        except Exception:
            pass

        return {
            "status": "success",
            "analysis_id": req.analysis_id,
            "metrics": metrics,
        }

    except Exception as e:
        print(f"Error: {e}")
        import traceback

        traceback.print_exc()
        return {"status": "error", "message": str(e)}


def _best_person_box_px(yolo_model, frame, imgsz):
    """Largest, most-central COCO 'person' (cls 0) box in pixels, or None.

    MediaPipe pose is unreliable when the player is small in the frame (its left/right
    landmark assignment flips between runs). Cropping to the player before pose estimation
    gives a large, stable figure. Returns (x1, y1, x2, y2) in pixel coordinates.
    """
    try:
        res = yolo_model(
            frame,
            verbose=False,
            classes=[0],
            conf=_env_float("PLAYER_CROP_CONF", 0.25),
            iou=0.5,
            imgsz=imgsz,
            max_det=8,
        )
    except Exception:
        return None
    if not res:
        return None
    boxes = getattr(res[0], "boxes", None)
    if boxes is None or getattr(boxes, "xyxy", None) is None or len(boxes.xyxy) == 0:
        return None
    h, w = frame.shape[:2]
    cxf, cyf = w / 2.0, h / 2.0
    best = None
    best_score = -1.0
    for i in range(len(boxes.xyxy)):
        if int(boxes.cls[i].item()) != 0:
            continue
        x1, y1, x2, y2 = (float(v) for v in boxes.xyxy[i].tolist())
        area = max(0.0, x2 - x1) * max(0.0, y2 - y1)
        if area <= 0:
            continue
        bx, by = (x1 + x2) / 2.0, (y1 + y2) / 2.0
        dist2 = ((bx - cxf) / w) ** 2 + ((by - cyf) / h) ** 2
        # Prefer the big, central player (closest to camera) over background people.
        score = area * (1.0 - 0.3 * dist2)
        if score > best_score:
            best_score = score
            best = (x1, y1, x2, y2)
    return best


def _square_padded_box(box, w, h, pad):
    """Expand a person box to a padded square, clamped to the frame (keeps aspect for pose)."""
    x1, y1, x2, y2 = box
    bw, bh = x2 - x1, y2 - y1
    cx, cy = (x1 + x2) / 2.0, (y1 + y2) / 2.0
    side = max(bw, bh) * (1.0 + 2.0 * pad)
    half = side / 2.0
    nx1 = max(0, int(round(cx - half)))
    ny1 = max(0, int(round(cy - half)))
    nx2 = min(int(w), int(round(cx + half)))
    ny2 = min(int(h), int(round(cy + half)))
    return nx1, ny1, nx2, ny2


def run_video_analysis(video_path, impact_frame_indices=None):
    """MediaPipe pose + YOLO ball/racket on every frame; optional impact-frame mesh enrichment."""
    import cv2
    import mediapipe as mp

    mesh_enabled = _env_bool("MESH_ENRICHMENT_ENABLED", True)
    player_crop_enabled = _env_bool("PLAYER_CROP_ENABLED", True)
    player_crop_pad = _env_float("PLAYER_CROP_PAD", 0.25)
    player_crop_ema = _env_float("PLAYER_CROP_EMA", 0.5)

    mp_pose = mp.solutions.pose
    mp_pose_obj = mp_pose.Pose(
        # When cropping to the player each frame, run per-frame detection (no video tracking)
        # so a shifting crop can't drag the tracker; otherwise keep temporal tracking.
        static_image_mode=player_crop_enabled,
        # model_complexity must match train_modal_app.py (=1) so query and library
        # landmarks come from the same estimator (sequence-ensemble parity).
        model_complexity=_env_int("POSE_MODEL_COMPLEXITY", 1, 0, 2),
        enable_segmentation=False,
        min_detection_confidence=0.5,
    )

    yolo_model, yolo_enabled = _maybe_load_yolo()
    crop_ema_box = None  # EMA-smoothed player crop box (pixels) across frames
    yolo_conf_thres = _env_float("YOLO_DETECTION_CONFIDENCE", 0.08)
    yolo_racket_conf_thres = _env_float("YOLO_RACKET_CONFIDENCE", 0.01)
    yolo_ball_conf_thres = _env_float("YOLO_BALL_CONFIDENCE", 0.10)
    yolo_iou_thres = _env_float("YOLO_DETECTION_IOU", 0.70)
    yolo_imgsz = _env_int("YOLO_DETECTION_IMGSZ", 1280, 320, 1600)
    yolo_logs = _env_bool("YOLO_DETECTION_LOGS", True)

    print(
        f"[PadelAnalyzer] YOLO enabled={yolo_enabled} conf={yolo_conf_thres} "
        f"racket={yolo_racket_conf_thres} ball={yolo_ball_conf_thres} imgsz={yolo_imgsz}"
    )

    cap = cv2.VideoCapture(video_path)
    frames_data = []
    yolo_rows = []
    frame_count = 0
    prev_tracks = {}
    next_track_num = 1
    yolo_stats = {
        "raw_detected_frames": set(),
        "det_frame_set": set(),
        "ball_count": 0,
        "racket_count": 0,
        "raw_ball_candidates": 0,
        "raw_racket_candidates": 0,
        "accepted_ball": 0,
        "accepted_racket": 0,
        "conf_sum": 0.0,
        "conf_n": 0,
    }

    print("Processing frames...")
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        frame_h, frame_w = frame.shape[:2]

        # Crop to the player (large, stable figure) before pose estimation when enabled.
        crop_box = None
        if player_crop_enabled and yolo_enabled and yolo_model is not None and frame_w > 0:
            pbox = _best_person_box_px(yolo_model, frame, yolo_imgsz)
            if pbox is not None:
                raw = _square_padded_box(pbox, frame_w, frame_h, player_crop_pad)
                if crop_ema_box is None:
                    crop_ema_box = list(map(float, raw))
                else:
                    a = player_crop_ema
                    crop_ema_box = [
                        prev * (1.0 - a) + cur * a
                        for prev, cur in zip(crop_ema_box, raw)
                    ]
                crop_box = tuple(int(round(v)) for v in crop_ema_box)
            elif crop_ema_box is not None:
                crop_box = tuple(int(round(v)) for v in crop_ema_box)

        x_off, y_off, crop_w, crop_h, z_scale = 0, 0, frame_w, frame_h, 1.0
        if crop_box is not None:
            cx0, cy0, cx1, cy1 = crop_box
            if cx1 - cx0 >= 16 and cy1 - cy0 >= 16:
                sub = frame[cy0:cy1, cx0:cx1]
                rgb_frame = cv2.cvtColor(sub, cv2.COLOR_BGR2RGB)
                x_off, y_off, crop_w, crop_h = cx0, cy0, cx1 - cx0, cy1 - cy0
                z_scale = crop_w / float(frame_w) if frame_w else 1.0
            else:
                crop_box = None
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        else:
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        results = mp_pose_obj.process(rgb_frame)

        if results.pose_landmarks:
            landmarks = {}
            for idx, lm in enumerate(results.pose_landmarks.landmark):
                name = mp_pose.PoseLandmark(idx).name
                # Map crop-normalized coords back to full-frame normalized coords.
                fx = (x_off + lm.x * crop_w) / frame_w if frame_w else lm.x
                fy = (y_off + lm.y * crop_h) / frame_h if frame_h else lm.y
                landmarks[name] = {
                    "x": fx,
                    "y": fy,
                    "z": lm.z * z_scale,
                    "visibility": lm.visibility,
                }
            frames_data.append({"frame": frame_count, "landmarks": landmarks})

        if yolo_enabled and yolo_model is not None:
            new_rows, prev_tracks, next_track_num = _run_yolo_on_frame(
                yolo_model,
                frame,
                frame_count,
                yolo_conf_thres=yolo_conf_thres,
                yolo_racket_conf_thres=yolo_racket_conf_thres,
                yolo_ball_conf_thres=yolo_ball_conf_thres,
                yolo_iou_thres=yolo_iou_thres,
                yolo_imgsz=yolo_imgsz,
                yolo_logs=yolo_logs,
                prev_tracks=prev_tracks,
                next_track_num=next_track_num,
                stats=yolo_stats,
            )
            yolo_rows.extend(new_rows)

        frame_count += 1

    cap.release()
    mp_pose_obj.close()

    yolo_summary = {
        "enabled": bool(yolo_enabled),
        "model": "yolov8n",
        "sampled_frames": frame_count,
        "detected_frames": len(yolo_stats["det_frame_set"]),
        "sports_ball_count": yolo_stats["ball_count"],
        "racket_count": yolo_stats["racket_count"],
        "raw_detected_frames": len(yolo_stats["raw_detected_frames"]),
        "raw_ball_candidates": yolo_stats["raw_ball_candidates"],
        "raw_racket_candidates": yolo_stats["raw_racket_candidates"],
        "accepted_ball_candidates": yolo_stats["accepted_ball"],
        "accepted_racket_candidates": yolo_stats["accepted_racket"],
        "avg_confidence": round(yolo_stats["conf_sum"] / yolo_stats["conf_n"], 6)
        if yolo_stats["conf_n"]
        else 0.0,
        "confidence_threshold": yolo_conf_thres,
        "confidence_threshold_racket": yolo_racket_conf_thres,
        "confidence_threshold_ball": yolo_ball_conf_thres,
        "iou_threshold": yolo_iou_thres,
        "imgsz": yolo_imgsz,
    }

    print(
        f"MediaPipe complete: {frame_count} frames, {len(frames_data)} pose rows; "
        f"YOLO: {len(yolo_rows)} detections on {yolo_summary['detected_frames']} frames"
    )

    pose_by_frame = {row["frame"]: row["landmarks"] for row in frames_data}
    pose_enrichment = None
    if mesh_enabled and frame_count > 0 and pose_by_frame:
        candidates = pick_impact_candidate_frames(
            frame_count,
            yolo_rows,
            explicit_indices=impact_frame_indices,
            window=_env_int("MESH_IMPACT_WINDOW", 10, 1, 60),
        )
        pose_enrichment = enrich_impact_frames(
            video_path,
            candidates,
            pose_by_frame,
            trigger="impact_always" if not impact_frame_indices else "explicit_indices",
        )

    out = {
        "total_frames": frame_count,
        "analyzed_frames": len(frames_data),
        "pose_data": frames_data,
        "yolo_detections": yolo_rows[:5000],
        "yolo_summary": yolo_summary,
    }
    if pose_enrichment is not None:
        out["pose_enrichment"] = pose_enrichment
    return out
