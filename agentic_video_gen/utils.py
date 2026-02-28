import os
import requests
from pathlib import Path

def setup_assets_impl(assets_path, assets_dict):
    """
    Writes the raw SVGs to the assets folder so Manim can load them.
    """
    os.makedirs(str(assets_path), exist_ok=True)
    for name, content in assets_dict.items():
        with open(os.path.join(assets_path, name), "w", encoding="utf-8") as f:
            f.write(content)


def _write_silence(file_path: Path):
    """Write a 1-second silent WAV so Manim can compile even when TTS is unavailable."""
    import numpy as np
    import soundfile as sf
    sf.write(str(file_path), np.zeros(44100), 44100)


def _tts_local(text: str, file_path: Path):
    response = requests.post("http://localhost:8000/tts", data={"text": text})
    response.raise_for_status()
    with open(file_path, "wb") as f:
        f.write(response.content)


def _tts_elevenlabs(text: str, file_path: Path):
    api_key = os.environ.get("ELEVENLABS_API_KEY")
    if not api_key:
        raise RuntimeError("ELEVENLABS_API_KEY is not set")

    voice_id = os.environ.get("ELEVENLABS_VOICE_ID", "cgSgspJ2msm6clMCkdW9")
    model_id = os.environ.get("ELEVENLABS_MODEL_ID", "eleven_multilingual_v2")

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {
        "xi-api-key": api_key,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }
    payload = {
        "text": text,
        "model_id": model_id,
        "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
    }
    response = requests.post(url, headers=headers, json=payload, timeout=60)
    response.raise_for_status()

    # ElevenLabs returns mp3; convert to wav so Manim/soundfile handles it uniformly
    import io
    from pydub import AudioSegment
    audio = AudioSegment.from_file(io.BytesIO(response.content), format="mp3")
    audio.export(str(file_path), format="wav")


def generate_sounds_from_api(segments, out_path, tts_provider: str = "local"):
    """
    Generates a .wav file per segment using the chosen TTS provider.

    tts_provider:
      "local"       — local Coqui XTTS server at http://localhost:8000 (default)
      "elevenlabs"  — ElevenLabs API (requires ELEVENLABS_API_KEY)
    """
    out_path = Path(out_path)
    out_path.mkdir(parents=True, exist_ok=True)

    _tts_fn = _tts_elevenlabs if tts_provider == "elevenlabs" else _tts_local

    for seg in segments:
        file_path = out_path / f"{seg.id}.wav"
        print(f"Generating audio [{tts_provider}] for {seg.id} -> {file_path}")
        try:
            _tts_fn(seg.script, file_path)
        except Exception as e:
            print(f"Error generating TTS for {seg.id}: {e}")
            print(f"Creating silent fallback for {seg.id}.")
            _write_silence(file_path)
