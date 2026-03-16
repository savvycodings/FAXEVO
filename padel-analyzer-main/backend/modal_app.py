import modal
import requests
from pydantic import BaseModel, Field
from typing import Literal

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
    .pip_install("opencv-python-headless")
    .pip_install("numpy")
    .pip_install("requests")
)

app = modal.App("padel-analyzer")

AllowedModels = Literal["mediapipe"]
DEFAULT_MODEL = "mediapipe"


class AnalyzeRequest(BaseModel):
  video_url: str
  analysis_id: str
  model: AllowedModels = Field(default=DEFAULT_MODEL)


@app.function(image=image, gpu="any", timeout=600)
@modal.fastapi_endpoint(method="POST")
def analyze_video(req: AnalyzeRequest):
    print(f"=== Starting analysis for {req.analysis_id} ===")
    print(f"Request data: video_url={req.video_url}, analysis_id={req.analysis_id}, model={req.model}")

    if not req.video_url or not req.analysis_id:
        return {"status": "error", "message": "Missing video_url or analysis_id"}

    try:
        # Download video
        print("Step 1: Downloading video...")
        import tempfile as tf
        import os
        import requests as dl
        import cv2

        with tf.NamedTemporaryFile(delete=False, suffix=".mp4") as tmp_video:
            download_response = dl.get(req.video_url, stream=True, timeout=60)
            if download_response.status_code != 200:
                return {"status": "error", "message": f"Failed to download video: {download_response.status_code}"}

            for chunk in download_response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    tmp_video.write(chunk)
            video_path = tmp_video.name
            print(f"Video downloaded to {video_path}")

        # MediaPipe analysis only
        print("Step 2: Running MediaPipe analysis...")
        metrics = run_mediapipe_analysis(video_path)

        # Clean up temp file
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


def run_mediapipe_analysis(video_path):
    """MediaPipe analysis using mediapipe package"""
    print("Using MediaPipe Pose (mediapipe)")
    import mediapipe as mp
    mp_pose = mp.solutions.pose
    import cv2
    import numpy as np
    
    mp_pose_obj = mp_pose.Pose(
        static_image_mode=False,
        model_complexity=0,
        enable_segmentation=False,
        min_detection_confidence=0.5
    )
    
    cap = cv2.VideoCapture(video_path)
    frames_data = []
    frame_count = 0
    
    print("Processing frames...")
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
        
        # Process every 15th frame for speed
        if frame_count % 15 == 0:
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = mp_pose_obj.process(rgb_frame)
            
            if results.pose_landmarks:
                landmarks = {}
                for idx, lm in enumerate(results.pose_landmarks.landmark):
                    name = mp_pose.PoseLandmark(idx).name
                    landmarks[name] = {"x": lm.x, "y": lm.y}
                frames_data.append({"frame": frame_count, "landmarks": landmarks})
        
        frame_count += 1
    
    cap.release()
    print(f"MediaPipe complete: {frame_count} frames, {len(frames_data)} pose data")
    
    # Return raw pose metrics; higher-level AI analysis runs in Node/Neon stack
    return {
        "total_frames": frame_count,
        "analyzed_frames": len(frames_data),
        "pose_data": frames_data[:10],
    }
