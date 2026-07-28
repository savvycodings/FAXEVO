import modal
import requests
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone
import json
import os
import sys

if "/root" not in sys.path:
    sys.path.insert(0, "/root")

from sam_mesh import enrich_impact_frames

# Define image with dependencies
image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install(
        "libgl1",
        "libglib2.0-0",
        "libsm6",
        "libxext6",
        "libxrender1",
        "libgomp1"
    )
    .pip_install("fastapi[standard]")
    .pip_install("mediapipe==0.10.14")
    .pip_install("ultralytics")
    .pip_install("opencv-python-headless")
    .pip_install("numpy")
    .pip_install("requests")
    .pip_install("psycopg[binary]")
    .pip_install("openai")
    # Training extraction parity config (set in code, not secrets). The Modal secret can still
    # override any of these at runtime; sensitive keys (DATABASE_URL, OPENAI_API_KEY, HF_TOKEN,
    # SAM3D_ENABLED) stay in the secret.
    .env(
        {
            "TRAIN_POSE_STRIDE": "1",
            "TRAIN_INDEX_WINDOW": "40",
            "YOLO_DETECTION_ENABLED": "1",
            "MESH_ENRICHMENT_ENABLED": "1",
            "YOLO_DETECTION_CONFIDENCE": "0.08",
            "YOLO_RACKET_CONFIDENCE": "0.01",
            "YOLO_BALL_CONFIDENCE": "0.10",
            "YOLO_DETECTION_IOU": "0.70",
            "YOLO_DETECTION_IMGSZ": "1280",
        }
    )
    .add_local_file("sam_mesh.py", "/root/sam_mesh.py", copy=True)
    .add_local_file("sam3d_inference.py", "/root/sam3d_inference.py", copy=True)
)

app = modal.App("padel-trainset")
TRAIN_MODAL_SECRET_NAME = "xevo-train-env"


class ProcessRequest(BaseModel):
    video_url: str
    sample_id: str
    movement_label: str
    # Optional if caller already knows which train_video row this sample belongs to
    train_video_id: Optional[str] = None


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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
    # Enabled by default so training detects ball/racket contact the same way inference does.
    enabled = _env_bool("YOLO_DETECTION_ENABLED", True)
    if not enabled:
        return None, False
    try:
        from ultralytics import YOLO

        model = YOLO("yolov8n.pt")
        print("[TrainModal] YOLOv8n loaded")
        return model, True
    except Exception as e:
        print(f"[TrainModal] YOLO load failed, continuing without detections: {e}")
        return None, False


def _best_person_box_px(yolo_model, frame, imgsz):
    """Largest, most-central COCO 'person' (cls 0) box in pixels, or None.

    Must mirror modal_app.py so library and query landmarks are extracted identically:
    cropping to the player yields a large, stable figure (MediaPipe left/right assignment is
    unreliable on small figures). Returns (x1, y1, x2, y2) in pixels.
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


def _update_status(
    conn,
    sample_id: str,
    *,
    status: str,
    error_message: Optional[str] = None,
    frame_count: Optional[int] = None,
    total_frames: Optional[int] = None,
    pose_sequence: Optional[list] = None,
    extraction_meta: Optional[dict] = None,
    movement_label: Optional[str] = None,
):
    """
    Writes processing state into Neon.
    Expected schema (from planned Drizzle model):
      train_sample(
        id text pk,
        status text,
        "errorMessage" text,
        "frameCount" int,
        "totalFrames" int,
        "poseSequence" jsonb,
        "extractionMeta" jsonb,
        "strokeNameSnapshot" text,
        "updatedAt" timestamptz
      )
    """
    assignments = ['status = %s', '"updatedAt" = NOW()']
    values = [status]

    if error_message is not None:
        assignments.append('"errorMessage" = %s')
        values.append(error_message)
    if frame_count is not None:
        assignments.append('"frameCount" = %s')
        values.append(frame_count)
    if total_frames is not None:
        assignments.append('"totalFrames" = %s')
        values.append(total_frames)
    if pose_sequence is not None:
        assignments.append('"poseSequence" = %s::jsonb')
        values.append(json.dumps(pose_sequence))
    if extraction_meta is not None:
        assignments.append('"extractionMeta" = %s::jsonb')
        values.append(json.dumps(extraction_meta))
    if movement_label is not None:
        assignments.append('"strokeNameSnapshot" = %s')
        values.append(movement_label)

    values.append(sample_id)

    sql = f"""
        UPDATE train_sample
        SET {", ".join(assignments)}
        WHERE id = %s
    """
    with conn.cursor() as cur:
        cur.execute(sql, values)


def _normalize_label_with_openai(movement_label: str) -> Optional[dict]:
    """
    Optional helper for cleaner training metadata.
    If OPENAI_API_KEY is absent or request fails, returns None.
    """
    import os

    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key:
        return None

    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        prompt = (
            "Normalize this padel stroke label for training dataset use. "
            "Return strict JSON with keys: canonical_stroke, stroke_family, aliases, confidence. "
            f"Input label: {movement_label}"
        )
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0,
        )
        content = resp.choices[0].message.content
        if not content:
            return None
        parsed = json.loads(content)
        if isinstance(parsed, dict):
            return parsed
    except Exception as e:
        print(f"[TrainModal] OpenAI normalization failed: {e}")

    return None


@app.function(
    image=image,
    gpu="any",
    timeout=600,
    secrets=[modal.Secret.from_name(TRAIN_MODAL_SECRET_NAME)],
)
@modal.fastapi_endpoint(method="POST")
def process_video(req: ProcessRequest):
    """Extract MediaPipe pose landmarks and save labeled training data into Neon."""
    print(f"=== Starting processing for sample {req.sample_id} | label: {req.movement_label} ===")

    if not req.video_url or not req.sample_id or not req.movement_label:
        return {"status": "error", "message": "Missing video_url, sample_id, or movement_label"}

    import os
    database_url = (os.getenv("DATABASE_URL") or "").strip()
    if not database_url:
        return {"status": "error", "message": "DATABASE_URL is not set in Modal environment"}

    try:
        import psycopg
        conn = psycopg.connect(database_url)
        conn.autocommit = False
    except Exception as e:
        return {"status": "error", "message": f"Failed to connect to Neon: {e}"}

    try:
        # Step 1: Update status in Neon
        print("Step 1: Updating status to 'processing' in Neon...")
        _update_status(
            conn,
            req.sample_id,
            status="processing",
            error_message=None,
            movement_label=req.movement_label.strip(),
        )
        conn.commit()

        # Step 2: Download video
        print("Step 2: Downloading video...")
        import tempfile as tf
        import cv2

        with tf.NamedTemporaryFile(delete=False, suffix=".mp4") as tmp_video:
            download_response = requests.get(req.video_url, stream=True, timeout=60)
            if download_response.status_code != 200:
                return {"status": "error", "message": f"Failed to download video: {download_response.status_code}"}
            for chunk in download_response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    tmp_video.write(chunk)
            video_path = tmp_video.name
            print(f"Video downloaded to {video_path}")

        # Step 3: Run MediaPipe pose extraction
        print("Step 3: Running MediaPipe pose extraction...")
        import mediapipe as mp
        mp_pose = mp.solutions.pose

        player_crop_enabled = _env_bool("PLAYER_CROP_ENABLED", True)
        player_crop_pad = _env_float("PLAYER_CROP_PAD", 0.25)
        player_crop_ema = _env_float("PLAYER_CROP_EMA", 0.5)

        mp_pose_obj = mp_pose.Pose(
            # Per-frame detection when cropping (mirrors modal_app.py) so a shifting crop
            # cannot drag MediaPipe's video tracker.
            static_image_mode=player_crop_enabled,
            model_complexity=1,
            enable_segmentation=False,
            min_detection_confidence=0.5
        )

        cap = cv2.VideoCapture(video_path)
        pose_sequence = []
        total_frames = 0
        sampled_frame_count = 0
        crop_ema_box = None
        yolo_model, yolo_enabled = _maybe_load_yolo()
        # Defaults aligned with modal_app.py inference so "contact" is detected identically.
        yolo_conf_thres = _env_float("YOLO_DETECTION_CONFIDENCE", 0.08)
        yolo_racket_conf_thres = _env_float("YOLO_RACKET_CONFIDENCE", 0.01)
        yolo_ball_conf_thres = _env_float("YOLO_BALL_CONFIDENCE", 0.10)
        yolo_iou_thres = _env_float("YOLO_DETECTION_IOU", 0.70)
        yolo_imgsz = _env_int("YOLO_DETECTION_IMGSZ", 1280, 320, 1600)
        # Stride 1 = every frame (parity with inference). Configurable for cost control.
        pose_stride = _env_int("TRAIN_POSE_STRIDE", 1, 1, 30)
        yolo_logs = _env_bool("YOLO_DETECTION_LOGS", False)
        yolo_rows = []
        yolo_det_frame_set = set()
        yolo_ball_count = 0
        yolo_racket_count = 0
        yolo_raw_detected_frames = set()
        yolo_raw_ball_candidates = 0
        yolo_raw_racket_candidates = 0
        yolo_accepted_ball_candidates = 0
        yolo_accepted_racket_candidates = 0
        yolo_conf_sum = 0.0
        yolo_conf_n = 0
        prev_tracks = {}
        next_track_num = 1

        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break

            # Stride 1 by default = every frame (matches inference density).
            if total_frames % pose_stride == 0:
                sampled_frame_count += 1
                frame_h, frame_w = frame.shape[:2]

                crop_box = None
                if (
                    player_crop_enabled
                    and yolo_enabled
                    and yolo_model is not None
                    and frame_w > 0
                ):
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
                        fx = (x_off + lm.x * crop_w) / frame_w if frame_w else lm.x
                        fy = (y_off + lm.y * crop_h) / frame_h if frame_h else lm.y
                        landmarks[name] = {
                            "x": round(fx, 6),
                            "y": round(fy, 6),
                            "z": round(lm.z * z_scale, 6),
                            "visibility": round(lm.visibility, 6)
                        }
                    pose_sequence.append({
                        "frame_idx": total_frames,
                        "landmarks": landmarks
                    })

                if yolo_enabled and yolo_model is not None:
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
                            print(f"[TrainModal] YOLO inference failed at frame {total_frames}: {e}")
                        infer = []
                    if infer:
                        item = infer[0]
                        boxes = getattr(item, "boxes", None)
                        if boxes is not None and getattr(boxes, "xyxy", None) is not None:
                            h, w = frame.shape[:2]
                            frame_had_raw = False
                            frame_raw_racket = 0
                            frame_acc_racket = 0
                            for idx in range(len(boxes.xyxy)):
                                cls_id = int(boxes.cls[idx].item())
                                if cls_id not in (32, 38):
                                    continue
                                frame_had_raw = True
                                yolo_raw_detected_frames.add(total_frames)
                                if cls_id == 32:
                                    yolo_raw_ball_candidates += 1
                                else:
                                    yolo_raw_racket_candidates += 1
                                    frame_raw_racket += 1
                                conf = float(boxes.conf[idx].item())
                                class_conf_thres = (
                                    yolo_ball_conf_thres if cls_id == 32 else yolo_racket_conf_thres
                                )
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
                                yolo_rows.append(
                                    {
                                        "frame": total_frames,
                                        "label": label,
                                        "confidence": round(conf, 6),
                                        "bbox": {
                                            "x": round(nx, 6),
                                            "y": round(ny, 6),
                                            "w": round(nw, 6),
                                            "h": round(nh, 6),
                                        },
                                        "track_id": track_id,
                                    }
                                )
                                yolo_det_frame_set.add(total_frames)
                                yolo_conf_sum += conf
                                yolo_conf_n += 1
                                if label == "sports_ball":
                                    yolo_ball_count += 1
                                    yolo_accepted_ball_candidates += 1
                                else:
                                    yolo_racket_count += 1
                                    yolo_accepted_racket_candidates += 1
                                    frame_acc_racket += 1
                            if yolo_logs and frame_had_raw:
                                print(
                                    f"[TrainModal][YOLO] frame={total_frames} raw_racket={frame_raw_racket} accepted_racket={frame_acc_racket}"
                                )

            total_frames += 1

        cap.release()
        mp_pose_obj.close()
        print(f"Extraction complete: {total_frames} total frames, {len(pose_sequence)} pose frames captured")

        # Resolve impact via YOLO ball∩racket contact (parity with inference). Fallback to the
        # last pose frame (admin clips are trimmed to end ≈ contact) when no contact is found.
        impact_frame_resolved = None
        if pose_sequence:
            _pose_frames = sorted(
                row["frame_idx"]
                for row in pose_sequence
                if isinstance(row.get("landmarks"), dict)
            )
            _ball = {r["frame"] for r in yolo_rows if r.get("label") == "sports_ball"}
            _racket = {r["frame"] for r in yolo_rows if r.get("label") == "racket"}
            _contact = sorted(_ball & _racket)
            if _contact:
                impact_frame_resolved = _contact[len(_contact) // 2]
            elif _pose_frames:
                impact_frame_resolved = _pose_frames[-1]

        pose_enrichment = None
        mesh_enabled = _env_bool("MESH_ENRICHMENT_ENABLED", True)
        if mesh_enabled and total_frames > 0 and pose_sequence:
            pose_by_frame = {
                row["frame_idx"]: row["landmarks"]
                for row in pose_sequence
                if isinstance(row.get("landmarks"), dict)
            }
            # Index a WIDE contact-centered window for redundancy: the TRAIN_INDEX_WINDOW
            # sampled frames closest to impact (same closeness rule the server uses for pose),
            # so pose and mesh enrich the exact same frames and align with the query window.
            train_window = _env_int("TRAIN_INDEX_WINDOW", 40, 1, 240)
            sampled_sorted = sorted(pose_by_frame.keys())
            center = impact_frame_resolved if impact_frame_resolved is not None else (
                sampled_sorted[-1] if sampled_sorted else 0
            )
            candidates = sorted(
                sorted(sampled_sorted, key=lambda f: abs(f - center))[:train_window]
            )
            pose_enrichment = enrich_impact_frames(
                video_path,
                candidates,
                pose_by_frame,
                trigger="train_impact_window",
            )

        # Step 4: Optional OpenAI label normalization metadata
        print("Step 4: Normalizing label metadata (optional OpenAI)...")
        normalized_label = _normalize_label_with_openai(req.movement_label.strip())

        # Step 5: Save results to Neon
        print("Step 5: Saving results to Neon...")
        extraction_meta = {
            "processed_at": _utc_now_iso(),
            "sampler": {"stride": pose_stride},
            "model": {"provider": "mediapipe", "name": "pose", "model_complexity": 1},
            "impact_frame_resolved": impact_frame_resolved,
            "pose_enrichment": pose_enrichment,
            "yolo_summary": {
                "enabled": bool(yolo_enabled),
                "model": "yolov8n",
                "sampled_frames": sampled_frame_count,
                "detected_frames": len(yolo_det_frame_set),
                "sports_ball_count": yolo_ball_count,
                "racket_count": yolo_racket_count,
                "raw_detected_frames": len(yolo_raw_detected_frames),
                "raw_ball_candidates": yolo_raw_ball_candidates,
                "raw_racket_candidates": yolo_raw_racket_candidates,
                "accepted_ball_candidates": yolo_accepted_ball_candidates,
                "accepted_racket_candidates": yolo_accepted_racket_candidates,
                "avg_confidence": round(yolo_conf_sum / yolo_conf_n, 6) if yolo_conf_n else 0.0,
                "confidence_threshold": yolo_conf_thres,
                "confidence_threshold_racket": yolo_racket_conf_thres,
                "confidence_threshold_ball": yolo_ball_conf_thres,
                "iou_threshold": yolo_iou_thres,
                "imgsz": yolo_imgsz,
                # Keep metadata compact while preserving examples for debugging.
                "sample_rows": yolo_rows[:80],
            },
            "normalized_label": normalized_label,
            "train_video_id": req.train_video_id,
        }

        _update_status(
            conn,
            req.sample_id,
            status="completed",
            frame_count=len(pose_sequence),
            total_frames=total_frames,
            pose_sequence=pose_sequence,
            extraction_meta=extraction_meta,
            error_message=None,
            movement_label=req.movement_label.strip(),
        )
        conn.commit()

        print(f"Successfully saved {len(pose_sequence)} frames for '{req.movement_label}'")
        return {
            "status": "success",
            "sample_id": req.sample_id,
            "movement_label": req.movement_label,
            "frame_count": len(pose_sequence),
            "total_frames": total_frames,
            "normalized_label": normalized_label,
        }

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

        # Try to mark as failed in Neon
        try:
            _update_status(
                conn,
                req.sample_id,
                status="failed",
                error_message=str(e),
            )
            conn.commit()
        except Exception:
            pass

        return {"status": "error", "message": str(e)}
    finally:
        try:
            conn.close()
        except Exception:
            pass