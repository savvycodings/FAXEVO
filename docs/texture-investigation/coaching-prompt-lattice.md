# Coaching prompt brings the Fun Control lattice back

**Date:** 2026-10-05  
**Analysis:** `4a236a48-63d2-4b6e-872b-ce590070c904` (Expo TestFlight → Railway → this 5090 Comfy)  
**Related:** [README.md](./README.md) (damaged-weight lattice, now fixed), [kyle-checklist.md](./kyle-checklist.md), [submission-mosaic-todos.md](./submission-mosaic-todos.md)

## What happened

After we pointed Railway at the RunPod bf16 workflow (`video_wan2_2_fun_control.runpod_bf16.api.json`, `CORRECTION_FUN_LENGTH=17`) and confirmed the Fun Control weights on the 5090 match the good checksums, a local hand test looked clean. The next Expo generation still showed the full-frame “stained glass” mosaic.

That was confusing because the Railway logs already showed the path we wanted:

- `comfyHost: xevo-comfy-kyle.ngrok.dev`
- `funWorkflow: video_wan2_2_fun_control.runpod_bf16.api.json`
- `length: 17`, `steps: 20`, `model: bf16`, canvas `768x768`
- `prompt: coaching`

The mosaic mp4 on Railway was **byte-identical** to the file Comfy wrote under `ComfyUI/output/video/`. Railway did not corrupt it. Env was not wrong.

## Why our earlier “clean” test did not catch it

The clean verify reused the **same start PNG** as the Expo job (sha256 `77878e18…`, 1080×1920), but it used:

1. A **different** pose control clip (`xevo_fun_pose_eb24aa7a-…` vs Expo’s `xevo_fun_pose_4a236a48-…`)
2. The **short generic** Fun Control prompt (~1347 chars), not the live **coaching** prompt (~3399 chars)

So we never actually replayed the production job.

## A/B on the same box (2026-10-05)

Fixed: start PNG, RunPod bf16 workflow, length 17, steps 20, cfg 3.5, shift 8, this Comfy. Changed one thing at a time.

| # | Pose | Positive prompt | Result |
|---|---|---|---|
| 1 | Expo `4a236a48` | Generic (`buildWanFunControlPrompt`) | **Clean** — no lattice (~142 KB) |
| 2 | Expo `4a236a48` | Exact coaching text from the mosaic mp4 + same seed `212920516` | **Lattice** — same look as Expo (~470 KB) |
| 3 | Older clean-test pose `eb24` | Exact coaching text + same seed | **Lattice** again |

Conclusion: **the coaching prompt path causes the lattice on good weights.** The Expo pose overlay alone does not; the same Expo pose is clean with the generic prompt.

Mid-frame artifacts for run 2/3 match the production mosaic (full-frame ~16 px token grid). Run 1 can still show soft faces / motion smear from the small player in the start frame; that is a separate quality issue.

## What the coaching prompt injects

Built by `buildWanFunControlCoachingPrompt` in [`server/src/technique/comfyVideo.ts`](../../server/src/technique/comfyVideo.ts) when correction-videos has coaching context (`prompt: 'coaching'` in logs).

On top of the usual photoreal / ball-continuity text it adds:

- `COACHING INTENT …`
- `WHAT WENT WRONG: …` (diagnosis)
- `PRIORITY BODY CHANGES (normalized frame coords, current -> target):` with lines like  
  `RIGHT_INDEX: current (0.516, 0.600) → target (0.697, 0.598) …`
- Joint angle targets and timing lines

Those coordinate dumps are the main difference vs the generic shot prompt. Wan Fun Control already gets limb placement from the OpenPose control video; stuffing numeric frame coords into the text conditioner is what correlates with the lattice in every coaching run we replayed.

## What is *not* the cause (for this incident)

- Damaged Fun Control UNet downloads (checksums still match [kyle-checklist.md](./kyle-checklist.md))
- Railway still on the old 33-frame / non-runpod workflow
- Wrong Comfy host (job ran on this 5090)
- App compare playback inventing the pattern
- Start-frame identity alone (same start PNG is clean under the generic prompt)

## What we should do to fix it

### Immediate (unblocks Expo)

1. **Stop feeding the coaching prompt into Fun Control video generation.**  
   In `generatePoseRetargetVideoComfy`, always use `buildWanFunControlPrompt(shot, handedness)` for the positive CLIP text (same as A/B run 1). Keep coaching context for stills / Gemini / UI copy if needed — just not for Wan Fun Control video.
2. Redeploy BE (org + savvycodings / Railway). No workflow JSON change required if Railway already has runpod_bf16 + length 17.
3. Force-regenerate a known mosaic analysis from TestFlight and confirm the embedded prompt is the short generic one and the mid-frame has no lattice.

**Status (2026-10-05):** step 1 landed in `generatePoseRetargetVideoComfy` — Fun Control video always uses the generic prompt; coaching context is logged as `coachingContextSkipped` when present but not sent to CLIP.

### Better follow-up (if we still want “coaching” in video)

Do **not** put normalized `(x, y)` joint targets or long diagnosis dumps in the CLIP positive. If we keep a coaching flavor, limit it to short natural-language cues only (e.g. “keep the elbow closer to the body”), and A/B that short form on the same start+pose before shipping.

Pose skeleton already carries the motion correction; text should stay identity / shot / continuity.

### Still separate (after lattice is gone)

- Tight player crop / face reference (Tin’s Animate / face-crop tooling) for melted faces and soft hands from a tiny figure in a 1080×1920 start stretched to 768×768.
- Do not re-download bf16 weights again for this coaching lattice; they are already the good files.

## How to re-check quickly

```bash
# Mid-frame from a new corrected.mp4 — lattice is obvious by eye on skin/court
ffmpeg -y -i corrected.mp4 -vf "select=eq(n\,8)" -frames:v 1 -update 1 mid.png

# Confirm which prompt path ran (coaching dumps PRIORITY BODY CHANGES)
ffprobe -v quiet -show_entries format_tags=prompt -of default=noprint_wrappers=1:nokey=1 corrected.mp4 \
  | python3 -c 'import sys,json; t=json.load(sys.stdin)["99"]["inputs"]["text"]; print(len(t), "PRIORITY" in t)'
```

Artifacts from the A/B (local only): `/tmp/forensic-4a23/ab/` — `1_expo_pose_generic.mp4` (clean), `2_expo_pose_coaching.mp4` / `3_clean_pose_coaching.mp4` (lattice).
