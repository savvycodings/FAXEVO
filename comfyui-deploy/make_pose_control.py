# /// script
# requires-python = ">=3.10,<3.13"
# dependencies = ["rtmlib", "onnxruntime", "opencv-python", "numpy"]
# ///
"""
Build the two inputs for the Wan 2.2 Fun Control workflow from one real swing clip,
without any custom nodes on the ComfyUI box:

  <out>/start.png  -> Load Image (node 145, ref_image)
  <out>/pose.mp4   -> Load Video (node 158, control_video)

The skeleton is DWPose (rtmlib Wholebody) drawn in standard OpenPose colors on black,
which is what Fun Control was trained on. Only the largest person in frame is drawn,
so other players on court don't leak into the control video.

  uv run FAXevo/comfyui-deploy/make_pose_control.py swing.mp4 --start 1.2 --frames 33 --fps 16

Corrected skeleton (same idea as the backend's coachedControlLandmarkFrames): pass a pro
clip and the player's pose is pulled part of the way toward the pro's, after the pro is
time-aligned on peak wrist speed, moved onto the player's hips, scaled to the player's
torso, and mirrored if the two swing with different arms.

  uv run ... player.mp4 --start 0.9 --frames 25 --fps 16 --pro pro.mp4 --pro-start 1.0 --blend 0.4

With --pro, pose.mp4 is the corrected skeleton and pose_own.mp4 is the player's own, for
comparison. Then set node 160 width/height/length and node 100 fps to the printed values.

The racket arm is guessed from wrist reach, and a free arm stretched out for balance can
win; a pro read as left-handed gets mirrored and aligned on the wrong wrist. Check the
printed "swing arm" line and pass --player-side R --pro-side R (or L) when it's wrong.

Crop the clip around the player first (ffmpeg crop) when they're small in frame: the model
works in 16-pixel blocks, so a 70-pixel-wide player can't get a stable face or fingers.
"""

import argparse
import os
import subprocess
import tempfile

import cv2
import numpy as np
from rtmlib import Wholebody, draw_skeleton

# rtmlib Wholebody(to_openpose=True) -> 134 points: OpenPose-18 body (0-17, neck=1),
# feet 18-23 (left 18-20, right 21-23), face 24-91, left hand 92-112, right hand 113-133.
R_SHO, R_WRI, L_SHO, L_WRI, R_HIP, L_HIP = 2, 4, 5, 7, 8, 11
_PAIRS = [(2, 5), (3, 6), (4, 7), (8, 11), (9, 12), (10, 13), (14, 15), (16, 17)]
_PAIRS += [(18 + i, 21 + i) for i in range(3)]
_PAIRS += [(92 + i, 113 + i) for i in range(21)]
MIRROR_PERM = np.arange(134)
for a, b in _PAIRS:
    MIRROR_PERM[a], MIRROR_PERM[b] = b, a


def round32(n: float) -> int:
    return max(256, int(round(n / 32)) * 32)


def largest_person(keypoints: np.ndarray, scores: np.ndarray, thr: float) -> int | None:
    best, best_area = None, 0.0
    for i in range(len(keypoints)):
        pts = keypoints[i][scores[i] > thr]
        if len(pts) < 5:
            continue
        w, h = np.ptp(pts[:, 0]), np.ptp(pts[:, 1])
        if w * h > best_area:
            best, best_area = i, w * h
    return best


def extract(model, video: str, start: float, frames: int, fps: int, size: int, thr: float):
    """Resample `video` to `fps` from `start`; return resized frames and the main person's pose."""
    cap = cv2.VideoCapture(video)
    if not cap.isOpened():
        raise SystemExit(f"cannot open {video}")
    src_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    src_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    src_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    scale = size / max(src_w, src_h)
    out_w, out_h = round32(src_w * scale), round32(src_h * scale)

    wanted = [int(round((start + i / fps) * src_fps)) for i in range(frames)]
    raw: dict[int, np.ndarray] = {}
    idx = 0
    while idx <= wanted[-1]:
        ok, frame = cap.read()
        if not ok:
            break
        if idx in wanted:
            raw[idx] = frame
        idx += 1
    cap.release()
    if len(raw) < len(set(wanted)):
        raise SystemExit(
            f"{video} too short: need {frames} frames at {fps}fps from {start}s "
            f"({wanted[-1] / src_fps:.2f}s), clip has {idx / src_fps:.2f}s"
        )

    images, kps, scs = [], [], []
    for fi in wanted:
        img = cv2.resize(raw[fi], (out_w, out_h), interpolation=cv2.INTER_AREA)
        k, s = model(img)
        who = largest_person(k, s, thr) if len(k) else None
        images.append(img)
        kps.append(None if who is None else k[who])
        scs.append(None if who is None else s[who])
    return images, kps, scs, (out_w, out_h)


def mid(k: np.ndarray, s: np.ndarray, a: int, b: int, thr: float) -> np.ndarray | None:
    return (k[a] + k[b]) / 2 if s[a] > thr and s[b] > thr else None


def swing_side(kps, scs, thr: float) -> str | None:
    """Arm with more wrist reach from the hips over the window (same idea as the backend)."""
    reach = {"R": 0.0, "L": 0.0}
    for k, s in zip(kps, scs):
        if k is None:
            continue
        hip = mid(k, s, R_HIP, L_HIP, thr)
        if hip is None:
            continue
        for side, w in (("R", R_WRI), ("L", L_WRI)):
            if s[w] > thr:
                reach[side] += float(np.linalg.norm(k[w] - hip))
    hi, lo = max(reach.values()), min(reach.values())
    if hi <= 0 or (hi - lo) / hi < 0.04:
        return None
    return "R" if reach["R"] > reach["L"] else "L"


def peak_speed_index(kps, scs, wrist: int, thr: float) -> int:
    speeds = [0.0]
    for i in range(1, len(kps)):
        a, b = kps[i - 1], kps[i]
        ok = a is not None and b is not None and scs[i - 1][wrist] > thr and scs[i][wrist] > thr
        speeds.append(float(np.linalg.norm(b[wrist] - a[wrist])) if ok else 0.0)
    return int(np.argmax(speeds))


def retarget(pk, ps, uk, us, mirror: bool, thr: float):
    """Pro pose moved onto the user's hips and scaled to the user's torso."""
    phip, uhip = mid(pk, ps, R_HIP, L_HIP, thr), mid(uk, us, R_HIP, L_HIP, thr)
    psho, usho = mid(pk, ps, R_SHO, L_SHO, thr), mid(uk, us, R_SHO, L_SHO, thr)
    if phip is None or uhip is None or psho is None or usho is None:
        return None, None
    scale = np.linalg.norm(usho - uhip) / max(np.linalg.norm(psho - phip), 1e-6)
    rel = (pk - phip) * scale
    if mirror:
        rel[:, 0] *= -1
        rel, ps = rel[MIRROR_PERM], ps[MIRROR_PERM]
    return uhip + rel, ps


def blend(uk, us, pk, ps, alpha: float, thr: float):
    both = (us > thr) & (ps > thr)
    k = np.where(both[:, None], uk + (pk - uk) * alpha, np.where((us > thr)[:, None], uk, pk))
    s = np.where(both, np.minimum(us, ps), np.maximum(us, ps))
    return k, s


def smooth(kps, scs, radius: int, thr: float):
    """Centred moving average per joint over visible frames; endpoints shrink the window."""
    if radius < 1:
        return kps
    out = []
    for i in range(len(kps)):
        if kps[i] is None:
            out.append(None)
            continue
        lo, hi = max(0, i - radius), min(len(kps) - 1, i + radius)
        r = min(i - lo, hi - i)
        acc, cnt = np.zeros_like(kps[i]), np.zeros(len(kps[i]))
        for j in range(i - r, i + r + 1):
            if kps[j] is None:
                continue
            vis = scs[j] > thr
            acc[vis] += kps[j][vis]
            cnt[vis] += 1
        k = kps[i].copy()
        m = cnt > 0
        k[m] = acc[m] / cnt[m][:, None]
        out.append(k)
    return out


def write_pose_video(path: str, size: tuple[int, int], kps, scs, fps: int, thr: float) -> int:
    missed = 0
    with tempfile.TemporaryDirectory() as tmp:
        for n, (k, s) in enumerate(zip(kps, scs)):
            canvas = np.zeros((size[1], size[0], 3), dtype=np.uint8)
            if k is None:
                missed += 1
            else:
                canvas = draw_skeleton(canvas, k[None], s[None], openpose_skeleton=True, kpt_thr=thr)
            cv2.imwrite(os.path.join(tmp, f"{n:04d}.png"), canvas)
        subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-framerate", str(fps),
             "-i", os.path.join(tmp, "%04d.png"),
             "-c:v", "libx264", "-pix_fmt", "yuv420p", path],
            check=True,
        )
    return missed


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--out", default="pose_control_out")
    ap.add_argument("--start", type=float, default=0.0, help="seconds into the clip where the swing starts")
    ap.add_argument("--frames", type=int, default=33, help="4n+1: 17, 25, 33, ...")
    ap.add_argument("--fps", type=int, default=16, help="output fps; frames/fps = seconds covered")
    ap.add_argument("--size", type=int, default=768, help="long side, snapped to a multiple of 32")
    ap.add_argument("--thr", type=float, default=0.3, help="keypoint confidence threshold")
    ap.add_argument("--pro", help="pro clip whose swing the player's pose is pulled toward")
    ap.add_argument("--pro-start", type=float, default=0.0, help="seconds into the pro clip")
    ap.add_argument("--blend", type=float, default=0.4, help="0 = player's own pose, 1 = full pro pose")
    ap.add_argument("--mirror", choices=["auto", "yes", "no"], default="auto",
                    help="mirror the pro when the two swing with different arms")
    ap.add_argument("--player-side", choices=["R", "L"],
                    help="player's racket arm; overrides detection, which can pick a reaching free arm")
    ap.add_argument("--pro-side", choices=["R", "L"], help="pro's racket arm; overrides detection")
    ap.add_argument("--smooth", type=int, default=1, help="moving-average radius in frames (0 = off)")
    args = ap.parse_args()

    if (args.frames - 1) % 4:
        raise SystemExit(f"--frames must be 4n+1 (got {args.frames})")

    model = Wholebody(to_openpose=True, mode="balanced", backend="onnxruntime", device="cpu")
    images, ukps, uscs, size = extract(
        model, args.video, args.start, args.frames, args.fps, args.size, args.thr
    )
    os.makedirs(args.out, exist_ok=True)
    cv2.imwrite(os.path.join(args.out, "start.png"), images[0])

    if not args.pro:
        missed = write_pose_video(os.path.join(args.out, "pose.mp4"), size, ukps, uscs, args.fps, args.thr)
        print(f"wrote {args.out}/start.png and {args.out}/pose.mp4")
    else:
        _, pkps, pscs, _ = extract(
            model, args.pro, args.pro_start, args.frames, args.fps, args.size, args.thr
        )
        uside = args.player_side or swing_side(ukps, uscs, args.thr)
        pside = args.pro_side or swing_side(pkps, pscs, args.thr)
        mirror = args.mirror == "yes" or (args.mirror == "auto" and uside and pside and uside != pside)
        uw = L_WRI if uside == "L" else R_WRI
        pw = L_WRI if pside == "L" else R_WRI
        shift = peak_speed_index(pkps, pscs, pw, args.thr) - peak_speed_index(ukps, uscs, uw, args.thr)

        ckps, cscs = [], []
        for i in range(args.frames):
            uk, us = ukps[i], uscs[i]
            j = min(max(i + shift, 0), args.frames - 1)
            pk, ps = pkps[j], pscs[j]
            if uk is None:
                ckps.append(None)
                cscs.append(None)
                continue
            rk, rs = retarget(pk, ps, uk, us, bool(mirror), args.thr) if pk is not None else (None, None)
            if rk is None:
                ckps.append(uk)
                cscs.append(us)
                continue
            k, s = blend(uk, us, rk, rs, args.blend, args.thr)
            ckps.append(k)
            cscs.append(s)
        ckps = smooth(ckps, cscs, args.smooth, args.thr)

        write_pose_video(os.path.join(args.out, "pose_own.mp4"), size, ukps, uscs, args.fps, args.thr)
        missed = write_pose_video(os.path.join(args.out, "pose.mp4"), size, ckps, cscs, args.fps, args.thr)
        print(f"wrote {args.out}/start.png, {args.out}/pose.mp4 (corrected) and {args.out}/pose_own.mp4")
        print(
            f"swing arm player={uside or '?'} pro={pside or '?'} mirror={bool(mirror)} "
            f"time shift={shift:+d} frames blend={args.blend}"
        )

    w, h = size
    print(f"node 160: width={w} height={h} length={args.frames} | node 100: fps={args.fps}")
    if missed:
        print(f"warning: no person found in {missed}/{args.frames} frames (those are blank)")


if __name__ == "__main__":
    main()
