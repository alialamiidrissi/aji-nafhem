"""
FastAPI backend for the Aji Nafhem video generation pipeline.
Replaces the Gradio interface with proper REST + SSE endpoints.
"""
import os
import sys
import json
import uuid
import shutil
import logging
import queue
import threading
import subprocess
from pathlib import Path
from typing import Generator

from fastapi import FastAPI, HTTPException, Request, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel
from dotenv import load_dotenv

from agentic_video_gen.pipeline import run_pipeline, PipelineStopped
from agentic_video_gen.stitch import stitch_project_videos
from agentic_video_gen.projects import (
    create_project,
    add_native_scene,
    import_scene as _import_scene,
    remove_scene as _remove_scene,
    fork_project as _fork_project,
    run_project_scene,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("uvicorn.error")

# job_id → stop event for active pipeline runs
_active_jobs: dict[str, threading.Event] = {}


load_dotenv()

MANIM_BIN = os.environ.get("MANIM_BIN", "manim")
PROJECT_DIR = Path(__file__).parent
RUNS_DIR = Path(os.environ.get("RUNS_DIR", PROJECT_DIR / "agentic_video_gen" / "runs"))
PROJECTS_DIR = RUNS_DIR / "projects"
DEFAULT_AUDIENCE = "high school student"

_CHECKPOINT_FILES = {
    1: "checkpoint_step1_solved.json",
    2: "checkpoint_step2_script.json",
    3: "checkpoint_step3a_maps.json",
    4: "checkpoint_step3_svgs.json",
    5: "checkpoint_step4_manim.json",
}

app = FastAPI(title="Aji Nafhem API")

@app.middleware("http")
async def log_json(request: Request, call_next):
    if request.headers.get("content-type") == "application/json":
        body = await request.body()
        print("JSON Body:", body.decode())

        async def receive():
            return {"type": "http.request", "body": body, "more_body": False}

        request = Request(request.scope, receive)

    return await call_next(request)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class GenerateRequest(BaseModel):
    query: str
    audience: str = DEFAULT_AUDIENCE
    model_provider: str = "google"
    tts_provider: str = "local"
    language: str = "darija"
    nudge_1: str = ""
    nudge_2: str = ""
    nudge_3: str = ""
    nudge_4: str = ""
    nudge_5: str = ""


class ResumeRequest(BaseModel):
    run_id: str
    from_step: int = 1
    copy_run: bool = False
    nudge_1: str = ""
    nudge_2: str = ""
    nudge_3: str = ""
    nudge_4: str = ""
    nudge_5: str = ""
    force_fix_prompt: str = ""
    force_fix_image_path: str | None = None
    model_provider: str = "google"
    tts_provider: str = "local"
    language: str = "darija"


class NewProjectRequest(BaseModel):
    audience: str = DEFAULT_AUDIENCE
    carry_solver_context: bool = False


class RenameProjectRequest(BaseModel):
    name: str


class AddSceneRequest(BaseModel):
    query: str
    scene_index: int | None = None


class ImportSceneRequest(BaseModel):
    source_path: str  # relative path under RUNS_DIR


class RemoveSceneRequest(BaseModel):
    scene_index: int


class RunSceneRequest(BaseModel):
    scene_index: int
    from_step: int = 1
    nudge_1: str = ""
    nudge_2: str = ""
    nudge_3: str = ""
    nudge_4: str = ""
    nudge_5: str = ""
    force_fix_prompt: str = ""
    force_fix_image_path: str | None = None
    model_provider: str = "google"
    tts_provider: str = "local"
    language: str = "darija"
    insert_shift: bool = False


# ---------------------------------------------------------------------------
# Helpers (ported from gradio_app.py)
# ---------------------------------------------------------------------------

def _read_run_info(run_dir: Path) -> dict | None:
    info_json = run_dir / "run_info.json"
    info_txt = run_dir / "run_info.txt"
    if info_json.exists():
        data = json.loads(info_json.read_text(encoding="utf-8"))
        return {"query": data.get("query", ""), "audience": data.get("audience", DEFAULT_AUDIENCE),
                "language": data.get("language", "darija")}
    elif info_txt.exists():
        info = {}
        for line in info_txt.read_text(encoding="utf-8").splitlines():
            if ": " in line:
                k, v = line.split(": ", 1)
                info[k.strip()] = v.strip()
        return {"query": info.get("Query", ""), "audience": info.get("Audience", DEFAULT_AUDIENCE)}
    return None


def _fork_run_dir(src_dir: Path, from_step: int) -> tuple[str, Path]:
    new_id = str(uuid.uuid4())
    dst_dir = RUNS_DIR / new_id
    dst_dir.mkdir(parents=True)
    (dst_dir / "assets").mkdir()
    (dst_dir / "audios").mkdir()

    for step in range(1, from_step):
        fname = _CHECKPOINT_FILES.get(step)
        if fname and (src_dir / fname).exists():
            shutil.copy2(src_dir / fname, dst_dir / fname)

    # Step 3a (map requests) is part of step 3 — copy it whenever step 3 is being skipped
    if from_step > 3:
        fname_3a = _CHECKPOINT_FILES.get("3a")
        if fname_3a and (src_dir / fname_3a).exists():
            shutil.copy2(src_dir / fname_3a, dst_dir / fname_3a)

    if from_step > 2 and (src_dir / "audios").exists():
        shutil.copytree(src_dir / "audios", dst_dir / "audios", dirs_exist_ok=True)
    if from_step > 3 and (src_dir / "assets").exists():
        shutil.copytree(src_dir / "assets", dst_dir / "assets", dirs_exist_ok=True)
    if from_step > 4 and (src_dir / "generated_scene.py").exists():
        shutil.copy2(src_dir / "generated_scene.py", dst_dir / "generated_scene.py")

    # Copy run_info.json
    if (src_dir / "run_info.json").exists():
        shutil.copy2(src_dir / "run_info.json", dst_dir / "run_info.json")

    return new_id, dst_dir


class _QueueWriter:
    def __init__(self, q: queue.Queue):
        self._q = q

    def write(self, text: str):
        if text:
            self._q.put(text)

    def flush(self):
        pass


def _sse_event(data: str) -> str:
    """Format a string as an SSE data event."""
    lines = data.replace("\r\n", "\n").replace("\r", "\n")
    return "".join(f"data: {line}\n" for line in lines.split("\n") if line) + "\n"


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
    language: str = "darija",
    stop_event: threading.Event | None = None,
):
    orig_stdout = sys.stdout
    orig_stderr = sys.stderr
    writer = _QueueWriter(log_q)
    sys.stdout = writer
    sys.stderr = writer
    try:
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
            language=language,
            stop_event=stop_event,
        )
        result_box["run_dir"] = run_dir
    except PipelineStopped:
        log_q.put("\n🛑 Pipeline stopped by user.\n")
        result_box["stopped"] = True
    except Exception as exc:
        if stop_event and stop_event.is_set():
            log_q.put("\n🛑 Pipeline stopped by user.\n")
            result_box["stopped"] = True
        else:
            log_q.put(f"\n❌ Pipeline error: {exc}\n")
            import traceback
            log_q.put(traceback.format_exc())
            result_box["error"] = str(exc)
    finally:
        sys.stdout = orig_stdout
        sys.stderr = orig_stderr
        log_q.put(None)


def _run_render_thread(run_dir: Path, log_q: queue.Queue, result_box: dict, stop_event: threading.Event | None = None):
    out_file = run_dir / "generated_scene.py"
    run_env = {**os.environ, "MANIM_RUN_DIR": str(run_dir.resolve())}

    log_q.put(f"\n[Render] Running: manim -qm {out_file} GeneratedEducationalScene\n")

    media_dir = run_dir / "media"
    proc = subprocess.Popen(
        [MANIM_BIN, "-qm", str(out_file), "GeneratedEducationalScene",
         "--disable_caching", "--verbosity", "WARNING",
         "--media_dir", str(media_dir)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=run_env,
        cwd=str(PROJECT_DIR),
    )

    for line in proc.stdout:
        if stop_event and stop_event.is_set():
            proc.terminate()
            log_q.put("\n🛑 Render stopped by user.\n")
            result_box["stopped"] = True
            log_q.put(None)
            return
        log_q.put(line)

    proc.wait()
    if proc.returncode == 0:
        # Manim writes to <media_dir>/videos/<scene_stem>/720p30/<ClassName>.mp4
        scene_stem = out_file.stem
        video_path = media_dir / "videos" / scene_stem / "720p30" / "GeneratedEducationalScene.mp4"
        if video_path.exists():
            shutil.copy2(video_path, run_dir / "rendered_video.mp4")
            result_box["video_path"] = str(run_dir / "rendered_video.mp4")
            # Remove partial movie files and the tmp render output — not needed after copy
            partial_dir = video_path.parent / "partial_movie_files"
            if partial_dir.exists():
                shutil.rmtree(partial_dir)
            video_path.unlink(missing_ok=True)
            wav_path = video_path.with_suffix(".wav")
            wav_path.unlink(missing_ok=True)
            log_q.put(f"\n✅ Render complete → {run_dir / 'rendered_video.mp4'}\n")
        else:
            log_q.put(f"\n⚠️  Render succeeded but video file not found at {video_path}.\n")
    else:
        log_q.put(f"\n❌ Render failed (exit code {proc.returncode}).\n")

    log_q.put(None)


def _run_stitch_thread(project_id: str, log_q: queue.Queue, result_box: dict):
    orig_stdout = sys.stdout
    orig_stderr = sys.stderr
    writer = _QueueWriter(log_q)
    sys.stdout = writer
    sys.stderr = writer
    try:
        output_path = stitch_project_videos(project_id)
        result_box["video_path"] = str(output_path)
        log_q.put(f"\n✅ Stitch complete → {output_path}\n")
    except Exception as exc:
        log_q.put(f"\n❌ Stitch error: {exc}\n")
        import traceback
        log_q.put(traceback.format_exc())
    finally:
        sys.stdout = orig_stdout
        sys.stderr = orig_stderr
        log_q.put(None)


def _stream_pipeline_and_render_generator(
    query: str,
    audience: str,
    run_id: str | None = None,
    from_step: int = 1,
    nudges: dict | None = None,
    force_fix_prompt: str | None = None,
    force_fix_image: str | None = None,
    model_provider: str = "google",
    tts_provider: str = "local",
    language: str = "darija",
) -> Generator[str, None, None]:
    job_id = str(uuid.uuid4())
    stop_event = threading.Event()
    _active_jobs[job_id] = stop_event

    try:
        log_q: queue.Queue = queue.Queue()
        result_box: dict = {}

        t = threading.Thread(
            target=_run_pipeline_thread,
            args=(query, audience, log_q, result_box),
            kwargs={
                "run_id": run_id, "from_step": from_step, "nudges": nudges,
                "force_fix_prompt": force_fix_prompt, "force_fix_image": force_fix_image,
                "model_provider": model_provider, "tts_provider": tts_provider,
                "language": language, "stop_event": stop_event,
            },
            daemon=True,
        )
        t.start()

        yield f"event: job_id\ndata: {job_id}\n\n"
        yield _sse_event("Starting pipeline...")

        while True:
            try:
                msg = log_q.get(timeout=0.2)
            except queue.Empty:
                continue
            if msg is None:
                break
            yield _sse_event(msg)

        t.join()

        if result_box.get("stopped"):
            yield "event: done\ndata: done\n\n"
            return

        if "error" in result_box:
            yield f"event: error\ndata: {result_box['error']}\n\n"
            return

        run_dir: Path = result_box["run_dir"]
        run_id_final = run_dir.name
        yield f"event: run_id\ndata: {run_id_final}\n\n"

        log_q2: queue.Queue = queue.Queue()
        result_box2: dict = {}

        t2 = threading.Thread(
            target=_run_render_thread,
            args=(run_dir, log_q2, result_box2),
            kwargs={"stop_event": stop_event},
            daemon=True,
        )
        t2.start()

        while True:
            try:
                msg = log_q2.get(timeout=0.2)
            except queue.Empty:
                continue
            if msg is None:
                break
            yield _sse_event(msg)

        t2.join()

        if "video_path" in result_box2:
            rel = Path(result_box2["video_path"]).resolve().relative_to(RUNS_DIR.resolve())
            yield f"event: video\ndata: /api/media/{rel}\n\n"

        yield "event: done\ndata: done\n\n"
    finally:
        _active_jobs.pop(job_id, None)


# ---------------------------------------------------------------------------
# Routes: Upload
# ---------------------------------------------------------------------------

UPLOADS_DIR = PROJECT_DIR / "uploads"

@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    """Save an uploaded file and return its server path."""
    UPLOADS_DIR.mkdir(exist_ok=True)
    suffix = Path(file.filename).suffix if file.filename else ".png"
    dest = UPLOADS_DIR / f"{uuid.uuid4()}{suffix}"
    content = await file.read()
    dest.write_bytes(content)
    return {"path": str(dest)}


# ---------------------------------------------------------------------------
# Routes: Runs
# ---------------------------------------------------------------------------

@app.get("/api/runs")
def list_runs():
    if not RUNS_DIR.exists():
        return []
    runs = []
    for d in sorted(RUNS_DIR.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if not d.is_dir() or d.name == "projects":
            continue
        info = _read_run_info(d)
        if info is None:
            continue
        runs.append({
            "run_id": d.name,
            "query": info["query"],
            "audience": info["audience"],
            "query_preview": info["query"].replace("\n", " ")[:70],
        })
    return runs


@app.get("/api/runs/{run_id}")
def get_run(run_id: str):
    run_dir = RUNS_DIR / run_id
    info = _read_run_info(run_dir)
    if info is None:
        raise HTTPException(404, "Run not found")

    checkpoints = {}
    step_names = {1: "Solver", 2: "Script", 3: "Maps", 4: "SVGs", 5: "Manim"}
    for s, fname in _CHECKPOINT_FILES.items():
        checkpoints[s] = {
            "name": step_names[s],
            "done": (run_dir / fname).exists(),
        }

    has_scene = (run_dir / "generated_scene.py").exists()
    has_video = (run_dir / "rendered_video.mp4").exists()

    return {
        "run_id": run_id,
        "query": info["query"],
        "audience": info["audience"],
        "language": info.get("language", "darija"),
        "checkpoints": checkpoints,
        "has_scene": has_scene,
        "has_video": has_video,
        "video_url": f"/api/media/{run_id}/rendered_video.mp4" if has_video else None,
    }


# ---------------------------------------------------------------------------
# Routes: Generate (SSE)
# ---------------------------------------------------------------------------

@app.post("/api/generate")
def generate_video(req: GenerateRequest):
    if not req.query.strip():
        raise HTTPException(400, "Query cannot be empty")

    nudges = {k: v for k, v in {1: req.nudge_1, 2: req.nudge_2, 3: req.nudge_3, 4: req.nudge_4, 5: req.nudge_5}.items() if v and v.strip()} or None

    return StreamingResponse(
        _stream_pipeline_and_render_generator(
            req.query, req.audience,
            nudges=nudges,
            model_provider=req.model_provider,
            tts_provider=req.tts_provider,
            language=req.language,
        ),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )


@app.post("/api/stop/{job_id}")
def stop_job(job_id: str):
    ev = _active_jobs.get(job_id)
    if ev:
        ev.set()
    return {"ok": True}


@app.post("/api/resume")
def resume_video(req: ResumeRequest):
    run_dir = RUNS_DIR / req.run_id
    info = _read_run_info(run_dir)
    if info is None:
        raise HTTPException(404, "Run not found")

    run_id = req.run_id
    if req.copy_run:
        run_id, run_dir = _fork_run_dir(run_dir, req.from_step)

    nudges = {k: v for k, v in {1: req.nudge_1, 2: req.nudge_2, 3: req.nudge_3, 4: req.nudge_4, 5: req.nudge_5}.items() if v and v.strip()} or None

    def gen():
        if req.copy_run:
            yield _sse_event(f"[Fork] Copied to new run: {run_id}")
        yield from _stream_pipeline_and_render_generator(
            info["query"], info["audience"],
            run_id=run_id,
            from_step=req.from_step,
            nudges=nudges,
            force_fix_prompt=req.force_fix_prompt.strip() or None,
            force_fix_image=req.force_fix_image_path or None,
            model_provider=req.model_provider,
            tts_provider=req.tts_provider,
            language=req.language,
        )

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )


# ---------------------------------------------------------------------------
# Routes: Projects
# ---------------------------------------------------------------------------

@app.get("/api/projects")
def list_projects():
    if not PROJECTS_DIR.exists():
        return []
    projects = []
    for d in sorted(PROJECTS_DIR.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if not d.is_dir():
            continue
        info_path = d / "project_info.json"
        if not info_path.exists():
            continue
        try:
            info = json.loads(info_path.read_text(encoding="utf-8"))
            projects.append({
                "project_id": info["project_id"],
                "name": info.get("name", ""),
                "audience": info.get("audience", DEFAULT_AUDIENCE),
                "carry_solver_context": info.get("carry_solver_context", False),
                "scene_count": len(info.get("scenes", [])),
            })
        except Exception:
            pass
    return projects


@app.get("/api/projects/{project_id}")
def get_project(project_id: str):
    info_path = PROJECTS_DIR / project_id / "project_info.json"
    if not info_path.exists():
        raise HTTPException(404, "Project not found")

    info = json.loads(info_path.read_text(encoding="utf-8"))
    scenes = []
    for entry in info.get("scenes", []):
        scene_dir = RUNS_DIR / entry["scene_dir"]
        has_video = (scene_dir / "rendered_video.mp4").exists()
        checkpoints = {
            s: (scene_dir / fname).exists()
            for s, fname in _CHECKPOINT_FILES.items()
        }

        solver_data = None
        if checkpoints[1]:
            try:
                solver_data = json.loads((scene_dir / _CHECKPOINT_FILES[1]).read_text())
            except Exception:
                pass

        script_data = None
        if checkpoints[2]:
            try:
                script_data = json.loads((scene_dir / _CHECKPOINT_FILES[2]).read_text())
            except Exception:
                pass

        scenes.append({
            **entry,
            "has_video": has_video,
            "video_url": f"/api/media/{entry['scene_dir']}/rendered_video.mp4" if has_video else None,
            "checkpoints": checkpoints,
            "solver": solver_data,
            "script": script_data,
        })

    return {
        "project_id": info["project_id"],
        "name": info.get("name", ""),
        "audience": info.get("audience", DEFAULT_AUDIENCE),
        "carry_solver_context": info.get("carry_solver_context", False),
        "scenes": scenes,
    }


@app.post("/api/projects")
def new_project(req: NewProjectRequest):
    project_id, _ = create_project(
        audience=req.audience,
        carry_solver_context=req.carry_solver_context,
    )
    return {"project_id": project_id}


@app.post("/api/projects/{project_id}/add-scene")
def add_scene(project_id: str, req: AddSceneRequest):
    info_path = PROJECTS_DIR / project_id / "project_info.json"
    if not info_path.exists():
        raise HTTPException(404, "Project not found")

    scene_index = add_native_scene(
        project_id=project_id,
        query=req.query,
        insert_shift=req.scene_index is not None,
        scene_index=req.scene_index,
    )
    return {"scene_index": scene_index}


@app.post("/api/projects/{project_id}/import-scene")
def import_scene(project_id: str, req: ImportSceneRequest):
    info_path = PROJECTS_DIR / project_id / "project_info.json"
    if not info_path.exists():
        raise HTTPException(404, "Project not found")

    source_path = (RUNS_DIR / req.source_path).resolve()
    scene_index = _import_scene(project_id=project_id, source_dir=source_path)
    return {"scene_index": scene_index}


@app.post("/api/projects/{project_id}/remove-scene")
def remove_scene(project_id: str, req: RemoveSceneRequest):
    info_path = PROJECTS_DIR / project_id / "project_info.json"
    if not info_path.exists():
        raise HTTPException(404, "Project not found")

    _remove_scene(project_id=project_id, scene_index=req.scene_index)
    return {"ok": True}


@app.delete("/api/projects/{project_id}")
def delete_project(project_id: str):
    project_dir = PROJECTS_DIR / project_id
    if not project_dir.exists():
        raise HTTPException(404, "Project not found")
    shutil.rmtree(project_dir)
    return {"ok": True}


@app.patch("/api/projects/{project_id}/rename")
def rename_project(project_id: str, req: RenameProjectRequest):
    info_path = PROJECTS_DIR / project_id / "project_info.json"
    if not info_path.exists():
        raise HTTPException(404, "Project not found")
    info = json.loads(info_path.read_text(encoding="utf-8"))
    info["name"] = req.name.strip()
    info_path.write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True}


@app.post("/api/projects/{project_id}/fork")
def fork_project(project_id: str):
    info_path = PROJECTS_DIR / project_id / "project_info.json"
    if not info_path.exists():
        raise HTTPException(404, "Project not found")

    new_id, _ = _fork_project(PROJECTS_DIR / project_id)
    return {"project_id": new_id}


@app.post("/api/projects/{project_id}/run-scene")
def run_scene(project_id: str, req: RunSceneRequest):
    info_path = PROJECTS_DIR / project_id / "project_info.json"
    if not info_path.exists():
        raise HTTPException(404, "Project not found")

    project_info = json.loads(info_path.read_text(encoding="utf-8"))
    audience = project_info.get("audience", DEFAULT_AUDIENCE)
    carry_solver_context = project_info.get("carry_solver_context", False)

    # Resolve the query for this scene from the stored scene list
    scenes = project_info.get("scenes", [])
    scene_entry = next((s for s in scenes if s["scene_index"] == req.scene_index), None)
    if scene_entry is None:
        raise HTTPException(404, f"Scene {req.scene_index} not found in project")
    scene_query = scene_entry["query"]

    nudges = {
        k: v for k, v in {1: req.nudge_1, 2: req.nudge_2, 3: req.nudge_3, 4: req.nudge_4, 5: req.nudge_5}.items()
        if v and v.strip()
    } or None

    job_id = str(uuid.uuid4())
    stop_event = threading.Event()
    _active_jobs[job_id] = stop_event

    log_q: queue.Queue = queue.Queue()
    result_box: dict = {}

    def _thread():
        orig_stdout = sys.stdout
        orig_stderr = sys.stderr
        writer = _QueueWriter(log_q)
        sys.stdout = writer
        sys.stderr = writer
        try:
            run_dir = run_project_scene(
                project_id=project_id,
                scene_index=req.scene_index,
                query=scene_query,
                audience_level=audience,
                carry_solver_context=carry_solver_context,
                from_step=req.from_step,
                nudges=nudges,
                force_fix_prompt=req.force_fix_prompt.strip() or None,
                force_fix_image=req.force_fix_image_path or None,
                model_provider=req.model_provider,
                tts_provider=req.tts_provider,
                language=req.language,
                insert_shift=req.insert_shift,
                stop_event=stop_event,
            )
            result_box["run_dir"] = run_dir
        except PipelineStopped:
            log_q.put("\n🛑 Pipeline stopped by user.\n")
            result_box["stopped"] = True
        except Exception as exc:
            if stop_event and stop_event.is_set():
                log_q.put("\n🛑 Pipeline stopped by user.\n")
                result_box["stopped"] = True
            else:
                log_q.put(f"\n❌ Error: {exc}\n")
                import traceback
                log_q.put(traceback.format_exc())
                result_box["error"] = str(exc)
        finally:
            sys.stdout = orig_stdout
            sys.stderr = orig_stderr
            log_q.put(None)

    def gen():
        try:
            t = threading.Thread(target=_thread, daemon=True)
            t.start()

            yield f"event: job_id\ndata: {job_id}\n\n"
            yield _sse_event(f"Starting scene {req.scene_index} pipeline...")

            while True:
                try:
                    msg = log_q.get(timeout=0.2)
                except queue.Empty:
                    continue
                if msg is None:
                    break
                yield _sse_event(msg)

            t.join()

            if result_box.get("stopped"):
                yield "event: done\ndata: done\n\n"
                return

            if "error" in result_box:
                yield f"event: error\ndata: {result_box['error']}\n\n"
                return

            run_dir: Path = result_box["run_dir"]

            log_q2: queue.Queue = queue.Queue()
            result_box2: dict = {}

            t2 = threading.Thread(
                target=_run_render_thread,
                args=(run_dir, log_q2, result_box2),
                kwargs={"stop_event": stop_event},
                daemon=True,
            )
            t2.start()

            while True:
                try:
                    msg = log_q2.get(timeout=0.2)
                except queue.Empty:
                    continue
                if msg is None:
                    break
                yield _sse_event(msg)

            t2.join()

            if "video_path" in result_box2:
                rel = Path(result_box2["video_path"]).relative_to(PROJECT_DIR)
                yield f"event: video\ndata: /api/media/{rel}\n\n"
        finally:
            _active_jobs.pop(job_id, None)

        yield "event: done\ndata: done\n\n"

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )


@app.post("/api/projects/{project_id}/stitch")
def stitch_project(project_id: str):
    info_path = PROJECTS_DIR / project_id / "project_info.json"
    if not info_path.exists():
        raise HTTPException(404, "Project not found")

    log_q: queue.Queue = queue.Queue()
    result_box: dict = {}

    def gen():
        t = threading.Thread(
            target=_run_stitch_thread,
            args=(project_id, log_q, result_box),
            daemon=True,
        )
        t.start()

        yield _sse_event("Starting stitch...")

        while True:
            try:
                msg = log_q.get(timeout=0.2)
            except queue.Empty:
                continue
            if msg is None:
                break
            yield _sse_event(msg)

        t.join()

        if "video_path" in result_box:
            try:
                rel = Path(result_box["video_path"]).relative_to(RUNS_DIR)
                yield f"event: video\ndata: /api/media/{rel}\n\n"
            except ValueError:
                yield f"event: video\ndata: {result_box['video_path']}\n\n"

        yield "event: done\ndata: done\n\n"

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )


# ---------------------------------------------------------------------------
# Routes: Importable sources
# ---------------------------------------------------------------------------

@app.get("/api/importable-sources")
def importable_sources():
    sources = []

    if RUNS_DIR.exists():
        for d in sorted(RUNS_DIR.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            if not d.is_dir() or d.name == "projects":
                continue
            info = _read_run_info(d)
            if info is None:
                continue
            sources.append({
                "type": "run",
                "path": d.name,
                "label": f"{d.name[:8]}… — {info['query'].replace(chr(10), ' ')[:50]}",
            })

    if PROJECTS_DIR.exists():
        for proj_d in sorted(PROJECTS_DIR.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            if not proj_d.is_dir():
                continue
            info_path = proj_d / "project_info.json"
            if not info_path.exists():
                continue
            try:
                proj_info = json.loads(info_path.read_text(encoding="utf-8"))
                for entry in proj_info.get("scenes", []):
                    scene_dir = RUNS_DIR / entry["scene_dir"]
                    if (scene_dir / "run_info.json").exists():
                        sources.append({
                            "type": "scene",
                            "path": entry["scene_dir"],
                            "label": f"{proj_info['project_id'][:8]}… #{entry['scene_index']} — {entry.get('query', '—')[:40]}",
                        })
            except Exception:
                pass

    # Deduplicate by path — an imported scene may reference the same dir as a standalone run
    seen: set[str] = set()
    unique: list[dict] = []
    for s in sources:
        if s["path"] not in seen:
            seen.add(s["path"])
            unique.append(s)
    return unique


# ---------------------------------------------------------------------------
# Media file serving
# ---------------------------------------------------------------------------

@app.get("/api/media/{file_path:path}")
def serve_media(file_path: str):
    full_path = RUNS_DIR / file_path
    if not full_path.exists() or not full_path.is_file():
        raise HTTPException(404, "File not found")
    # Security: ensure the path is within RUNS_DIR
    try:
        full_path.resolve().relative_to(RUNS_DIR.resolve())
    except ValueError:
        raise HTTPException(403, "Access denied")
    return FileResponse(str(full_path))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080, reload=False)
