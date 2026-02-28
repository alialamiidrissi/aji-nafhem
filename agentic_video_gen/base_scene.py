import os
from pathlib import Path
from manim import *
from contextlib import contextmanager
import soundfile as sf
from agentic_video_gen.utils import setup_assets_impl


class BaseEducationalScene(Scene):
    """
    Base class for all generated Manim scenes.

    Reads the run directory from the MANIM_RUN_DIR environment variable,
    which the pipeline sets before invoking manim. This allows each run's
    assets/ and audios/ to be self-contained under a unique UUID folder.

    If MANIM_RUN_DIR is not set, falls back to a default path for manual use.
    """

    def setup(self):
        run_dir = os.environ.get("MANIM_RUN_DIR")
        if run_dir:
            base = Path(run_dir)
        else:
            # Fallback for manual manim invocation
            base = Path("agentic_video_gen/runs/latest")

        self.asset_path = base / "assets"
        self.out_path = base / "audios"

    def setup_assets(self):
        """Ensures the assets folder exists. SVGs are pre-written by the pipeline."""
        self.asset_path.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def speech(self, audio_id):
        """
        Context manager that plays TTS audio for the given segment id and
        waits exactly for its duration so animations stay in sync.
        """
        path = str(self.out_path / f"{audio_id}.wav")
        duration = 2.0  # safe fallback

        try:
            start_time = self.renderer.time
            if os.path.exists(path):
                with sf.SoundFile(path) as f:
                    duration = len(f) / f.samplerate
                self.add_sound(path)
            else:
                print(f"[BaseScene] Warning: audio file not found: {path}. Using {duration}s fallback.")

            yield duration

        finally:
            elapsed = self.renderer.time - start_time
            remaining = duration - elapsed
            if remaining > 0:
                self.wait(remaining)

    def get_svg(self, name, **kwargs):
        """
        Loads an SVGMobject from this run's assets directory.
        Falls back to a placeholder Square if the file is missing.
        """
        svg_path = self.asset_path / name
        if not svg_path.exists():
            print(f"[BaseScene] Warning: SVG not found: {svg_path}. Using placeholder.")
            return Square(**kwargs)
        return SVGMobject(str(svg_path), **kwargs)
