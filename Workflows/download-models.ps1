# Download Xevo local AI weights into ComfyUI + Hugging Face cache.
# Safe to re-run (curl -C - / hf resume). Prefer fp8 Fun Control for RTX 5090 (32GB).

$ErrorActionPreference = "Stop"
$Comfy = "C:\Users\knoom\ComfyUI"
$LogDir = Join-Path $PSScriptRoot "logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Ensure-Dir([string]$Path) {
  New-Item -ItemType Directory -Force -Path $Path | Out-Null
}

function Download-File {
  param(
    [Parameter(Mandatory=$true)][string]$Url,
    [Parameter(Mandatory=$true)][string]$OutFile
  )
  Ensure-Dir (Split-Path -Parent $OutFile)
  # Only skip if a sibling .ok marker exists from a finished download, or file is very large
  # and curl would report HTTP 416 / identical. Prefer resume via -C - for partials.
  if ((Test-Path "$OutFile.ok")) {
    Write-Host "SKIP (ok marker): $OutFile"
    return
  }
  Write-Host "GET $Url"
  Write-Host " -> $OutFile"
  $ok = $false
  for ($attempt = 1; $attempt -le 8; $attempt++) {
    & curl.exe -L --retry 5 --retry-delay 3 --retry-all-errors -C - -o $OutFile $Url
    if ($LASTEXITCODE -eq 0 -and (Test-Path $OutFile) -and ((Get-Item $OutFile).Length -gt 0)) {
      New-Item -ItemType File -Force -Path "$OutFile.ok" | Out-Null
      $ok = $true
      break
    }
    Write-Warning "Attempt $attempt failed for $OutFile (exit $LASTEXITCODE); retrying in 5s"
    Start-Sleep -Seconds 5
  }
  if (-not $ok) { throw "Download failed after retries: $Url" }
}

$ComfyFiles = @(
  # Wan 2.2 Fun Control 14B — fp8 for 5090
  @{ Url = "https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/diffusion_models/wan2.2_fun_control_high_noise_14B_fp8_scaled.safetensors"; Out = "$Comfy\models\diffusion_models\wan2.2_fun_control_high_noise_14B_fp8_scaled.safetensors" },
  @{ Url = "https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/diffusion_models/wan2.2_fun_control_low_noise_14B_fp8_scaled.safetensors"; Out = "$Comfy\models\diffusion_models\wan2.2_fun_control_low_noise_14B_fp8_scaled.safetensors" },

  # Wan 2.2 TI2V 5B
  @{ Url = "https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/diffusion_models/wan2.2_ti2v_5B_fp16.safetensors"; Out = "$Comfy\models\diffusion_models\wan2.2_ti2v_5B_fp16.safetensors" },

  # Shared text encoder + VAEs
  @{ Url = "https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors"; Out = "$Comfy\models\text_encoders\umt5_xxl_fp8_e4m3fn_scaled.safetensors" },
  @{ Url = "https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/vae/wan2.2_vae.safetensors"; Out = "$Comfy\models\vae\wan2.2_vae.safetensors" },
  @{ Url = "https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/vae/wan_2.1_vae.safetensors"; Out = "$Comfy\models\vae\wan_2.1_vae.safetensors" },

  # Also mirror CLIP path Comfy sometimes resolves
  @{ Url = "https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors"; Out = "$Comfy\models\clip\umt5_xxl_fp8_e4m3fn_scaled.safetensors" },

  # Qwen Image Edit GGUF stack (filenames match workflow JSON)
  @{ Url = "https://huggingface.co/unsloth/Qwen-Image-2512-GGUF/resolve/main/qwen-image-2512-Q4_K_M.gguf"; Out = "$Comfy\models\unet\qwen-image-2512-Q4_K_M.gguf" },
  @{ Url = "https://huggingface.co/unsloth/Qwen2.5-VL-7B-Instruct-GGUF/resolve/main/Qwen2.5-VL-7B-Instruct-UD-Q4_K_XL.gguf"; Out = "$Comfy\models\clip\Qwen2.5-VL-7B-Instruct-UD-Q4_K_XL.gguf" },
  @{ Url = "https://huggingface.co/Comfy-Org/Qwen-Image_ComfyUI/resolve/main/split_files/vae/qwen_image_vae.safetensors"; Out = "$Comfy\models\vae\qwen_image_vae.safetensors" },
  @{ Url = "https://huggingface.co/alibaba-pai/Qwen-Image-2512-Fun-Controlnet-Union/resolve/main/Qwen-Image-2512-Fun-Controlnet-Union-2602.safetensors"; Out = "$Comfy\models\controlnet\Qwen-Image-2512-Fun-Controlnet-Union-2602.safetensors" },

  # SDXL correction + OpenPose
  @{ Url = "https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0/resolve/main/sd_xl_base_1.0.safetensors"; Out = "$Comfy\models\checkpoints\sd_xl_base_1.0.safetensors" },
  @{ Url = "https://huggingface.co/thibaud/controlnet-openpose-sdxl-1.0/resolve/main/OpenPoseXL2.safetensors"; Out = "$Comfy\models\controlnet\OpenPoseXL2.safetensors" },

  # FaceID / IP-Adapter (SDXL FaceID Plus V2 preset)
  @{ Url = "https://huggingface.co/h94/IP-Adapter-FaceID/resolve/main/ip-adapter-faceid-plusv2_sdxl.bin"; Out = "$Comfy\models\ipadapter\ip-adapter-faceid-plusv2_sdxl.bin" },
  @{ Url = "https://huggingface.co/h94/IP-Adapter-FaceID/resolve/main/ip-adapter-faceid-plusv2_sdxl_lora.safetensors"; Out = "$Comfy\models\loras\ip-adapter-faceid-plusv2_sdxl_lora.safetensors" },
  @{ Url = "https://huggingface.co/h94/IP-Adapter/resolve/main/sdxl_models/image_encoder/model.safetensors"; Out = "$Comfy\models\clip_vision\CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors" },

  # Upscale (Real-ESRGAN) — used in texture/start-frame experiments
  @{ Url = "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth"; Out = "$Comfy\models\upscale_models\RealESRGAN_x4plus.pth" },
  @{ Url = "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.1/RealESRGAN_x2plus.pth"; Out = "$Comfy\models\upscale_models\RealESRGAN_x2plus.pth" },
  @{ Url = "https://huggingface.co/Kim2091/UltraSharp/resolve/main/4x-UltraSharp.pth"; Out = "$Comfy\models\upscale_models\4x-UltraSharp.pth" },

  # Wan 2.2 Animate extras (kyle-checklist)
  @{ Url = "https://huggingface.co/Kijai/WanVideo_comfy_fp8_scaled/resolve/main/Wan22Animate/Wan2_2-Animate-14B_fp8_e4m3fn_scaled_KJ.safetensors"; Out = "$Comfy\models\diffusion_models\Wan2_2-Animate-14B_fp8_e4m3fn_scaled_KJ.safetensors" },
  @{ Url = "https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/clip_vision/clip_vision_h.safetensors"; Out = "$Comfy\models\clip_vision\clip_vision_h.safetensors" },
  @{ Url = "https://huggingface.co/Kijai/WanVideo_comfy/resolve/main/Lightx2v/lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors"; Out = "$Comfy\models\loras\lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors" }
)

Write-Host "=== ComfyUI model downloads ($($ComfyFiles.Count) files) ==="
foreach ($f in $ComfyFiles) {
  Download-File -Url $f.Url -OutFile $f.Out
}

Write-Host "=== Hugging Face cache (Unsloth LLM / Orpheus / Chatterbox / Whisper STT) ==="
python -m pip install -U "huggingface_hub[cli]" hf_transfer | Out-Host
$env:HF_HUB_ENABLE_HF_TRANSFER = "1"

$HfRepos = @(
  @{ Id = "unsloth/Qwen3.5-4B-GGUF"; Patterns = @("Qwen3.5-4B-UD-Q4_K_XL.gguf") },
  @{ Id = "vinhnx90/VT-Orpheus-3B-TTS-Ceylia-Q4KM-GGUFF"; Patterns = @("VT-Orpheus-3B-TTS-Ceylia.Q4_K_M.gguf") },
  @{ Id = "ResembleAI/chatterbox"; Patterns = @("*") },
  @{ Id = "Systran/faster-whisper-large-v3"; Patterns = @("*") },
  @{ Id = "openai/whisper-large-v3"; Patterns = @("*.json","*.txt","model.safetensors","*.tiktoken") }
)

foreach ($repo in $HfRepos) {
  Write-Host "HF snapshot $($repo.Id)"
  $patternArgs = @()
  foreach ($p in $repo.Patterns) { $patternArgs += @("--include", $p) }
  & hf download $repo.Id @patternArgs
  if ($LASTEXITCODE -ne 0) {
    Write-Warning "hf download failed for $($repo.Id); retrying without hf_transfer"
    $env:HF_HUB_ENABLE_HF_TRANSFER = "0"
    & hf download $repo.Id @patternArgs
    $env:HF_HUB_ENABLE_HF_TRANSFER = "1"
  }
}

# InsightFace buffalo_l (FaceID)
$BuffaloZip = "$env:TEMP\buffalo_l.zip"
$BuffaloDir = "$Comfy\models\insightface\models\buffalo_l"
if (-not (Test-Path "$BuffaloDir\det_10g.onnx")) {
  Write-Host "GET InsightFace buffalo_l"
  Ensure-Dir $BuffaloDir
  Download-File -Url "https://github.com/deepinsight/insightface/releases/download/v0.7/buffalo_l.zip" -OutFile $BuffaloZip
  Expand-Archive -Path $BuffaloZip -DestinationPath "$Comfy\models\insightface\models" -Force
}

Write-Host "DONE. Comfy models under $Comfy\models ; HF cache under $env:USERPROFILE\.cache\huggingface"
