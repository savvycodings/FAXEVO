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

- **`snapshot.template.json`** — the custom-node/core environment (ComfyUI-Manager "snapshot" format). Shared across all 3 machines since none of the custom nodes are workflow-specific enough to bother splitting.
- **`models.image-correction.json`**, **`models.video-ti2v-5b.json`**, **`models.video-fun-control-14b.json`** — per-machine model manifests, derived from the literal filenames baked into each workflow JSON.
- **`create-machine.mjs`** — posts a machine definition to your deployed modal-builder `/create` endpoint.

## ⚠️ Before you run this: get a real snapshot, don't trust my hashes

`snapshot.template.json` has the **correct custom-node repos** (grep'd straight out of the workflow JSONs' node types), but the `hash` fields are placeholders — I can't know the exact commit your shared Comfy box is running, and guessing would just move the "messy shared Comfy" problem into the deploy config instead of fixing it.

Do this once, on the shared Comfy instance that currently renders these 4 workflows correctly:

1. Install [ComfyUI-Manager](https://github.com/ltdrdata/ComfyUI-Manager) if it isn't already there (it almost certainly is).
2. Manager menu → **"Save Snapshot"**. This dumps the exact `comfyui` core hash + every custom node's exact commit hash into `ComfyUI/user/default/ComfyUI-Manager/snapshots/*.json`.
3. Copy that file over `snapshot.template.json` here (same shape: `comfyui`, `git_custom_nodes`, `file_custom_nodes`).
4. Commit it. From now on, "what's actually installed" is a diffable git file instead of tribal knowledge on one machine.

## ⚠️ Also fill in real model URLs

The `url` field in each `models.*.json` is `"TODO"` for anything I wasn't 100% sure of the exact source for (quantized GGUF repacks and Wan finetunes have multiple community re-uploads — picking the wrong one silently changes output quality). Filenames, `save_path`, and `type` are accurate — they're read straight off the workflow JSON — you just need to point `url` at wherever your current shared instance actually pulls these from (check `ComfyUI/models/<save_path>/` on that box, or your team's model-download script if you have one).

Two filename mismatches worth a sanity check with whoever built these workflows before you deploy:

- `video_wan2_2_5B_ti2v.json` loads **`wan2.2_vae.safetensors`**, but `video_wan2_2_fun_control.api.json` loads **`wan_2.1_vae.safetensors`** — different VAE files for the two Wan workflows. This may be intentional (Fun Control 14B was released before an updated 2.2 VAE existed), but confirm it's not a leftover from copying the workflow before it was fully updated.
- The SDXL workflow's `IPAdapterUnifiedLoaderFaceID` node uses preset `"FACEID PLUS V2"`, which resolves `ip-adapter-faceid-plusv2_sdxl.bin` + its LoRA + a CLIP vision encoder **by preset name at runtime** — none of those filenames appear literally in the JSON, so they're not in `models.image-correction.json` yet. Add them once you confirm exact filenames from the working instance.

## Deploying a machine

```bash
export BUILDER_URL="https://your-modal-builder.fly.dev"   # your deployed modal-builder instance
export CALLBACK_URL="https://your-comfyui-deploy-app.example.com/api/machine-built"

node create-machine.mjs xevo-image-correction        "Xevo Image Correction (Qwen+SDXL)" models.image-correction.json        A10G
node create-machine.mjs xevo-video-ti2v-5b            "Xevo Wan2.2 TI2V 5B"               models.video-ti2v-5b.json             A10G
node create-machine.mjs xevo-video-fun-control-14b    "Xevo Wan2.2 Fun Control 14B"        models.video-fun-control-14b.json     A100
```

Each call POSTs to `${BUILDER_URL}/create` and the builder streams build logs back over `ws://.../ws/{machine_id}` — watch `machine_id_websocket_dict` server logs if a build hangs.

## Wiring BEXevo to the deployed machine

Once machines exist, `src/technique/comfyVideo.ts` / `comfyCorrection.ts` need to target the comfyui-deploy `/run` (or equivalent) endpoint + `machine_id` instead of a raw Comfy server URL — that's the follow-up piece once the machines are actually built and you've confirmed the 4 workflows render correctly through them.
