# /// script
# requires-python = ">=3.10,<3.13"
# dependencies = ["rtmlib", "onnxruntime", "opencv-python", "numpy"]
# ///
"""
Build the face video for the Wan 2.2 Animate workflow (node 13, xevo_animate_face.mp4):
a 512x512 crop of the player's face for every frame, sampled with the same --start,
--frames and --fps as make_pose_control.py so it lines up with pose.mp4.

The crop is centred on the largest person's face keypoints each frame, with one fixed
size (median over the clip) so the face doesn't pulse in and out.

  uv run FAXevo/comfyui-deploy/make_face_crops.py swing.mp4 --start 0.2 --frames 33 --fps 16 --out face.mp4
"""

import argparse
import subprocess

import cv2
import numpy as np
from rtmlib import Wholebody

# rtmlib Wholebody (COCO-WholeBody order): face landmarks are 23-90.
FACE = slice(23, 91)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--out", default="face.mp4")
    ap.add_argument("--start", type=float, default=0.0)
    ap.add_argument("--frames", type=int, default=33)
    ap.add_argument("--fps", type=int, default=16)
    ap.add_argument("--size", type=int, default=512)
    ap.add_argument("--scale", type=float, default=1.8, help="crop side as a multiple of the face landmark extent")
    ap.add_argument("--thr", type=float, default=0.3)
    args = ap.parse_args()

    cap = cv2.VideoCapture(args.video)
    src_fps = cap.get(cv2.CAP_PROP_FPS)
    model = Wholebody(to_openpose=False, mode="performance", backend="onnxruntime", device="cpu")

    images, centres, extents = [], [], []
    for i in range(args.frames):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(round((args.start + i / args.fps) * src_fps)))
        ok, img = cap.read()
        if not ok:
            break
        images.append(img)
        kps, scs = model(img)
        if len(kps) == 0:
            centres.append(None)
            continue
        best = int(np.argmax([np.ptp(k[:, 1]) for k in kps]))
        face = kps[best][FACE][scs[best][FACE] > args.thr]
        if len(face) < 10:
            centres.append(None)
            continue
        centres.append(face.mean(axis=0))
        extents.append(max(np.ptp(face[:, 0]), np.ptp(face[:, 1])))

    if not extents:
        raise SystemExit("no face found in any frame")
    side = int(np.median(extents) * args.scale)
    found = [c for c in centres if c is not None]
    last = found[0]

    p = subprocess.Popen(
        ["ffmpeg", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24",
         "-s", f"{args.size}x{args.size}", "-r", str(args.fps), "-i", "-",
         "-c:v", "libx264", "-crf", "12", "-pix_fmt", "yuv420p", args.out],
        stdin=subprocess.PIPE,
    )
    for img, c in zip(images, centres):
        last = c if c is not None else last
        padded = cv2.copyMakeBorder(img, side, side, side, side, cv2.BORDER_REPLICATE)
        x0, y0 = int(last[0] - side / 2) + side, int(last[1] - side / 2) + side
        crop = padded[y0:y0 + side, x0:x0 + side]
        p.stdin.write(cv2.resize(crop, (args.size, args.size), interpolation=cv2.INTER_CUBIC).tobytes())
    p.stdin.close()
    p.wait()

    missing = sum(c is None for c in centres)
    print(f"wrote {args.out}: {len(images)} frames, face crop {side}px, no face in {missing}")


if __name__ == "__main__":
    main()
