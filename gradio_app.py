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
    """Return run choices as 'run_id — query' strings, newest first."""
    if not RUNS_DIR.exists():
        return []
    choices = []
    for d in sorted(RUNS_DIR.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if not d.is_dir():
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
):
    """Generator: runs pipeline thread, then render thread, yielding (logs, video, done)."""
    log_q: queue.Queue = queue.Queue()
    result_box: dict = {}
    accumulated = ""

    t = threading.Thread(
        target=_run_pipeline_thread,
        args=(query, audience, log_q, result_box),
        kwargs={"run_id": run_id, "from_step": from_step, "nudges": nudges},
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

def generate_video(query: str, audience: str):
    """New run: start from step 1."""
    if not query.strip():
        yield "Please enter a topic.", gr.update(visible=False), gr.update(visible=False)
        return
    yield from _stream_pipeline_and_render(query, audience)


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

    return (
        f"**Run ID:** `{run_id}`\n\n"
        f"**Query:** {info['query']}\n\n"
        f"**Audience:** {info['audience']}\n\n"
        f"**Checkpoints:**\n"
        + "\n".join(f"- {c}" for c in completed)
        + f"\n- {has_scene} generated_scene.py"
    )


def resume_video(run_choice: str, step_choice: str, copy_run: bool, n1: str, n2: str, n3: str, n4: str):
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

    yield from _stream_pipeline_and_render(query, audience, run_id=run_id, from_step=from_step, nudges=nudges)


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

with gr.Blocks(title="Agentic Video Generator") as demo:
    gr.Markdown("# 🎬 Agentic Educational Video Generator")

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

            generate_btn = gr.Button("Generate Video", variant="primary", size="lg")

            new_logs = gr.Textbox(label="Live Logs", lines=20, max_lines=40, interactive=False, autoscroll=True)
            new_video = gr.Video(label="Generated Video", visible=False)
            new_done = gr.Markdown("### ✅ Video ready!", visible=False)

            generate_btn.click(
                fn=generate_video,
                inputs=[query_input, audience_input],
                outputs=[new_logs, new_video, new_done],
            )

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

            with gr.Accordion("Per-step nudges (optional)", open=False):
                gr.Markdown(
                    "Add extra instructions for any step that will run. "
                    "Each nudge is appended only to that step's prompt and ignored for skipped steps."
                )
                nudge1 = gr.Textbox(label="Step 1 — Analytical Solver", lines=2, placeholder="e.g. 'Focus on intuition, skip heavy math'")
                nudge2 = gr.Textbox(label="Step 2 — Script & TTS", lines=2, placeholder="e.g. 'Use shorter sentences, more humor'")
                nudge3 = gr.Textbox(label="Step 3 — SVG Assets", lines=2, placeholder="e.g. 'Use warmer colors, avoid circular shapes'")
                nudge4 = gr.Textbox(label="Step 4 — Manim Code", lines=2, placeholder="e.g. 'Animate each element with a fade-in'")

            resume_btn = gr.Button("Resume from Step", variant="primary", size="lg")

            resume_logs = gr.Textbox(label="Live Logs", lines=20, max_lines=40, interactive=False, autoscroll=True)
            resume_video_out = gr.Video(label="Generated Video", visible=False)
            resume_done = gr.Markdown("### ✅ Video ready!", visible=False)

            run_dropdown.change(fn=_run_preview, inputs=run_dropdown, outputs=run_preview)

            refresh_btn.click(
                fn=lambda: gr.update(choices=_list_runs()),
                outputs=run_dropdown,
            )

            resume_btn.click(
                fn=resume_video,
                inputs=[run_dropdown, step_radio, copy_run_checkbox, nudge1, nudge2, nudge3, nudge4],
                outputs=[resume_logs, resume_video_out, resume_done],
            )


if __name__ == "__main__":
    demo.queue().launch(
        server_name="0.0.0.0",
        server_port=7861,
        inbrowser=True,
        theme=gr.themes.Soft(),
    )
