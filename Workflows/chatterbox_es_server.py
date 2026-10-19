#!/usr/bin/env python3
"""
Spanish Chatterbox TTS — OpenAI-compatible /v1/audio/speech for Xevo coach.

Drop-in for the old Orpheus Maria Studio on :8890. The coach router already
POSTs { input, model, voice, response_format } to XEVO_TTS_ES_BASE_URL.

Env:
  CHATTERBOX_HOST       bind host (default 127.0.0.1)
  CHATTERBOX_PORT       bind port (default 8890)
  CHATTERBOX_DEVICE     cuda | cpu (default cuda)
  CHATTERBOX_LANGUAGE   language_id for multilingual model (default es)
  CHATTERBOX_VOICE_REF  optional reference wav for voice cloning
  CHATTERBOX_EXAGGERATION  default 0.5
  CHATTERBOX_CFG_WEIGHT    default 0.5
"""
from __future__ import annotations

import io
import os
import threading
import time
from typing import Any, Optional

import numpy as np
import soundfile as sf
import torch
import uvicorn
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

HOST = os.environ.get("CHATTERBOX_HOST", "127.0.0.1")
PORT = int(os.environ.get("CHATTERBOX_PORT", "8890"))
DEVICE = os.environ.get("CHATTERBOX_DEVICE", "cuda" if torch.cuda.is_available() else "cpu")
LANGUAGE = os.environ.get("CHATTERBOX_LANGUAGE", "es")
VOICE_REF = os.environ.get("CHATTERBOX_VOICE_REF", "").strip() or None
DEFAULT_EXAG = float(os.environ.get("CHATTERBOX_EXAGGERATION", "0.5"))
DEFAULT_CFG = float(os.environ.get("CHATTERBOX_CFG_WEIGHT", "0.5"))
MODEL_ID = "ResembleAI/chatterbox"

app = FastAPI(title="Xevo Chatterbox ES", version="1.0")
_lock = threading.Lock()
_model = None
_loaded_at: Optional[float] = None


def get_model():
    global _model, _loaded_at
    if _model is not None:
        return _model
    with _lock:
        if _model is not None:
            return _model
        print(f"[chatterbox-es] loading multilingual on {DEVICE}…", flush=True)
        t0 = time.time()
        from chatterbox.mtl_tts import ChatterboxMultilingualTTS

        _model = ChatterboxMultilingualTTS.from_pretrained(device=DEVICE)
        _loaded_at = time.time()
        print(f"[chatterbox-es] ready in {_loaded_at - t0:.1f}s sr={_model.sr}", flush=True)
        return _model


class SpeechRequest(BaseModel):
    input: str = Field(..., min_length=1)
    model: Optional[str] = None
    voice: Optional[str] = None
    response_format: Optional[str] = "wav"
    language: Optional[str] = None
    audio_prompt_path: Optional[str] = None
    exaggeration: Optional[float] = None
    cfg_weight: Optional[float] = None


@app.get("/health")
def health():
    return {
        "ok": True,
        "loaded": _model is not None,
        "device": DEVICE,
        "language": LANGUAGE,
        "model_id": MODEL_ID,
        "voice_ref": VOICE_REF,
    }


@app.get("/v1/models")
def list_models():
    return {
        "object": "list",
        "data": [
            {
                "id": MODEL_ID,
                "object": "model",
                "owned_by": "resemble",
                "loaded": _model is not None,
            }
        ],
    }


@app.post("/v1/audio/speech")
def audio_speech(
    body: SpeechRequest,
    authorization: Optional[str] = Header(default=None),
):
    # Auth is optional locally; Railway/ngrok may pass a bearer key we ignore.
    _ = authorization
    text = (body.input or "").strip()
    if not text:
        raise HTTPException(400, "input is required")

    lang = (body.language or LANGUAGE).strip() or "es"
    prompt = (body.audio_prompt_path or VOICE_REF or "").strip() or None
    exaggeration = body.exaggeration if body.exaggeration is not None else DEFAULT_EXAG
    cfg_weight = body.cfg_weight if body.cfg_weight is not None else DEFAULT_CFG
    fmt = (body.response_format or "wav").lower()
    if fmt not in ("wav", "pcm"):
        # Coach asks for wav; refuse exotic formats rather than lie.
        raise HTTPException(400, f"unsupported response_format: {fmt}")

    model = get_model()
    t0 = time.time()
    kwargs: dict[str, Any] = {
        "language_id": lang,
        "exaggeration": exaggeration,
        "cfg_weight": cfg_weight,
    }
    if prompt:
        kwargs["audio_prompt_path"] = prompt

    with _lock:
        try:
            wav = model.generate(text, **kwargs)
        except TypeError:
            # Older chatterbox builds may not take exaggeration/cfg on multilingual.
            kwargs.pop("exaggeration", None)
            kwargs.pop("cfg_weight", None)
            wav = model.generate(text, **kwargs)

    if isinstance(wav, torch.Tensor):
        audio_np = wav.detach().float().cpu().numpy()
    else:
        audio_np = np.asarray(wav, dtype=np.float32)
    if audio_np.ndim > 1:
        # (channels, samples) -> (samples, channels) for soundfile
        audio_np = np.squeeze(audio_np)
        if audio_np.ndim > 1 and audio_np.shape[0] <= 8:
            audio_np = audio_np.T

    buf = io.BytesIO()
    sf.write(buf, audio_np, int(model.sr), format="WAV", subtype="PCM_16")
    audio = buf.getvalue()
    print(
        f"[chatterbox-es] gen ok lang={lang} chars={len(text)} "
        f"sec={time.time() - t0:.2f} bytes={len(audio)}",
        flush=True,
    )
    return Response(content=audio, media_type="audio/wav")


@app.post("/v1/load")
def load_model():
    get_model()
    return JSONResponse({"ok": True, "model": MODEL_ID, "loaded_at": _loaded_at})


if __name__ == "__main__":
    # Warm on boot so the first coach speech isn't a cold download.
    try:
        get_model()
    except Exception as e:
        print(f"[chatterbox-es] warm-load failed (will retry on first request): {e}", flush=True)
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")
