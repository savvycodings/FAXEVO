# Models required by current `server/.env` + workflows

Derived from `FAXevo/server/.env` (no secrets listed here).

## Local AI services (must be on this PC)

| Env | Port / URL | Model / assets |
|-----|------------|----------------|
| `XEVO_LLM_*` | Unsloth Studio `:8888` (ngrok `xevo-sloth-kyle`) | `unsloth/Qwen3.5-4B-GGUF` variant `UD-Q4_K_XL` |
| `XEVO_TTS_*` | Orpheus Studio `:8889` | `vinhnx90/VT-Orpheus-3B-TTS-Ceylia-Q4KM-GGUFF` voice `ceylia` |
| `XEVO_TTS_ES_*` | Chatterbox `:8890` | `ResembleAI/chatterbox` multilingual (`ChatterboxMultilingualTTS`, `language_id=es`) |
| `COMFYUI_BASE_URL` | ComfyUI `:8188` (ngrok `xevo-comfy-kyle`) | See workflows below |
| STT (coach dictation) | Unsloth Studio `/api/inference/audio/transcribe` | Whisper GGUF via Studio (e.g. `unslothai/whisper-large-v3-GGUF`) |

Chatterbox runtime: `~/.xevo/chatterbox-es` + `Workflows/chatterbox_es_server.py`.

## ComfyUI workflows pinned in `.env`

1. **Correction stills** — `COMFYUI_WORKFLOW_PATH=qwen_image_edit_plus_gguf_correction.api.json`
   - `qwen-image-2512-Q4_K_M.gguf`
   - `Qwen2.5-VL-7B-Instruct-UD-Q4_K_XL.gguf`
   - `qwen_image_vae.safetensors`
   - `Qwen-Image-2512-Fun-Controlnet-Union-2602.safetensors`

2. **TI2V 5B video** — `COMFYUI_VIDEO_WORKFLOW_PATH=video_wan2_2_5B_ti2v.json`
   - `wan2.2_ti2v_5B_fp16.safetensors`
   - `umt5_xxl_fp8_e4m3fn_scaled.safetensors`
   - `wan2.2_vae.safetensors`

3. **Fun Control 14B** — `COMFYUI_FUN_CONTROL_WORKFLOW_PATH=video_wan2_2_fun_control.runpod_bf16.api.json`
   - `wan2.2_fun_control_high_noise_14B_bf16.safetensors` (~28.6 GB)
   - `wan2.2_fun_control_low_noise_14B_bf16.safetensors` (~28.6 GB)
   - `umt5_xxl_fp8_e4m3fn_scaled.safetensors`
   - `wan_2.1_vae.safetensors`
   - Note: RTX 5090 (32 GB) usually prefers the **fp8** pair + `video_wan2_2_fun_control.fp8.api.json`; bf16 is what `.env` currently points at (RunPod-style).

## Cloud (no local weight download)

- Gemini correction images (`XEVO_DEFAULT_CORRECTION_IMAGE_PROVIDER=gemini`)
- OpenRouter Seedance video (`OPENROUTER_VIDEO_MODEL=bytedance/seedance-2.0`) — comment says local Comfy/SeedVR upscales later
- fal / Modal / YOLO (ultralytics pulls `yolov8n.pt` on first use)

## Download helpers

- `Workflows/download-models.ps1` — Comfy + HF cache
- `Workflows/logs/download-chatterbox.ps1` — ES Chatterbox weights via curl
