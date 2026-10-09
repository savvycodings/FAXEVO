# /// script
# requires-python = ">=3.10,<3.13"
# dependencies = ["rtmlib", "onnxruntime", "opencv-python", "numpy"]
# ///
"""
21-point hand keypoints for every frame of a clip, for the largest person in frame.

The backend's pose data is MediaPipe Pose, which carries only three rough hand points, so the
control skeleton has no fingers and Fun Control draws fists and stumps. This adds DWPose
(rtmlib Wholebody, as in make_pose_control.py) hands, in OpenPose's 21-point hand layout, so
they can be merged into the analysis pose rows and drawn into the skeleton.

  uv run FAXevo/comfyui-deploy/extract_hands.py clip.mp4 hands.json

Output: {"width", "height", "fps", "frames": [{"frame", "hands": [{"label": "left"|"right",
"points": [[x, y, score] x21]}]}]}, x/y normalized to the frame. Labels are DWPose's; the
backend matches each hand to a wrist by distance rather than trusting them.
"""

import argparse
import json

import cv2
import numpy as np
from rtmlib import Wholebody

# rtmlib Wholebody(to_openpose=True): left hand 92-112, right hand 113-133.
HANDS = {"left": range(92, 113), "right": range(113, 134)}


def largest_person(keypoints: np.ndarray, scores: np.ndarray, thr: float) -> int | None:
    best, best_area = None, 0.0
    for i in range(len(keypoints)):
        pts = keypoints[i][:18][scores[i][:18] > thr]
        if len(pts) < 5:
            continue
        area = float(np.ptp(pts[:, 0]) * np.ptp(pts[:, 1]))
        if area > best_area:
            best, best_area = i, area
    return best


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("out")
    ap.add_argument("--thr", type=float, default=0.3)
    ap.add_argument("--mode", default="balanced", choices=["lightweight", "balanced", "performance"])
    args = ap.parse_args()

    model = Wholebody(to_openpose=True, mode=args.mode, backend="onnxruntime", device="cpu")
    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        raise SystemExit(f"cannot open {args.video}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    frames = []
    idx = 0
    while True:
        ok, img = cap.read()
        if not ok:
            break
        k, s = model(img)
        who = largest_person(k, s, args.thr) if len(k) else None
        hands = []
        if who is not None:
            for label, rng in HANDS.items():
                pts = [[float(k[who][j][0]) / w, float(k[who][j][1]) / h, float(s[who][j])] for j in rng]
                hands.append({"label": label, "points": pts})
        frames.append({"frame": idx, "hands": hands})
        idx += 1
    cap.release()
    with open(args.out, "w") as f:
        json.dump({"width": w, "height": h, "fps": fps, "frames": frames}, f)
    seen = sum(1 for fr in frames for hd in fr["hands"] if np.mean([p[2] for p in hd["points"]]) > args.thr)
    print(f"{args.out}: {len(frames)} frames, {seen} confident hands")


if __name__ == "__main__":
    main()
