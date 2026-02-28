"""
Gradio UI for the Agentic Video Generation pipeline.
Streams live logs and displays the final rendered video.
"""
import os
import sys
import uuid
import shutil
import queue
import threading
import subprocess
from pathlib import Path

import gradio as gr
from dotenv import load_dotenv

load_dotenv()

MANIM_BIN = "/Users/aalamiid/miniconda3/envs/audio_tts/bin/manim"
PROJECT_DIR = Path(__file__).parent
RUNS_DIR = PROJECT_DIR / "agentic_video_gen" / "runs"
DEFAULT_AUDIENCE = "high school student"

STEP_CHOICES = [
    "1 — Analytical Solver",
    "2 — Script & TTS",
    "3 — SVG Assets",
    "4 — Manim Code",
    "5 — Compile & Fix",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _QueueWriter:
    """Redirect writes to a thread-safe queue."""
    def __init__(self, q: queue.Queue):
        self._q = q

    def write(self, text: str):
        if text:
            self._q.put(text)

    def flush(self):
        pass


def _read_run_info(run_dir: Path) -> dict | None:
    """Return {'query': ..., 'audience': ...} for a run dir, or None if missing."""
    info_json = run_dir / "run_info.json"
    info_txt = run_dir / "run_info.txt"
    if info_json.exists():
        import json
        data = json.loads(info_json.read_text(encoding="utf-8"))
        return {"query": data.get("query", ""), "audience": data.get("audience", DEFAULT_AUDIENCE)}
    elif info_txt.exists():
        info = {}
        for line in info_txt.read_text(encoding="utf-8").splitlines():
            if ": " in line:
                k, v = line.split(": ", 1)
                info[k.strip()] = v.strip()
        return {"query": info.get("Query", ""), "audience": info.get("Audience", DEFAULT_AUDIENCE)}
    return None


def _list_runs() -> list[str]:
    """Return run choices as 'run_id — query' strings, newest first.

    Skips the projects/ subdirectory so project scenes don't appear here.
    """
    if not RUNS_DIR.exists():
        return []
    choices = []
    for d in sorted(RUNS_DIR.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if not d.is_dir():
            continue
        if d.name == "projects":  # skip multi-scene project dirs
            continue
        info = _read_run_info(d)
        if info is None:
            continue
        query_preview = info["query"].replace("\n", " ")[:70]
        choices.append(f"{d.name} — {query_preview}")
    return choices


def _parse_run_choice(choice: str) -> str:
    """Extract the run_id (UUID) from a 'run_id — query' choice string."""
    return choice.split(" — ")[0].strip()


def _parse_step_choice(choice: str) -> int:
    """Extract the step number from a '3 — SVG Assets' choice string."""
    return int(choice.split(" — ")[0].strip())


_CHECKPOINT_FILES = {
    1: "checkpoint_step1_solved.json",
    2: "checkpoint_step2_script.json",
    3: "checkpoint_step3_svgs.json",
    4: "checkpoint_step4_manim.json",
}


def _fork_run_dir(src_dir: Path, from_step: int) -> tuple[str, Path]:
    """
    Create a new run directory forked from src_dir.

    Copies checkpoints for steps < from_step, plus the associated generated
    artifacts (audios/, assets/, generated_scene.py) so the new run can
    seamlessly resume without touching the original.

    Returns (new_run_id, new_run_dir).
    """
    new_id = str(uuid.uuid4())
    dst_dir = RUNS_DIR / new_id
    dst_dir.mkdir(parents=True)
    (dst_dir / "assets").mkdir()
    (dst_dir / "audios").mkdir()

    # Copy checkpoints for every step that will be skipped
    for step in range(1, from_step):
        fname = _CHECKPOINT_FILES.get(step)
        if fname and (src_dir / fname).exists():
            shutil.copy2(src_dir / fname, dst_dir / fname)

    # Step 2 generates audios — needed if we're resuming at step 3+
    if from_step > 2 and (src_dir / "audios").exists():
        shutil.copytree(src_dir / "audios", dst_dir / "audios", dirs_exist_ok=True)

    # Step 3 generates assets — needed if we're resuming at step 4+
    if from_step > 3 and (src_dir / "assets").exists():
        shutil.copytree(src_dir / "assets", dst_dir / "assets", dirs_exist_ok=True)

    # Step 4 generates the scene file — needed if we're resuming at step 5
    if from_step > 4 and (src_dir / "generated_scene.py").exists():
        shutil.copy2(src_dir / "generated_scene.py", dst_dir / "generated_scene.py")

    return new_id, dst_dir


# ---------------------------------------------------------------------------
# Thread workers
# ---------------------------------------------------------------------------

def _run_pipeline_thread(
    query: str,
    audience: str,
    log_q: queue.Queue,
    result_box: dict,
    run_id: str | None = None,
    from_step: int = 1,
    nudges: dict | None = None,
    force_fix_prompt: str | None = None,
    force_fix_image: str | None = None,
    model_provider: str = "google",
    tts_provider: str = "local",
):
    """Target for the pipeline thread. Captures stdout into log_q."""
    orig_stdout = sys.stdout
    orig_stderr = sys.stderr
    writer = _QueueWriter(log_q)
    sys.stdout = writer
    sys.stderr = writer
    try:
        from agentic_video_gen.pipeline import run_pipeline
        run_dir = run_pipeline(
            query,
            audience_level=audience,
            run_id=run_id,
            from_step=from_step,
            nudges=nudges or None,
            force_fix_prompt=force_fix_prompt or None,
            force_fix_image=force_fix_image or None,
            model_provider=model_provider,
            tts_provider=tts_provider,
        )
        result_box["run_dir"] = run_dir
    except Exception as exc:
        log_q.put(f"\n❌ Pipeline error: {exc}\n")
        import traceback
        log_q.put(traceback.format_exc())
        result_box["error"] = str(exc)
    finally:
        sys.stdout = orig_stdout
        sys.stderr = orig_stderr
        log_q.put(None)  # sentinel


def _run_render_thread(run_dir: Path, log_q: queue.Queue, result_box: dict):
    """Render the Manim scene and stream its output into log_q."""
    out_file = run_dir / "generated_scene.py"
    run_env = {**os.environ, "MANIM_RUN_DIR": str(run_dir.resolve())}

    log_q.put(f"\n[Render] Running: manim -qm {out_file} GeneratedEducationalScene\n")

    proc = subprocess.Popen(
        [MANIM_BIN, "-qm", str(out_file), "GeneratedEducationalScene", "--disable_caching"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=run_env,
        cwd=str(PROJECT_DIR),
    )

    for line in proc.stdout:
        log_q.put(line)

    proc.wait()
    if proc.returncode == 0:
        video_path = PROJECT_DIR / "media/videos/generated_scene/720p30/GeneratedEducationalScene.mp4"
        if video_path.exists():
            # Persist a copy next to the run artifacts for stitching and resumption
            shutil.copy2(video_path, run_dir / "rendered_video.mp4")
            result_box["video"] = str(video_path)
            log_q.put(f"\n✅ Render complete → {video_path}\n")
        else:
            log_q.put("\n⚠️  Render succeeded but video file not found at expected path.\n")
    else:
        log_q.put(f"\n❌ Render failed (exit code {proc.returncode}).\n")

    log_q.put(None)  # sentinel


# ---------------------------------------------------------------------------
# Shared generator: stream pipeline then render
# ---------------------------------------------------------------------------

def _stream_pipeline_and_render(
    query: str,
    audience: str,
    run_id: str | None = None,
    from_step: int = 1,
    nudges: dict | None = None,
    force_fix_prompt: str | None = None,
    force_fix_image: str | None = None,
    model_provider: str = "google",
    tts_provider: str = "local",
):
    """Generator: runs pipeline thread, then render thread, yielding (logs, video, done)."""
    log_q: queue.Queue = queue.Queue()
    result_box: dict = {}
    accumulated = ""

    t = threading.Thread(
        target=_run_pipeline_thread,
        args=(query, audience, log_q, result_box),
        kwargs={"run_id": run_id, "from_step": from_step, "nudges": nudges, "force_fix_prompt": force_fix_prompt, "force_fix_image": force_fix_image, "model_provider": model_provider, "tts_provider": tts_provider},
        daemon=True,
    )
    t.start()

    yield "Starting pipeline...\n", gr.update(visible=False), gr.update(visible=False)

    while True:
        try:
            msg = log_q.get(timeout=0.2)
        except queue.Empty:
            yield accumulated, gr.update(visible=False), gr.update(visible=False)
            continue
        if msg is None:
            break
        accumulated += msg
        yield accumulated, gr.update(visible=False), gr.update(visible=False)

    t.join()

    if "error" in result_box:
        yield accumulated, gr.update(visible=False), gr.update(visible=False)
        return

    run_dir: Path = result_box["run_dir"]

    log_q2: queue.Queue = queue.Queue()
    result_box2: dict = {}

    t2 = threading.Thread(
        target=_run_render_thread,
        args=(run_dir, log_q2, result_box2),
        daemon=True,
    )
    t2.start()

    while True:
        try:
            msg = log_q2.get(timeout=0.2)
        except queue.Empty:
            yield accumulated, gr.update(visible=False), gr.update(visible=False)
            continue
        if msg is None:
            break
        accumulated += msg
        yield accumulated, gr.update(visible=False), gr.update(visible=False)

    t2.join()

    if "video" in result_box2:
        yield accumulated, gr.update(visible=True, value=result_box2["video"]), gr.update(visible=True)
    else:
        yield accumulated, gr.update(visible=False), gr.update(visible=False)


# ---------------------------------------------------------------------------
# Gradio entry points
# ---------------------------------------------------------------------------

def generate_video(query: str, audience: str, model_provider: str = "google", tts_provider: str = "local"):
    """New run: start from step 1."""
    if not query.strip():
        yield "Please enter a topic.", gr.update(visible=False), gr.update(visible=False)
        return
    yield from _stream_pipeline_and_render(query, audience, model_provider=model_provider, tts_provider=tts_provider)


def _run_preview(run_choice: str) -> str:
    """Return a markdown summary of the selected run for display."""
    if not run_choice:
        return "*Select a run to see its details.*"

    run_id = _parse_run_choice(run_choice)
    run_dir = RUNS_DIR / run_id
    info = _read_run_info(run_dir)
    if info is None:
        return f"*No run_info.json found for `{run_id}`.*"

    completed = []
    checkpoints = {
        1: "checkpoint_step1_solved.json",
        2: "checkpoint_step2_script.json",
        3: "checkpoint_step3_svgs.json",
        4: "checkpoint_step4_manim.json",
    }
    step_names = {1: "Solver", 2: "Script", 3: "SVGs", 4: "Manim"}
    for s, fname in checkpoints.items():
        if (run_dir / fname).exists():
            completed.append(f"✅ Step {s} — {step_names[s]}")
        else:
            completed.append(f"⬜ Step {s} — {step_names[s]}")

    has_scene = "✅" if (run_dir / "generated_scene.py").exists() else "⬜"
    video_path = run_dir / "rendered_video.mp4"
    if video_path.exists():
        video =  gr.update(value=str(video_path))
    else:
        video = gr.update(value = None)
    return (
        f"**Run ID:** `{run_id}`\n\n"
        f"**Query:** {info['query']}\n\n"
        f"**Audience:** {info['audience']}\n\n"
        f"**Checkpoints:**\n"
        + "\n".join(f"- {c}" for c in completed)
        + f"\n- {has_scene} generated_scene.py",
        video

    )


def resume_video(run_choice: str, step_choice: str, copy_run: bool, n1: str, n2: str, n3: str, n4: str, force_fix: str, force_fix_image: str | None = None, model_provider: str = "google", tts_provider: str = "local"):
    """Resume an existing run from the selected step, with optional per-step nudges."""
    if not run_choice:
        yield "Please select a run.", gr.update(visible=False), gr.update(visible=False)
        return

    run_id = _parse_run_choice(run_choice)
    from_step = _parse_step_choice(step_choice)

    run_dir = RUNS_DIR / run_id
    info = _read_run_info(run_dir)
    if info is None:
        yield f"❌ run_info.json not found for run {run_id}.", gr.update(visible=False), gr.update(visible=False)
        return

    query = info["query"]
    audience = info["audience"]

    if copy_run:
        run_id, run_dir = _fork_run_dir(run_dir, from_step)
        yield f"[Fork] Copied to new run: {run_id}\n", gr.update(visible=False), gr.update(visible=False)

    nudges = {k: v for k, v in {1: n1, 2: n2, 3: n3, 4: n4}.items() if v and v.strip()} or None

    yield from _stream_pipeline_and_render(
        query, audience,
        run_id=run_id, from_step=from_step,
        nudges=nudges,
        force_fix_prompt=force_fix.strip() or None,
        force_fix_image=force_fix_image or None,
        model_provider=model_provider,
        tts_provider=tts_provider,
    )


# ---------------------------------------------------------------------------
# Multi-Scene Project helpers
# ---------------------------------------------------------------------------

import json as _json  # local alias to avoid shadowing

PROJECTS_DIR = RUNS_DIR / "projects"


def _list_projects() -> list[str]:
    """Return project choices as 'project_id — N scenes' strings, newest first."""
    if not PROJECTS_DIR.exists():
        return []
    choices = []
    for d in sorted(PROJECTS_DIR.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if not d.is_dir():
            continue
        info_path = d / "project_info.json"
        if not info_path.exists():
            continue
        try:
            info = _json.loads(info_path.read_text(encoding="utf-8"))
            n = len(info.get("scenes", []))
            choices.append(f"{info['project_id']} — {n} scene(s)")
        except Exception:
            pass
    return choices


def _parse_project_choice(choice: str) -> str:
    """Extract project_id from 'project_id — N scene(s)' string."""
    return choice.split(" — ")[0].strip()


def _get_scene_choices(project_choice: str) -> list[str]:
    """Return sorted list of scene index strings for the selected project."""
    if not project_choice:
        return []
    try:
        pid = _parse_project_choice(project_choice)
        info_path = PROJECTS_DIR / pid / "project_info.json"
        if not info_path.exists():
            return []
        info = _json.loads(info_path.read_text(encoding="utf-8"))
        return [str(s["scene_index"]) for s in sorted(info.get("scenes", []), key=lambda s: s["scene_index"])]
    except Exception:
        return []


def _render_project_markdown(project_dir: Path) -> str:
    """Build a rich HTML/markdown summary of the project's scene list.

    Each scene gets collapsible <details> blocks for its full query,
    solver result, and voiceover script.
    """
    if not project_dir.exists():
        return "*Project directory not found.*"
    info_path = project_dir / "project_info.json"
    if not info_path.exists():
        return "*project_info.json not found.*"

    info = _json.loads(info_path.read_text(encoding="utf-8"))
    scenes = info.get("scenes", [])
    carry = info.get("carry_solver_context", False)
    audience = info.get("audience", "—")

    parts = [
        f"**Project:** `{info['project_id']}`  |  **Audience:** {audience}  |  "
        f"**Carry solver context:** {'Yes' if carry else 'No'}\n"
    ]

    if not scenes:
        parts.append("*No scenes yet. Add a scene below.*")
        return "\n".join(parts)

    for entry in scenes:
        idx = entry["scene_index"]
        source = entry.get("source", "native")
        query_text = entry.get("query", "—")
        scene_dir = RUNS_DIR / entry["scene_dir"]

        has_video = (scene_dir / "rendered_video.mp4").exists()
        has_script = (scene_dir / "checkpoint_step2_script.json").exists()
        has_solver = (scene_dir / "checkpoint_step1_solved.json").exists()

        status = "✅" if has_video else ("🔄" if has_script else "⬜")
        cp_badges = "  ".join(
            ("✅" if (scene_dir / fname).exists() else "⬜") + label
            for fname, label in [
                ("checkpoint_step1_solved.json", "solver"),
                ("checkpoint_step2_script.json", "script"),
                ("checkpoint_step3_svgs.json", "svgs"),
                ("checkpoint_step4_manim.json", "manim"),
            ]
        )

        block = [
            f"---",
            f"### Scene {idx} {status} &nbsp; <small>`{source}`</small>",
            f"{cp_badges}",
            "",
        ]

        # ── Query accordion ──
        block.append(
            f"<details><summary><b>Query</b></summary>\n\n{query_text}\n\n</details>"
        )

        # ── Solver result accordion ──
        if has_solver:
            try:
                solver = _json.loads(
                    (scene_dir / "checkpoint_step1_solved.json").read_text(encoding="utf-8")
                )
                topic = solver.get("topic", "—")
                steps_html = "\n".join(
                    f"<li><b>Step {s['step_number']} — {s['concept']}</b><br>{s['description']}</li>"
                    for s in solver.get("steps", [])
                )
                block.append(
                    f"<details><summary><b>Solver result</b> — {topic}</summary>"
                    f"\n\n<ol>{steps_html}</ol>\n\n</details>"
                )
            except Exception:
                block.append("<details><summary><b>Solver result</b></summary><i>Could not load.</i></details>")
        else:
            block.append("<details><summary><b>Solver result</b></summary><i>Not yet generated.</i></details>")

        # ── Script accordion ──
        if has_script:
            try:
                script = _json.loads(
                    (scene_dir / "checkpoint_step2_script.json").read_text(encoding="utf-8")
                )
                segs_html = "\n".join(
                    f"<li><b>[{s['id']}]</b> {s['script']}<br><i>Visual: {s['visual_action']}</i></li>"
                    for s in script.get("segments", [])
                )
                block.append(
                    f"<details><summary><b>Voiceover script</b> "
                    f"({len(script.get('segments', []))} segments)</summary>"
                    f"\n\n<ol>{segs_html}</ol>\n\n</details>"
                )
            except Exception:
                block.append("<details><summary><b>Voiceover script</b></summary><i>Could not load.</i></details>")
        else:
            block.append("<details><summary><b>Voiceover script</b></summary><i>Not yet generated.</i></details>")

        parts.append("\n".join(block))

    return "\n\n".join(parts)


def _list_importable_sources() -> list[str]:
    """All standalone runs + all project scenes, formatted for import dropdown."""
    sources: list[str] = []

    # Standalone runs
    if RUNS_DIR.exists():
        for d in sorted(RUNS_DIR.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            if not d.is_dir() or d.name == "projects":
                continue
            info = _read_run_info(d)
            if info is None:
                continue
            query_preview = info["query"].replace("\n", " ")[:50]
            sources.append(f"run:{d.name} — {query_preview}")

    # Project scenes
    if PROJECTS_DIR.exists():
        for proj_d in sorted(PROJECTS_DIR.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            if not proj_d.is_dir():
                continue
            info_path = proj_d / "project_info.json"
            if not info_path.exists():
                continue
            try:
                proj_info = _json.loads(info_path.read_text(encoding="utf-8"))
                for entry in proj_info.get("scenes", []):
                    scene_dir = RUNS_DIR / entry["scene_dir"]
                    if (scene_dir / "run_info.json").exists():
                        query_preview = entry.get("query", "—")[:40]
                        sources.append(
                            f"scene:{entry['scene_dir']} — {proj_info['project_id']} #{entry['scene_index']} — {query_preview}"
                        )
            except Exception:
                pass

    return sources


def _parse_import_source(source_choice: str) -> Path:
    """Convert an import source choice string to an absolute Path."""
    # Formats: "run:{uuid} — ..." or "scene:{rel_path} — ..."
    _, rest = source_choice.split(":", 1)
    path_part = rest.split(" — ")[0].strip()
    return (RUNS_DIR / path_part).resolve()


# ---------------------------------------------------------------------------
# Project UI action functions (called from Gradio event handlers)
# ---------------------------------------------------------------------------

def _new_project_ui(audience: str, carry_solver: bool) -> tuple[str, str]:
    """Create a new project. Returns (status_msg, new_project_choice)."""
    from agentic_video_gen.projects import create_project
    try:
        project_id, _ = create_project(audience, carry_solver)
        choice = f"{project_id} — 0 scene(s)"
        return f"✅ Created project `{project_id}`", choice
    except Exception as e:
        return f"❌ Error: {e}", ""


def _fork_project_ui(project_choice: str) -> tuple[str, str]:
    """Fork a project. Returns (status_msg, new_project_choice)."""
    if not project_choice:
        return "Please select a project first.", ""
    from agentic_video_gen.projects import fork_project
    project_id = _parse_project_choice(project_choice)
    project_dir = PROJECTS_DIR / project_id
    try:
        new_id, new_dir = fork_project(project_dir)
        choice = f"{new_id} — {len(_json.loads((new_dir / 'project_info.json').read_text())['scenes'])} scene(s)"
        return f"✅ Forked to `{new_id}`", choice
    except Exception as e:
        return f"❌ Error: {e}", ""


def _remove_scene_ui(project_choice: str, scene_index_str: str) -> tuple[str, str]:
    """Remove a scene from the project."""
    if not project_choice or not scene_index_str:
        return "Select a project and scene index.", ""
    from agentic_video_gen.projects import remove_scene
    project_id = _parse_project_choice(project_choice)
    project_dir = PROJECTS_DIR / project_id
    try:
        idx = int(scene_index_str)
        remove_scene(project_dir, idx)
        md = _render_project_markdown(project_dir)
        return f"✅ Removed scene {idx}.", md
    except Exception as e:
        return f"❌ Error: {e}", ""


def _import_scene_ui(
    project_choice: str,
    source_choice: str,
    query_override: str,
    scene_index_override: float | None = None,
) -> tuple[str, str]:
    """Import an existing run/scene into the project as the next scene."""
    if not project_choice or not source_choice:
        return "Select a project and source.", ""
    from agentic_video_gen.projects import import_scene, load_project_info, _shift_scenes_up
    project_id = _parse_project_choice(project_choice)
    project_dir = PROJECTS_DIR / project_id
    try:
        info = load_project_info(project_dir)
        if scene_index_override is not None:
            target_idx = int(scene_index_override)
            existing = {s["scene_index"] for s in info["scenes"]}
            if target_idx in existing:
                _shift_scenes_up(project_dir, target_idx)
        else:
            target_idx = max((s["scene_index"] for s in info["scenes"]), default=0) + 1
        source_path = _parse_import_source(source_choice)
        import_scene(
            project_dir,
            target_idx,
            source_path,
            query_override=query_override.strip() or None,
        )
        md = _render_project_markdown(project_dir)
        return f"✅ Imported as scene {target_idx}.", md
    except Exception as e:
        return f"❌ Error: {e}", ""


def _run_project_scene_ui(
    project_choice: str,
    scene_query: str,
    from_step_str: str,
    nudges_dict: dict,
    log_q: "queue.Queue",
    result_box: dict,
    scene_index: int | None = None,
    force_fix_prompt: str | None = None,
    force_fix_image: str | None = None,
    insert_shift: bool = False,
    model_provider: str = "google",
    tts_provider: str = "local",
):
    """Thread target: run a project scene and stream logs.

    If scene_index is None, appends as the next scene.
    If scene_index is given, re-runs that existing scene in place.
    """
    from agentic_video_gen.projects import run_project_scene, load_project_info

    orig_stdout = sys.stdout
    orig_stderr = sys.stderr
    writer = _QueueWriter(log_q)
    sys.stdout = writer
    sys.stderr = writer
    try:
        project_id = _parse_project_choice(project_choice)
        project_dir = PROJECTS_DIR / project_id
        info = load_project_info(project_dir)
        if scene_index is None:
            scene_index = max((s["scene_index"] for s in info["scenes"]), default=0) + 1
        from_step = int(from_step_str.split(" — ")[0].strip()) if " — " in from_step_str else int(from_step_str)
        audience = info["audience"]
        carry = info["carry_solver_context"]

        run_dir = run_project_scene(
            project_id=project_id,
            scene_index=scene_index,
            query=scene_query,
            audience_level=audience,
            carry_solver_context=carry,
            from_step=from_step,
            nudges=nudges_dict or None,
            force_fix_prompt=force_fix_prompt,
            force_fix_image=force_fix_image,
            insert_shift=insert_shift,
            model_provider=model_provider,
            tts_provider=tts_provider,
        )
        result_box["run_dir"] = run_dir
        result_box["scene_index"] = scene_index
    except Exception as exc:
        log_q.put(f"\n❌ Error: {exc}\n")
        import traceback
        log_q.put(traceback.format_exc())
        result_box["error"] = str(exc)
    finally:
        sys.stdout = orig_stdout
        sys.stderr = orig_stderr
        log_q.put(None)


def _stream_project_scene(
    project_choice: str,
    scene_query: str,
    from_step_str: str,
    n1: str, n2: str, n3: str, n4: str,
    scene_index_override: float | None = None,
    model_provider: str = "google",
    tts_provider: str = "local",
):
    """Generator: run project scene pipeline then render, yield (logs, video, md, scene_choices)."""
    no_choices = gr.update()
    if not project_choice or not scene_query.strip():
        yield "Please select a project and enter a query.", gr.update(visible=False), "*—*", no_choices
        return

    nudges = {k: v for k, v in {1: n1, 2: n2, 3: n3, 4: n4}.items() if v and v.strip()} or None
    scene_index = int(scene_index_override) if scene_index_override is not None else None
    insert_shift = scene_index is not None  # shift existing scenes when index is explicit
    log_q: queue.Queue = queue.Queue()
    result_box: dict = {}
    accumulated = ""

    t = threading.Thread(
        target=_run_project_scene_ui,
        args=(project_choice, scene_query, from_step_str, nudges, log_q, result_box),
        kwargs={"scene_index": scene_index, "insert_shift": insert_shift, "model_provider": model_provider, "tts_provider": tts_provider},
        daemon=True,
    )
    t.start()
    yield "Starting scene pipeline...\n", gr.update(visible=False), "*Running...*", no_choices

    while True:
        try:
            msg = log_q.get(timeout=0.2)
        except queue.Empty:
            yield accumulated, gr.update(visible=False), "*Running...*", no_choices
            continue
        if msg is None:
            break
        accumulated += msg
        yield accumulated, gr.update(visible=False), "*Running...*", no_choices

    t.join()

    if "error" in result_box:
        yield accumulated, gr.update(visible=False), "*Pipeline failed.*", no_choices
        return

    run_dir: Path = result_box["run_dir"]
    log_q2: queue.Queue = queue.Queue()
    result_box2: dict = {}

    t2 = threading.Thread(
        target=_run_render_thread,
        args=(run_dir, log_q2, result_box2),
        daemon=True,
    )
    t2.start()

    while True:
        try:
            msg = log_q2.get(timeout=0.2)
        except queue.Empty:
            yield accumulated, gr.update(visible=False), "*Rendering...*", no_choices
            continue
        if msg is None:
            break
        accumulated += msg
        yield accumulated, gr.update(visible=False), "*Rendering...*", no_choices

    t2.join()

    project_id = _parse_project_choice(project_choice)
    project_dir = PROJECTS_DIR / project_id
    md = _render_project_markdown(project_dir)
    scene_choices = gr.update(choices=_get_scene_choices(project_choice))

    if "video" in result_box2:
        yield accumulated, gr.update(visible=True, value=result_box2["video"]), md, scene_choices
    else:
        yield accumulated, gr.update(visible=False), md, scene_choices


def _stream_rerun_scene(
    project_choice: str,
    scene_idx_str: str,
    from_step_str: str,
    rr_n1: str, rr_n2: str, rr_n3: str, rr_n4: str,
    rr_force_fix: str,
    rr_force_fix_image: str | None = None,
    model_provider: str = "google",
    tts_provider: str = "local",
):
    """Generator: re-run an existing native scene from the chosen step."""
    no_choices = gr.update()
    if not project_choice or not scene_idx_str:
        yield "Select a project and scene.", gr.update(visible=False), "*—*", no_choices
        return
    from agentic_video_gen.projects import load_project_info
    try:
        project_id = _parse_project_choice(project_choice)
        project_dir = PROJECTS_DIR / project_id
        info = load_project_info(project_dir)
        idx = int(scene_idx_str)
        entry = next((s for s in info["scenes"] if s["scene_index"] == idx), None)
        if entry is None:
            yield f"Scene {idx} not found.", gr.update(visible=False), "*—*", no_choices
            return
        if entry.get("source") == "imported":
            yield f"Scene {idx} is imported — re-run the original run instead.", gr.update(visible=False), "*—*", no_choices
            return
        query = entry["query"]
    except Exception as exc:
        import traceback
        yield f"❌ {exc}\n{traceback.format_exc()}", gr.update(visible=False), "*—*", no_choices
        return

    nudges = {k: v for k, v in {1: rr_n1, 2: rr_n2, 3: rr_n3, 4: rr_n4}.items() if v and v.strip()} or None
    force_fix = rr_force_fix.strip() or None

    log_q: queue.Queue = queue.Queue()
    result_box: dict = {}
    accumulated = ""

    t = threading.Thread(
        target=_run_project_scene_ui,
        args=(project_choice, query, from_step_str, nudges, log_q, result_box),
        kwargs={"scene_index": idx, "force_fix_prompt": force_fix, "force_fix_image": rr_force_fix_image or None, "model_provider": model_provider, "tts_provider": tts_provider},
        daemon=True,
    )
    t.start()
    yield f"Re-running scene {idx} from {from_step_str}...\n", gr.update(visible=False), "*Running...*", no_choices

    while True:
        try:
            msg = log_q.get(timeout=0.2)
        except queue.Empty:
            yield accumulated, gr.update(visible=False), "*Running...*", no_choices
            continue
        if msg is None:
            break
        accumulated += msg
        yield accumulated, gr.update(visible=False), "*Running...*", no_choices

    t.join()

    if "error" in result_box:
        yield accumulated, gr.update(visible=False), "*Pipeline failed.*", no_choices
        return

    run_dir: Path = result_box["run_dir"]
    log_q2: queue.Queue = queue.Queue()
    result_box2: dict = {}

    t2 = threading.Thread(
        target=_run_render_thread,
        args=(run_dir, log_q2, result_box2),
        daemon=True,
    )
    t2.start()

    while True:
        try:
            msg = log_q2.get(timeout=0.2)
        except queue.Empty:
            yield accumulated, gr.update(visible=False), "*Rendering...*", no_choices
            continue
        if msg is None:
            break
        accumulated += msg
        yield accumulated, gr.update(visible=False), "*Rendering...*", no_choices

    t2.join()

    md = _render_project_markdown(project_dir)
    scene_choices = gr.update(choices=_get_scene_choices(project_choice))

    if "video" in result_box2:
        yield accumulated, gr.update(visible=True, value=result_box2["video"]), md, scene_choices
    else:
        yield accumulated, gr.update(visible=False), md, scene_choices


def _stitch_videos_ui(project_choice: str) -> tuple[str, object]:
    """Stitch all scene videos in the project."""
    if not project_choice:
        return "Select a project first.", gr.update(visible=False)
    from agentic_video_gen.stitch import stitch_project_videos
    project_id = _parse_project_choice(project_choice)
    project_dir = PROJECTS_DIR / project_id
    try:
        output = stitch_project_videos(project_dir)
        return f"✅ Stitched video saved to `{output}`", gr.update(visible=True, value=str(output))
    except Exception as e:
        return f"❌ Stitch failed: {e}", gr.update(visible=False)


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

with gr.Blocks(title="Agentic Video Generator") as demo:
    gr.Markdown("# 🎬 Agentic Educational Video Generator")

    with gr.Row():
        model_provider_radio = gr.Dropdown(
            choices=["google", "openai", "openrouter"],
            value="google",
            label="Model Provider",
            info="google = Gemini Flash · openai = GPT-5 mini · openrouter = OpenRouter (OPENROUTER_API_KEY)",
        )
        tts_provider_dropdown = gr.Dropdown(
            choices=["local", "elevenlabs"],
            value="local",
            label="TTS Provider",
            info="local = Coqui XTTS server (localhost:8000) · elevenlabs = ElevenLabs API (ELEVENLABS_API_KEY)",
        )

    with gr.Tabs():

        # ── Tab 1: New Video ─────────────────────────────────────────────
        with gr.Tab("New Video"):
            gr.Markdown("Enter a topic and audience level — the pipeline will generate a Manim educational video with voiceover.")

            with gr.Row():
                with gr.Column(scale=2):
                    query_input = gr.Textbox(
                        label="Topic / Question",
                        placeholder='e.g. "How does gravity work?" or "Explain photosynthesis"',
                        lines=6,
                        max_lines=10,
                    )
                    query_preview = gr.Markdown(value="*Preview will appear here as you type...*")
                with gr.Column(scale=1):
                    audience_input = gr.Textbox(
                        label="Audience Level",
                        value=DEFAULT_AUDIENCE,
                        placeholder="e.g. high school student, 7th grader",
                    )

            query_input.change(
                fn=lambda q: q if q.strip() else "*Preview will appear here as you type...*",
                inputs=query_input,
                outputs=query_preview,
            )

            with gr.Row():
                generate_btn = gr.Button("Generate Video", variant="primary", size="lg")
                new_stop_btn = gr.Button("⏹ Stop", variant="stop", size="lg")

            new_logs = gr.Textbox(label="Live Logs", lines=20, max_lines=40, interactive=False, autoscroll=True)
            new_video = gr.Video(label="Generated Video", visible=False)
            new_done = gr.Markdown("### ✅ Video ready!", visible=False)

            new_gen_event = generate_btn.click(
                fn=generate_video,
                inputs=[query_input, audience_input, model_provider_radio, tts_provider_dropdown],
                outputs=[new_logs, new_video, new_done],
            )
            new_stop_btn.click(fn=None, cancels=[new_gen_event])

        # ── Tab 2: Resume Run ────────────────────────────────────────────
        with gr.Tab("Resume Run"):
            gr.Markdown("Pick an existing run and the step to restart from. Earlier steps are loaded from saved checkpoints.")

            with gr.Row():
                run_dropdown = gr.Dropdown(
                    label="Existing Run",
                    choices=_list_runs(),
                    interactive=True,
                    scale=3,
                )
                refresh_btn = gr.Button("🔄 Refresh", scale=1)

            run_preview = gr.Markdown(value="*Select a run to see its details.*")

            step_radio = gr.Radio(
                label="Restart from step",
                choices=STEP_CHOICES,
                value=STEP_CHOICES[2],  # default: SVG Assets (common re-run point)
            )

            copy_run_checkbox = gr.Checkbox(
                label="Copy to new run (preserve original)",
                value=False,
                info="Creates a fresh run directory forked from the selected run. The original is left untouched.",
            )


            with gr.Accordion("🎬 Scene video preview", open=False):
                proj_scene_preview_video_resume = gr.Video(
                    label="Selected scene video",
                    interactive=False,
                    visible=True,
                )


            with gr.Accordion("Per-step nudges (optional)", open=False):
                gr.Markdown(
                    "Add extra instructions for any step that will run. "
                    "Each nudge is appended only to that step's prompt and ignored for skipped steps."
                )
                nudge1 = gr.Textbox(label="Step 1 — Analytical Solver", lines=2, placeholder="e.g. 'Focus on intuition, skip heavy math'")
                nudge2 = gr.Textbox(label="Step 2 — Script & TTS", lines=2, placeholder="e.g. 'Use shorter sentences, more humor'")
                nudge3 = gr.Textbox(label="Step 3 — SVG Assets", lines=2, placeholder="e.g. 'Use warmer colors, avoid circular shapes'")
                nudge4 = gr.Textbox(label="Step 4 — Manim Code", lines=2, placeholder="e.g. 'Animate each element with a fade-in'")

            force_fix_input = gr.Textbox(
                label="Visual fix description (force-fix at step 5)",
                lines=3,
                placeholder=(
                    "Describe what looks wrong in the rendered video and how to fix it.\n"
                    "e.g. 'The formula and the diagram overlap in the middle — move the formula to the top edge'\n"
                    "Leave blank to skip. Applied before the compilation loop when resuming from step 5."
                ),
            )
            force_fix_image_input = gr.Image(
                label="Screenshot of the issue (optional)",
                type="filepath",
                sources=["upload", "clipboard"],
            )

            with gr.Row():
                resume_btn = gr.Button("Resume from Step", variant="primary", size="lg")
                resume_stop_btn = gr.Button("⏹ Stop", variant="stop", size="lg")

            resume_logs = gr.Textbox(label="Live Logs", lines=20, max_lines=40, interactive=False, autoscroll=True)
            resume_video_out = gr.Video(label="Generated Video", visible=False)
            resume_done = gr.Markdown("### ✅ Video ready!", visible=False)

            run_dropdown.change(fn=_run_preview, inputs=run_dropdown, outputs=[run_preview, proj_scene_preview_video_resume])

            refresh_btn.click(
                fn=lambda: gr.update(choices=_list_runs()),
                outputs=run_dropdown,
            )

            resume_event = resume_btn.click(
                fn=resume_video,
                inputs=[run_dropdown, step_radio, copy_run_checkbox, nudge1, nudge2, nudge3, nudge4, force_fix_input, force_fix_image_input, model_provider_radio, tts_provider_dropdown],
                outputs=[resume_logs, resume_video_out, resume_done],
            )
            resume_stop_btn.click(fn=None, cancels=[resume_event])

        # ── Tab 3: Multi-Scene Project ───────────────────────────────────
        with gr.Tab("Multi-Scene Project"):
            gr.Markdown(
                "Create a **project** that groups multiple scenes into one stitched video. "
                "Each scene is a full pipeline run; context from earlier scenes is injected into later ones."
            )

            # ── Project selection row ──
            with gr.Row():
                proj_dropdown = gr.Dropdown(
                    label="Project",
                    choices=_list_projects(),
                    interactive=True,
                    scale=3,
                )
                proj_refresh_btn = gr.Button("🔄 Refresh", scale=1)
                proj_fork_btn = gr.Button("Fork Project", scale=1)
                proj_new_btn = gr.Button("New Project", variant="primary", scale=1)

            with gr.Row():
                proj_audience = gr.Textbox(
                    label="Audience (for new project)",
                    value=DEFAULT_AUDIENCE,
                    scale=2,
                )
                proj_carry_solver = gr.Checkbox(
                    label="Carry solver context in prompts",
                    value=False,
                    scale=1,
                )

            proj_status = gr.Markdown("*Select or create a project.*")

            # ── Scene list ──
            gr.Markdown("### Scene List")
            proj_scene_list = gr.Markdown("*No project selected.*")

            with gr.Accordion("🎬 Scene video preview", open=False):
                proj_scene_preview_video = gr.Video(
                    label="Selected scene video",
                    interactive=False,
                    visible=True,
                )

            # ── Action controls (below scene list) ──
            gr.Markdown("### Re-run / Remove Scene")
            with gr.Row():
                proj_scene_select = gr.Dropdown(
                    label="Select scene",
                    choices=[],
                    value=None,
                    interactive=True,
                    scale=3,
                )
                proj_remove_btn = gr.Button("🗑 Remove", scale=1)

            with gr.Row():
                proj_rerun_step = gr.Dropdown(
                    label="Re-run from step",
                    choices=STEP_CHOICES,
                    value=STEP_CHOICES[0],
                    interactive=True,
                    scale=3,
                )
                proj_rerun_btn = gr.Button("▶ Re-run Scene", variant="primary", scale=1)
                proj_rerun_stop_btn = gr.Button("⏹ Stop", variant="stop", scale=1)

            rr_force_fix = gr.Textbox(
                label="Visual fix description (force-fix at step 5)",
                lines=2,
                placeholder=(
                    "Describe what looks wrong visually — e.g. 'formula overlaps the diagram, move it to the top edge'. "
                    "Leave blank to skip."
                ),
            )
            rr_force_fix_image = gr.Image(
                label="Screenshot of the issue (optional)",
                type="filepath",
                sources=["upload", "clipboard"],
            )
            with gr.Accordion("Per-step nudges for re-run (optional)", open=False):
                rr_nudge1 = gr.Textbox(label="Step 1 — Solver", lines=2)
                rr_nudge2 = gr.Textbox(label="Step 2 — Script", lines=2)
                rr_nudge3 = gr.Textbox(label="Step 3 — SVGs", lines=2)
                rr_nudge4 = gr.Textbox(label="Step 4 — Manim", lines=2)

            # ── Add scene section ──
            gr.Markdown("### Add Scene")
            add_scene_mode = gr.Radio(
                label="Mode",
                choices=["Generate new scene", "Import existing scene"],
                value="Generate new scene",
            )

            with gr.Column(visible=True) as gen_scene_col:
                scene_query_input = gr.Textbox(
                    label="Query for next scene",
                    lines=4,
                    placeholder="e.g. Part a: finding the discriminant",
                )
                scene_query_preview = gr.Markdown(value="*Query preview will appear here...*")
                with gr.Row():
                    gen_from_step = gr.Dropdown(
                        label="Start from step",
                        choices=STEP_CHOICES,
                        value=STEP_CHOICES[0],
                        scale=3,
                    )
                    scene_index_input = gr.Number(
                        label="Scene index (leave blank for next)",
                        value=None,
                        precision=0,
                        minimum=1,
                        scale=1,
                    )
                with gr.Accordion("Per-step nudges (optional)", open=False):
                    proj_nudge1 = gr.Textbox(label="Step 1 — Solver", lines=2)
                    proj_nudge2 = gr.Textbox(label="Step 2 — Script", lines=2)
                    proj_nudge3 = gr.Textbox(label="Step 3 — SVGs", lines=2)
                    proj_nudge4 = gr.Textbox(label="Step 4 — Manim", lines=2)
            with gr.Row():
                run_scene_btn = gr.Button("▶ Run Scene", variant="primary")
                run_scene_stop_btn = gr.Button("⏹ Stop", variant="stop")

            with gr.Column(visible=False) as import_scene_col:
                import_source = gr.Dropdown(
                    label="Source run or scene",
                    choices=_list_importable_sources(),
                    interactive=True,
                )
                import_refresh_btn = gr.Button("🔄 Refresh sources")
                import_query_override = gr.Textbox(
                    label="Query label override (optional)",
                    placeholder="Leave blank to use original query",
                )
                import_scene_index_input = gr.Number(
                    label="Scene index (leave blank for next)",
                    value=None,
                    precision=0,
                    minimum=1,
                    interactive=True,
                )
                import_btn = gr.Button("Import Scene", variant="primary")

            # ── Output ──
            gr.Markdown("### Output")
            proj_logs = gr.Textbox(label="Live Logs", lines=18, max_lines=40, interactive=False, autoscroll=True)
            proj_video = gr.Video(label="Latest Scene Video", visible=False)

            gr.Markdown("---")
            stitch_btn = gr.Button("✂ Stitch All Scenes", variant="secondary")
            stitch_status = gr.Markdown("")
            stitched_video = gr.Video(label="Stitched Video", visible=False)

            # ── Event wiring ──

            scene_query_input.change(
                fn=lambda q: q if q.strip() else "*Query preview will appear here...*",
                inputs=scene_query_input,
                outputs=scene_query_preview,
            )

            def _toggle_add_mode(mode):
                return (
                    gr.update(visible=(mode == "Generate new scene")),
                    gr.update(visible=(mode == "Import existing scene")),
                )

            add_scene_mode.change(
                fn=_toggle_add_mode,
                inputs=add_scene_mode,
                outputs=[gen_scene_col, import_scene_col],
            )

            def _refresh_projects():
                return gr.update(choices=_list_projects())

            def _on_project_select(choice):
                if not choice:
                    return "*Select a project.*", gr.update(choices=[], value=None), False
                pid = _parse_project_choice(choice)
                project_dir = PROJECTS_DIR / pid
                md = _render_project_markdown(project_dir)
                choices = _get_scene_choices(choice)
                info_path = project_dir / "project_info.json"
                carry = _json.loads(info_path.read_text(encoding="utf-8")).get("carry_solver_context", False) if info_path.exists() else False
                return md, gr.update(choices=choices, value=choices[0] if choices else None), carry

            def _on_carry_solver_change(choice, carry):
                if not choice:
                    return gr.update()
                pid = _parse_project_choice(choice)
                info_path = PROJECTS_DIR / pid / "project_info.json"
                if not info_path.exists():
                    return gr.update()
                info = _json.loads(info_path.read_text(encoding="utf-8"))
                info["carry_solver_context"] = carry
                info_path.write_text(_json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
                return _render_project_markdown(PROJECTS_DIR / pid)

            def _on_scene_select_preview(project_choice, scene_idx_str):
                """Load the rendered_video.mp4 for the selected scene into the preview player."""
                if not project_choice or not scene_idx_str:
                    return gr.update(value=None)
                try:
                    pid = _parse_project_choice(project_choice)
                    info_path = PROJECTS_DIR / pid / "project_info.json"
                    info = _json.loads(info_path.read_text(encoding="utf-8"))
                    idx = int(scene_idx_str)
                    entry = next((s for s in info["scenes"] if s["scene_index"] == idx), None)
                    if entry is None:
                        return gr.update(value=None)
                    video_path = RUNS_DIR / entry["scene_dir"] / "rendered_video.mp4"
                    if video_path.exists():
                        return gr.update(value=str(video_path))
                except Exception:
                    pass
                return gr.update(value=None)

            proj_refresh_btn.click(fn=_refresh_projects, outputs=proj_dropdown)
            proj_dropdown.change(
                fn=_on_project_select,
                inputs=proj_dropdown,
                outputs=[proj_scene_list, proj_scene_select, proj_carry_solver],
            )
            proj_carry_solver.change(
                fn=_on_carry_solver_change,
                inputs=[proj_dropdown, proj_carry_solver],
                outputs=proj_scene_list,
            )
            proj_scene_select.change(
                fn=_on_scene_select_preview,
                inputs=[proj_dropdown, proj_scene_select],
                outputs=proj_scene_preview_video,
            )

            def _new_project_action(audience, carry):
                msg, choice = _new_project_ui(audience, carry)
                new_choices = _list_projects()
                return msg, gr.update(choices=new_choices, value=choice if choice else None), "*—*"

            proj_new_btn.click(
                fn=_new_project_action,
                inputs=[proj_audience, proj_carry_solver],
                outputs=[proj_status, proj_dropdown, proj_scene_list],
            )

            def _fork_project_action(choice):
                msg, new_choice = _fork_project_ui(choice)
                new_choices = _list_projects()
                return msg, gr.update(choices=new_choices, value=new_choice if new_choice else None)

            proj_fork_btn.click(
                fn=_fork_project_action,
                inputs=proj_dropdown,
                outputs=[proj_status, proj_dropdown],
            )

            proj_rerun_event = proj_rerun_btn.click(
                fn=_stream_rerun_scene,
                inputs=[
                    proj_dropdown, proj_scene_select, proj_rerun_step,
                    rr_nudge1, rr_nudge2, rr_nudge3, rr_nudge4,
                    rr_force_fix, rr_force_fix_image, model_provider_radio, tts_provider_dropdown,
                ],
                outputs=[proj_logs, proj_video, proj_scene_list, proj_scene_select],
            )
            proj_rerun_stop_btn.click(fn=None, cancels=[proj_rerun_event])

            def _remove_scene_action(project_choice, scene_idx_str):
                msg, md = _remove_scene_ui(project_choice, scene_idx_str)
                choices = _get_scene_choices(project_choice)
                return msg, md, gr.update(choices=choices, value=choices[0] if choices else None)

            proj_remove_btn.click(
                fn=_remove_scene_action,
                inputs=[proj_dropdown, proj_scene_select],
                outputs=[proj_status, proj_scene_list, proj_scene_select],
            )

            import_refresh_btn.click(
                fn=lambda: gr.update(choices=_list_importable_sources()),
                outputs=import_source,
            )

            def _import_scene_action(project_choice, source_choice, query_override, scene_index_override):
                msg, md = _import_scene_ui(project_choice, source_choice, query_override, scene_index_override)
                choices = _get_scene_choices(project_choice)
                return msg, md, gr.update(choices=choices, value=choices[-1] if choices else None)

            import_btn.click(
                fn=_import_scene_action,
                inputs=[proj_dropdown, import_source, import_query_override, import_scene_index_input],
                outputs=[proj_status, proj_scene_list, proj_scene_select],
            )

            run_scene_event = run_scene_btn.click(
                fn=_stream_project_scene,
                inputs=[
                    proj_dropdown, scene_query_input, gen_from_step,
                    proj_nudge1, proj_nudge2, proj_nudge3, proj_nudge4,
                    scene_index_input, model_provider_radio, tts_provider_dropdown,
                ],
                outputs=[proj_logs, proj_video, proj_scene_list, proj_scene_select],
            )
            run_scene_stop_btn.click(fn=None, cancels=[run_scene_event])

            def _stitch_action(project_choice):
                msg, video_update = _stitch_videos_ui(project_choice)
                return msg, video_update

            stitch_btn.click(
                fn=_stitch_action,
                inputs=proj_dropdown,
                outputs=[stitch_status, stitched_video],
            )


if __name__ == "__main__":
    demo.queue().launch(
        server_name="0.0.0.0",
        server_port=7861,
        inbrowser=True,
        theme=gr.themes.Soft(),
    )
