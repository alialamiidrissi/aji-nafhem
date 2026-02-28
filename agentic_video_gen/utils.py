import os
import json
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

def generate_sounds_from_api(segments, out_path):
    """
    Calls the local TTS API for each segment and generates a .wav file.
    """
    out_path = Path(out_path)
    out_path.mkdir(parents=True, exist_ok=True)
    
    for seg in segments:
        file_path = out_path / f"{seg.id}.wav"
        print(f"Generating audio for {seg.id} -> {file_path}")
        
        try:
            response = requests.post("http://localhost:8000/tts", data={"text": seg.script})
            response.raise_for_status()
            with open(file_path, "wb") as f:
                f.write(response.content)
        except Exception as e:
            print(f"Error generating TTS for {seg.id}: {e}")
            # Create dummy file to allow Manim to compile even if TTS is offline
            print(f"Creating dummy audio file for {seg.id} to allow Manim compilation.")
            import numpy as np
            import soundfile as sf
            # 1 second of silence
            sf.write(str(file_path), np.zeros(44100), 44100)
