"""
Project lifecycle management for multi-scene video projects.

A project groups multiple pipeline runs (scenes) into a single entity,
enabling cross-scene context injection and final video stitching.
"""
import json
import shutil
import uuid
from pathlib import Path
from typing import Optional

from agentic_video_gen.pipeline import RUNS_DIR, run_pipeline
from agentic_video_gen.schemas import SceneContext, ScriptSegments, SolvedSteps

PROJECTS_DIR = RUNS_DIR / "projects"


# ---------------------------------------------------------------------------
# Project info helpers
# ---------------------------------------------------------------------------

def load_project_info(project_dir: Path) -> dict:
    path = project_dir / "project_info.json"
    return json.loads(path.read_text(encoding="utf-8"))


def save_project_info(project_dir: Path, info: dict) -> None:
    path = project_dir / "project_info.json"
    path.write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Project creation
# ---------------------------------------------------------------------------

def create_project(
    audience: str,
    carry_solver_context: bool,
    project_id: str | None = None,
) -> tuple[str, Path]:
    """Create a new project directory and project_info.json.

    Returns (project_id, project_dir).
    """
    if project_id is None:
        project_id = "proj_" + str(uuid.uuid4())[:8]

    project_dir = PROJECTS_DIR / project_id
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "scenes").mkdir(exist_ok=True)

    info = {
        "project_id": project_id,
        "audience": audience,
        "carry_solver_context": carry_solver_context,
        "scenes": [],
    }
    save_project_info(project_dir, info)
    print(f"[project] Created project {project_id} at {project_dir}")
    return project_id, project_dir


# ---------------------------------------------------------------------------
# Scene directory resolution
# ---------------------------------------------------------------------------

def resolve_scene_dir(scene_entry: dict) -> Path:
    """Resolve a scene entry's scene_dir (relative to RUNS_DIR) to an absolute Path."""
    return RUNS_DIR / scene_entry["scene_dir"]


# ---------------------------------------------------------------------------
# Adding / removing scenes
# ---------------------------------------------------------------------------

def _shift_scenes_up(project_dir: Path, from_index: int) -> None:
    """Increment scene_index for all scenes >= from_index.

    For native scenes, also renames the scene directory on disk so the
    directory name stays in sync with the index.
    """
    info = load_project_info(project_dir)
    project_id = info["project_id"]

    # Process in reverse order to avoid collisions (e.g. 3→4 before 2→3)
    affected = sorted(
        [s for s in info["scenes"] if s["scene_index"] >= from_index],
        key=lambda s: s["scene_index"],
        reverse=True,
    )
    for entry in affected:
        new_idx = entry["scene_index"] + 1
        if entry["source"] == "native":
            old_dir = RUNS_DIR / entry["scene_dir"]
            new_scene_rel = f"projects/{project_id}/scenes/{new_idx}"
            new_dir = RUNS_DIR / new_scene_rel
            if old_dir.exists():
                old_dir.rename(new_dir)
            entry["scene_dir"] = new_scene_rel
        entry["scene_index"] = new_idx

    info["scenes"].sort(key=lambda s: s["scene_index"])
    save_project_info(project_dir, info)
    print(f"[project] Shifted scenes >= {from_index} up by 1")


def add_native_scene(project_dir: Path, scene_index: int, query: str, insert_shift: bool = False) -> Path:
    """Append a native scene entry to project_info.json and create its directory.

    If insert_shift=True and a scene already exists at scene_index, all scenes
    at >= scene_index are shifted up by one before inserting.

    Returns the scene directory path.
    """
    info = load_project_info(project_dir)
    project_id = info["project_id"]

    existing = {s["scene_index"] for s in info["scenes"]}
    if insert_shift and scene_index in existing:
        _shift_scenes_up(project_dir, scene_index)
        info = load_project_info(project_dir)  # reload after shift

    scene_dir_rel = f"projects/{project_id}/scenes/{scene_index}"
    scene_dir_abs = RUNS_DIR / scene_dir_rel
    scene_dir_abs.mkdir(parents=True, exist_ok=True)

    entry = {
        "scene_index": scene_index,
        "query": query,
        "scene_dir": scene_dir_rel,
        "source": "native",
    }
    # Replace existing entry with same index if present (replace, not shift)
    info["scenes"] = [s for s in info["scenes"] if s["scene_index"] != scene_index]
    info["scenes"].append(entry)
    info["scenes"].sort(key=lambda s: s["scene_index"])
    save_project_info(project_dir, info)

    return scene_dir_abs


def import_scene(
    project_dir: Path,
    scene_index: int,
    source_run_dir: Path,
    query_override: str | None = None,
) -> None:
    """Append an imported scene entry referencing an existing run directory.

    No files are copied — only a reference is stored.
    """
    # source_run_dir can be absolute or relative to RUNS_DIR.
    # Resolve both to absolute paths before computing the relative reference.
    runs_dir_abs = RUNS_DIR.resolve()
    if source_run_dir.is_absolute():
        rel = source_run_dir.relative_to(runs_dir_abs)
    else:
        rel = source_run_dir

    # Derive query from run_info.json if no override provided
    abs_dir = RUNS_DIR / rel
    if query_override:
        query = query_override
    else:
        run_info_path = abs_dir / "run_info.json"
        if run_info_path.exists():
            run_info = json.loads(run_info_path.read_text(encoding="utf-8"))
            query = run_info.get("query", str(rel))
        else:
            query = str(rel)

    info = load_project_info(project_dir)
    entry = {
        "scene_index": scene_index,
        "query": query,
        "scene_dir": str(rel),
        "source": "imported",
    }
    info["scenes"] = [s for s in info["scenes"] if s["scene_index"] != scene_index]
    info["scenes"].append(entry)
    info["scenes"].sort(key=lambda s: s["scene_index"])
    save_project_info(project_dir, info)
    print(f"[project] Imported scene {scene_index} from {rel}")


def remove_scene(project_dir: Path, scene_index: int) -> None:
    """Remove a scene entry. If native, also deletes its directory.

    Imported source directories are never touched.
    """
    info = load_project_info(project_dir)
    to_remove = [s for s in info["scenes"] if s["scene_index"] == scene_index]

    for entry in to_remove:
        if entry["source"] == "native":
            scene_dir = resolve_scene_dir(entry)
            if scene_dir.exists():
                shutil.rmtree(scene_dir)
                print(f"[project] Deleted native scene dir {scene_dir}")

    info["scenes"] = [s for s in info["scenes"] if s["scene_index"] != scene_index]
    save_project_info(project_dir, info)
    print(f"[project] Removed scene {scene_index} from project")


# ---------------------------------------------------------------------------
# Fork project
# ---------------------------------------------------------------------------

def fork_project(
    src_project_dir: Path,
    project_id: str | None = None,
) -> tuple[str, Path]:
    """Fork a project: copy project_info.json (with new id), copy native scene dirs.

    Imported references are preserved as-is.
    Returns (new_project_id, new_project_dir).
    """
    if project_id is None:
        project_id = "proj_" + str(uuid.uuid4())[:8]

    new_project_dir = PROJECTS_DIR / project_id
    new_project_dir.mkdir(parents=True, exist_ok=True)
    (new_project_dir / "scenes").mkdir(exist_ok=True)

    src_info = load_project_info(src_project_dir)
    src_project_id = src_info["project_id"]

    new_scenes = []
    for entry in src_info["scenes"]:
        new_entry = dict(entry)
        if entry["source"] == "native":
            # Repoint to new project's scenes dir
            old_abs = resolve_scene_dir(entry)
            new_scene_rel = f"projects/{project_id}/scenes/{entry['scene_index']}"
            new_scene_abs = RUNS_DIR / new_scene_rel
            if old_abs.exists():
                shutil.copytree(old_abs, new_scene_abs)
            else:
                new_scene_abs.mkdir(parents=True, exist_ok=True)
            new_entry["scene_dir"] = new_scene_rel
        # imported entries keep their scene_dir unchanged
        new_scenes.append(new_entry)

    new_info = dict(src_info)
    new_info["project_id"] = project_id
    new_info["scenes"] = new_scenes
    save_project_info(new_project_dir, new_info)

    print(f"[project] Forked {src_project_id} → {project_id}")
    return project_id, new_project_dir


# ---------------------------------------------------------------------------
# Context extraction for multi-scene prompts
# ---------------------------------------------------------------------------

def get_previous_scenes_context(
    project_dir: Path,
    up_to_scene: int,
    carry_solver_context: bool,
) -> list[SceneContext]:
    """Build SceneContext list for all scenes with index < up_to_scene."""
    info = load_project_info(project_dir)
    contexts: list[SceneContext] = []

    for entry in info["scenes"]:
        if entry["scene_index"] >= up_to_scene:
            continue
        scene_dir = resolve_scene_dir(entry)

        # Load script from checkpoint 2
        script_path = scene_dir / "checkpoint_step2_script.json"
        if not script_path.exists():
            print(f"[project] Warning: no script checkpoint for scene {entry['scene_index']} at {scene_dir}")
            continue
        script = ScriptSegments.model_validate_json(script_path.read_text(encoding="utf-8"))

        # Optionally load solver result from checkpoint 1
        solver_result: Optional[SolvedSteps] = None
        if carry_solver_context:
            solver_path = scene_dir / "checkpoint_step1_solved.json"
            if solver_path.exists():
                solver_result = SolvedSteps.model_validate_json(
                    solver_path.read_text(encoding="utf-8")
                )

        contexts.append(
            SceneContext(
                scene_index=entry["scene_index"],
                query=entry["query"],
                script=script,
                solver_result=solver_result,
            )
        )

    return contexts


# ---------------------------------------------------------------------------
# Run a scene within a project
# ---------------------------------------------------------------------------

def run_project_scene(
    project_id: str,
    scene_index: int,
    query: str,
    audience_level: str,
    carry_solver_context: bool,
    from_step: int = 1,
    nudges: dict[int, str] | None = None,
    force_fix_prompt: str | None = None,
    force_fix_image: str | None = None,
    insert_shift: bool = False,
    model_provider: str = "google",
    tts_provider: str = "local",
) -> Path:
    """Run (or resume) a native scene within a project.

    Registers the scene entry in project_info.json, collects context from
    earlier scenes, and delegates to run_pipeline().

    Returns the scene run directory.
    """
    project_dir = PROJECTS_DIR / project_id
    if not project_dir.exists():
        raise FileNotFoundError(f"Project not found: {project_dir}")

    # Ensure scene entry exists (creates dir if needed)
    add_native_scene(project_dir, scene_index, query, insert_shift=insert_shift)

    # Derive run_id from the scene dir name relative to RUNS_DIR
    # The scene dir is RUNS_DIR/projects/{project_id}/scenes/{scene_index}
    # We use the relative path as a stable identifier for run_pipeline
    # run_pipeline expects run_id to be joined with RUNS_DIR, so we pass the relative path
    info = load_project_info(project_dir)
    matching = [s for s in info["scenes"] if s["scene_index"] == scene_index]
    scene_dir_rel = matching[0]["scene_dir"]  # e.g. "projects/proj_abc/scenes/1"

    # Gather context from earlier scenes
    previous_ctx = get_previous_scenes_context(project_dir, scene_index, carry_solver_context)

    # run_pipeline uses RUNS_DIR / run_id as the run directory
    run_dir = run_pipeline(
        query=query,
        audience_level=audience_level,
        run_id=scene_dir_rel,
        from_step=from_step,
        nudges=nudges,
        previous_scenes_context=previous_ctx if previous_ctx else None,
        force_fix_prompt=force_fix_prompt,
        force_fix_image=force_fix_image,
        model_provider=model_provider,
        tts_provider=tts_provider,
    )

    print(f"[project] Scene {scene_index} complete → {run_dir}")
    return run_dir
