import io
import os
import tempfile
from typing import Optional
from pathlib import Path

os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
os.environ["PYTORCH_ENABLE_MPS_FALLBACK"] = "1"

import torch
torch.set_num_threads(1)

import shutil
import uvicorn
import numpy as np
import scipy.io.wavfile as wavfile
from fastapi import FastAPI, HTTPException, UploadFile, Form
from fastapi.responses import StreamingResponse
from TTS.tts.configs.xtts_config import XttsConfig
from TTS.tts.models.xtts import Xtts

app = FastAPI(title="Darija XTTS API")

base_path = Path(__file__).parent / "model"
model_path = base_path / 'model.pth'
config_path = base_path / 'config.json'
vocab_path = base_path / 'vocab.json'

config = XttsConfig()
config.load_json(str(config_path))
device = "mps"

print(f"Loading model to {device}...")
model = Xtts.init_from_config(config)
model.load_checkpoint(config, checkpoint_path=str(model_path), vocab_path=str(vocab_path), eval=True)
model.to(device)


@app.post("/tts")
async def text_to_speech(
    text: str = Form(...),
    temperature: float = Form(0.65),
    speaker_file: Optional[UploadFile] = None,
):
    try:
        if speaker_file is None:
            # Use the default reference speaker directly from disk
            speaker_path = str(base_path / "speaker_reference.wav")
            gpt_cond_latent, speaker_embedding = model.get_conditioning_latents(
                audio_path=[speaker_path]
            )
        else:
            # Write the uploaded speaker to a NamedTemporaryFile.
            # delete=True + context manager guarantees cleanup even on crash.
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as tmp_speaker:
                shutil.copyfileobj(speaker_file.file, tmp_speaker)
                tmp_speaker.flush()
                gpt_cond_latent, speaker_embedding = model.get_conditioning_latents(
                    audio_path=[tmp_speaker.name]
                )
            # tmp_speaker is deleted here automatically

        # Run inference
        out = model.inference(
            text,
            "ar",
            gpt_cond_latent,
            speaker_embedding,
            temperature=temperature,
        )

        # Write WAV entirely into memory — no disk write
        buffer = io.BytesIO()
        wavfile.write(buffer, 24000, out["wav"])
        buffer.seek(0)

        return StreamingResponse(
            buffer,
            media_type="audio/wav",
            headers={"Content-Disposition": "attachment; filename=result.wav"},
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run(app, port=8000)