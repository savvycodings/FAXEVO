# comfyui-deploy machine definitions

Machine/environment config for self-hosted [comfyui-deploy](https://github.com/BennyKok/comfyui-deploy) (Modal builder), derived directly from the 4 workflow API files in `BEXevo/workflows/`:

- `qwen_image_edit_plus_gguf_correction.api.json`
- `sdxl_correction_openpose_faceid.api.json`
- `video_wan2_2_5B_ti2v.json`
- `video_wan2_2_fun_control.api.json`

## Why 3 machines instead of 1

comfyui-deploy's `/create` payload (see `builder/modal-builder/src/main.py`) pins **one GPU per machine**. Our 4 workflows have very different VRAM profiles, so one shared machine either overpays or under-provisions:

| Machine | Workflows | Heaviest model | Suggested GPU |
|---|---|---|---|
| `xevo-image-correction` | Qwen GGUF edit, SDXL openpose+faceid | Qwen-Image Q4_K_M GGUF (~quantized, ~6-8GB) | `A10G` |
| `xevo-video-ti2v-5b` | Wan 2.2 TI2V 5B | `wan2.2_ti2v_5B_fp16.safetensors` (~10GB) | `A10G` or `A100` |
| `xevo-video-fun-control-14b` | Wan 2.2 Fun Control 14B (dual high/low-noise UNet, the OpenPose ControlNet video workflow) | two 14B bf16 UNets loaded simultaneously (~50GB+ combined) | `A100` |

Start all three at `A100` if unsure — downgrade once you've watched real VRAM usage per machine in the builder logs. Don't put `xevo-video-fun-control-14b` on anything smaller than `A100`; the dual 14B UNet load will OOM on `T4`/`L4`/`A10G`.

## Files

- **`snapshot.template.json`** — custom-node/core environment for the **image-correction** machine (Qwen GGUF + SDXL FaceID). Hashes are pinned to each repo's current public HEAD (resolved via `git ls-remote`), so it is deployable as-is.
- **`snapshot.video.json`** — lean snapshot for the two **Wan video** machines. Both video workflows use only core ComfyUI nodes, so this pins just the core `comfyui` hash + ComfyUI-Manager (no custom nodes).
- **`models.image-correction.json`**, **`models.video-ti2v-5b.json`**, **`models.video-fun-control-14b.json`** — per-machine model manifests, derived from the literal filenames baked into each workflow JSON. The two **video** manifests have real `url`s (Comfy-Org/Wan_2.2_ComfyUI_Repackaged); the image-correction manifest still has some `TODO` urls.
- **`create-machine.mjs`** — posts a machine definition to your deployed modal-builder `/create` endpoint. Snapshot file is selectable via `SNAPSHOT_FILE=...` (defaults to `snapshot.template.json`).

Workflow JSONs are the copies in **`FAXevo/workflows/`** (`video_wan2_2_fun_control.api.json`, `video_wan2_2_5B_ti2v.json`), which are the source of truth mirrored from `BEXevo/workflows/`.

## Snapshot notes

The pinned hashes make deploys reproducible against public HEAD at commit time. For **byte-exact** reproducibility of the shared Comfy box that already renders these workflows, export a ComfyUI-Manager **"Save Snapshot"** from that instance (Manager menu → Save Snapshot; lands in `ComfyUI/user/default/ComfyUI-Manager/snapshots/*.json`) and copy it over the relevant snapshot file.

## Model URLs

The two **video** manifests are filled in from `Comfy-Org/Wan_2.2_ComfyUI_Repackaged` — the same source ComfyUI's official Wan 2.2 templates use. VAE note (resolved, both intentional):

- `video_wan2_2_5B_ti2v.json` loads **`wan2.2_vae.safetensors`** and `video_wan2_2_fun_control.api.json` loads **`wan_2.1_vae.safetensors`**. This is **correct and intentional** — it matches ComfyUI's official Wan 2.2 templates (TI2V 5B pairs with the 2.2 VAE; Fun Control 14B pairs with the 2.1 VAE).

The **image-correction** manifest still has `TODO` urls (quantized GGUF repacks + the SDXL FaceID preset filenames resolved by name at runtime) — fill those from the working instance before deploying `xevo-image-correction`.

## Deploying a machine

You need a running comfyui-deploy **modal-builder** (`BUILDER_URL`) and a comfyui-deploy web app callback (`CALLBACK_URL`). These are NOT in this repo — the builder source lives in [BennyKok/comfyui-deploy](https://github.com/BennyKok/comfyui-deploy) under `builder/modal-builder`. Modal CLI auth is already set up (profile `axevo-tinhochu`).

```bash
export BUILDER_URL="https://your-modal-builder..."       # your deployed modal-builder instance
export CALLBACK_URL="https://your-comfyui-deploy-app.example.com/api/machine-built"

# Video machines use the lean core-only snapshot:
SNAPSHOT_FILE=snapshot.video.json \
  node create-machine.mjs xevo-video-fun-control-14b "Xevo Wan2.2 Fun Control 14B" models.video-fun-control-14b.json A100
SNAPSHOT_FILE=snapshot.video.json \
  node create-machine.mjs xevo-video-ti2v-5b         "Xevo Wan2.2 TI2V 5B"          models.video-ti2v-5b.json          A10G

# Image-correction machine uses the full snapshot (fill its model URLs first):
node create-machine.mjs xevo-image-correction "Xevo Image Correction (Qwen+SDXL)" models.image-correction.json A10G
```

> Heads up: each `create` kicks off a **billed GPU build** on Modal that downloads the model set (the Fun Control 14B pair alone is ~57 GB) and provisions the GPU. Confirm A100 quota on the Modal account before running the Fun Control build.

Each call POSTs to `${BUILDER_URL}/create` and the builder streams build logs back over `ws://.../ws/{machine_id}` — watch `machine_id_websocket_dict` server logs if a build hangs.

## Wiring BEXevo to the deployed machine

Once machines exist, `src/technique/comfyVideo.ts` / `comfyCorrection.ts` need to target the comfyui-deploy `/run` (or equivalent) endpoint + `machine_id` instead of a raw Comfy server URL — that's the follow-up piece once the machines are actually built and you've confirmed the 4 workflows render correctly through them.
