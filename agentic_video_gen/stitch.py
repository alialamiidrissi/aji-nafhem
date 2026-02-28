"""
Video stitching utilities for multi-scene projects.

Each scene video has a leading black buffer (~0.5s) that is trimmed before
concatenation. The trim point is detected by ffmpeg's blackdetect filter,
making it robust to changes in the buffer duration.
"""
import re
import subprocess
import tempfile
from pathlib import Path


def find_scene_videos(project_dir: Path) -> list[Path]:
    """Find rendered_video.mp4 in each scene dir, sorted by scene_index.

    Reads project_info.json to determine scene order, then resolves each
    scene dir. Only scenes that have a rendered_video.mp4 are included.
    """
    import json
    from agentic_video_gen.pipeline import RUNS_DIR

    info_path = project_dir / "project_info.json"
    if not info_path.exists():
        raise FileNotFoundError(f"project_info.json not found in {project_dir}")

    info = json.loads(info_path.read_text(encoding="utf-8"))
    videos: list[Path] = []

    for entry in sorted(info["scenes"], key=lambda s: s["scene_index"]):
        scene_dir = RUNS_DIR / entry["scene_dir"]
        video = scene_dir / "rendered_video.mp4"
        if video.exists():
            videos.append(video)
        else:
            print(f"[stitch] Warning: no rendered_video.mp4 for scene {entry['scene_index']} at {scene_dir}")

    return videos


def find_leading_black_end(video_path: Path, pix_threshold: float = 0.1) -> float:
    """Detect the end timestamp of the leading black section at video start.

    Uses ffmpeg's blackdetect filter with d=0 to catch even sub-frame black
    sections. Parses stderr for a black_start:0 line and returns its black_end.

    Returns 0.0 if no leading black section is found or ffmpeg fails.
    """
    cmd = [
        "ffmpeg",
        "-i", str(video_path),
        "-vf", f"blackdetect=d=0:pix_th={pix_threshold}",
        "-f", "null",
        "-",
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
        )
        # ffmpeg writes filter output to stderr
        stderr = result.stderr

        # Look for a blackdetect event that starts at 0
        # Format: black_start:0 black_end:0.5333... black_duration:...
        pattern = r"black_start:([\d.]+)\s+black_end:([\d.]+)"
        for match in re.finditer(pattern, stderr):
            start = float(match.group(1))
            end = float(match.group(2))
            if start < 0.05:  # starts at (or very near) the beginning
                return end

    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        print(f"[stitch] Warning: blackdetect failed for {video_path}: {e}")

    return 0.0


def stitch_project_videos(
    project_dir: Path,
    output_path: Path | None = None,
    pix_threshold: float = 0.1,
) -> Path:
    """Trim leading black from each scene video and concatenate them.

    Steps:
      1. Find all rendered_video.mp4 files via find_scene_videos()
      2. For each, detect leading black end with find_leading_black_end()
      3. Trim with: ffmpeg -ss {trim} -i scene.mp4 -c copy trimmed.mp4
      4. Concatenate all trimmed clips with ffmpeg concat demuxer
      5. Write to project_dir/stitched_video.mp4 (or output_path)

    Returns the path of the stitched video.
    """
    if output_path is None:
        output_path = project_dir / "stitched_video.mp4"

    videos = find_scene_videos(project_dir)
    if not videos:
        raise ValueError(f"No rendered scene videos found in project {project_dir}")

    print(f"[stitch] Found {len(videos)} scene video(s) to stitch.")

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        trimmed_clips: list[Path] = []

        for i, video in enumerate(videos):
            trim_point = find_leading_black_end(video, pix_threshold=pix_threshold)
            trimmed = tmp_path / f"trimmed_{i}.mp4"

            print(f"[stitch] Scene {i+1}: trim={trim_point:.3f}s → {video.name}")

            trim_cmd = [
                "ffmpeg", "-y",
                "-ss", str(trim_point),
                "-i", str(video),
                "-c", "copy",
                str(trimmed),
            ]
            result = subprocess.run(trim_cmd, capture_output=True, text=True)
            if result.returncode != 0:
                raise RuntimeError(
                    f"ffmpeg trim failed for {video}:\n{result.stderr}"
                )
            trimmed_clips.append(trimmed)

        # Write concat list file
        concat_list = tmp_path / "concat_list.txt"
        with open(concat_list, "w") as f:
            for clip in trimmed_clips:
                f.write(f"file '{clip}'\n")

        # Concatenate
        concat_cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(concat_list),
            "-c", "copy",
            str(output_path),
        ]
        print(f"[stitch] Concatenating {len(trimmed_clips)} clips → {output_path}")
        result = subprocess.run(concat_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(
                f"ffmpeg concat failed:\n{result.stderr}"
            )

    print(f"[stitch] Done → {output_path}")
    return output_path
