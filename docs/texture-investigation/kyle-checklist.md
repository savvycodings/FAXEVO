# Fun Control 14B texture: checks on the 5090 box

Every Fun Control 14B render on the box has a "stained glass" lattice, whatever the inputs or settings. The 5B model on the same box is clean. Details and evidence are in `README.md` in this folder. Steps 1-3 need shell access to the box, in this order; stop at the first one that gives a clean render. Step 4 downloads the model we want to move to next.

## 1. Verify the model files (about 5 minutes)

```bash
cd /home/shini/ComfyUI/models/diffusion_models
sha256sum wan2.2_fun_control_high_noise_14B_bf16.safetensors wan2.2_fun_control_low_noise_14B_bf16.safetensors
```

Expected:

```
e4be07ca25d67aaf3461ef87fbb5ad8762f602a5efa620aea9dc250ac2747a9d  wan2.2_fun_control_high_noise_14B_bf16.safetensors
d82bc21cd703e089eee4f6fabc25e90ebbd00965623fdc5e83d46d01dbeac2c3  wan2.2_fun_control_low_noise_14B_bf16.safetensors
```

If either differs, re-download it:

```bash
cd /home/shini/ComfyUI/models/diffusion_models
wget -c https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/diffusion_models/wan2.2_fun_control_high_noise_14B_bf16.safetensors
wget -c https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/diffusion_models/wan2.2_fun_control_low_noise_14B_bf16.safetensors
```

Also worth checking the shared text encoder and VAE the same way (`sha256sum` in `models/text_encoders` and `models/vae`) against the values shown on their Hugging Face file pages.

## 2. Try the official fp8 files (made for 32 GB cards)

```bash
cd /home/shini/ComfyUI/models/diffusion_models
wget -c https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/diffusion_models/wan2.2_fun_control_high_noise_14B_fp8_scaled.safetensors
wget -c https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/diffusion_models/wan2.2_fun_control_low_noise_14B_fp8_scaled.safetensors
```

Then point the backend at `FAXevo/workflows/video_wan2_2_fun_control.fp8.api.json` (`COMFYUI_FUN_CONTROL_WORKFLOW_PATH`) and generate one correction video.

## 3. Try an older ComfyUI side by side

The box runs ComfyUI 0.36.0 with PyTorch 2.14 (CUDA 13.0). This installs a second copy on port 8189 that reuses the same models, so the current server keeps running:

```bash
cd /home/shini
git clone https://github.com/comfyanonymous/ComfyUI ComfyUI-old
cd ComfyUI-old && git checkout 0d9017220a8a06c85f059f387949ff0bf23f4672
python3 -m venv .venv && . .venv/bin/activate
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128
pip install -r requirements.txt
rm -rf models && ln -s /home/shini/ComfyUI/models models
python main.py --listen 127.0.0.1 --port 8189
```

Run the same render against port 8189 (the backend's `COMFYUI_BASE_URL`, or load the workflow in that UI). If it's clean, the regression is in the newer ComfyUI or PyTorch, and we pin the older one.

## 4. Download Wan 2.2 Animate (for keeping the face, racket and ball)

Fun Control only sees one start frame, so the face and racket drift once the player turns. Wan 2.2 Animate is built to keep a specific person's look while following a pose: it takes a reference image of the player, the pose video, and crops of the player's own face. The workflow is `FAXevo/workflows/video_wan2_2_animate.api.json` and uses only built-in ComfyUI nodes. It needs these files (about 20 GB; the text encoder and VAE are already on the box):

```bash
cd /home/shini/ComfyUI/models
wget -c -P diffusion_models https://huggingface.co/Kijai/WanVideo_comfy_fp8_scaled/resolve/main/Wan22Animate/Wan2_2-Animate-14B_fp8_e4m3fn_scaled_KJ.safetensors
mkdir -p clip_vision loras
wget -c -P clip_vision https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/clip_vision/clip_vision_h.safetensors
wget -c -P loras https://huggingface.co/Kijai/WanVideo_comfy/resolve/main/Lightx2v/lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors
```

No restart is needed; ComfyUI picks up new model files on the next request. Animate is also a 14B model, so if the Fun Control lattice turns out to be a problem with the box itself, it will likely show up here too. Do steps 1-3 first.
