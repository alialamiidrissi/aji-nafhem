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
        """
        Ensures the assets folder exists and emits a short silent buffer.
        The buffer frames sit before any audio and prevent Manim's encoder
        from clipping the very start of the first TTS segment.
        """
        self.asset_path.mkdir(parents=True, exist_ok=True)
        self.wait(0.5)

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
                self.wait(remaining+0.2)

    def fit_to_frame(self, mob, margin=0.7):
        """
        Scales a mobject down (never up) so that it fits within the visible
        frame with the given margin on each side. Call this before adding any
        Text, SVG, or VGroup to the scene to prevent objects from going
        off-screen.
        """
        max_w = config.frame_width - margin * 2
        max_h = config.frame_height - margin * 2
        if mob.width > max_w:
            mob.scale_to_fit_width(max_w)
        if mob.height > max_h:
            mob.scale_to_fit_height(max_h)
        return mob

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

    def get_image(self, name, **kwargs):
        """
        Loads an ImageMobject (PNG/JPG) from this run's assets directory.
        Falls back to a placeholder Rectangle if the file is missing.

        Always call scale_to_fit_width() or scale_to_fit_height() immediately
        after loading — ImageMobject default size depends on pixel dimensions.
        Example (full frame):
            map_img = self.get_image("middle_east_map.png")
            map_img.scale_to_fit_width(config.frame_width)
        """
        img_path = self.asset_path / name
        if not img_path.exists():
            print(f"[BaseScene] Warning: image not found: {img_path}. Using placeholder.")
            return Rectangle(width=config.frame_width, height=config.frame_height, **kwargs)
        return ImageMobject(str(img_path), **kwargs)
