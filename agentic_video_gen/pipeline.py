import json
import os
import re
import sys
import uuid
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv

from agentic_video_gen.schemas import (
    SolvedSteps,
    ScriptSegments,
    VisualAssets,
    AssetMetadata,
    ManimCode,
)
from pydantic_ai import BinaryContent
from agentic_video_gen.agents import (
    get_solver_agent,
    get_script_agent,
    get_script_review_agent,
    get_svg_agent,
    get_manim_agent,
    get_manim_fix_agent,
)
from agentic_video_gen.utils import generate_sounds_from_api, setup_assets_impl

DEFAULT_AUDIENCE = "high school student"
RUNS_DIR = Path("agentic_video_gen/runs")

# Load .env as early as possible so GEMINI_API_KEY is set before agents initialize
load_dotenv(os.path.join(os.getcwd(), ".env"))

_CHECKPOINTS = {
    1: ("checkpoint_step1_solved.json", SolvedSteps),
    2: ("checkpoint_step2_script.json", ScriptSegments),
    3: ("checkpoint_step3_svgs.json", VisualAssets),
    4: ("checkpoint_step4_manim.json", ManimCode),
}


_STEP_NAMES = {
    1: "solver",
    2: "script",
    3: "svg",
    4: "manim",
    "manim_fix": "manim_fix",
}


def _log_model_call(run_dir: Path, step: int | str, _prompt: str, result) -> None:
    """Append one JSONL entry to logs/model_interactions.jsonl for every agent call."""
    logs_dir = run_dir / "logs"
    logs_dir.mkdir(exist_ok=True)

    usage = result.usage()

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "step": step,
        "step_name": _STEP_NAMES.get(step, str(step)),
        # Full message exchange: system prompt + user turn + model response
        "messages": json.loads(result.all_messages_json()),
        "output": json.loads(result.output.model_dump_json()),
        "usage": {
            "requests": usage.requests,
            "request_tokens": usage.request_tokens,
            "response_tokens": usage.response_tokens,
            "total_tokens": usage.total_tokens,
        },
    }

    log_file = logs_dir / "model_interactions.jsonl"
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def extract_code_fence(text: str) -> str:
    """
    Extracts the content of the first code block found in the text,
    effectively removing any 'yapping' (preamble or postscript).
    """
    pattern = r"```(?:\w+)?\n(.*?)\n```"
    match = re.search(pattern, text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return text.strip()


def _save_checkpoint(run_dir: Path, step: int, data) -> None:
    filename, _ = _CHECKPOINTS[step]
    path = run_dir / filename
    with open(path, "w", encoding="utf-8") as f:
        f.write(data.model_dump_json(indent=2))
    print(f"  [checkpoint] Saved step {step} → {path.name}")


def _load_checkpoint(run_dir: Path, step: int):
    filename, model_cls = _CHECKPOINTS[step]
    path = run_dir / filename
    if not path.exists():
        raise FileNotFoundError(
            f"Checkpoint for step {step} not found at {path}. "
            "Run earlier steps first."
        )
    with open(path, encoding="utf-8") as f:
        return model_cls.model_validate_json(f.read())


def _detect_completed_steps(run_dir: Path) -> list[int]:
    """Return a sorted list of step numbers whose checkpoints exist."""
    return [s for s, (fname, _) in _CHECKPOINTS.items() if (run_dir / fname).exists()]


def _scene_context_block(previous_scenes_context: list) -> str:
    """Format previous scene contexts into a prompt block."""
    if not previous_scenes_context:
        return ""
    lines = ["\n\n[PREVIOUS SCENES CONTEXT — this is part of a multi-scene series]"]
    for ctx in previous_scenes_context:
        lines.append(f"\nScene {ctx.scene_index} — Query: {ctx.query}")
        lines.append(
            f"  Script (already recorded, do NOT repeat these segments):\n  {ctx.script.model_dump_json(indent=2)}"
        )
        if ctx.solver_result:
            lines.append(
                f"  Solution covered:\n  {ctx.solver_result.model_dump_json(indent=2)}"
            )
    lines.append("\n[END PREVIOUS SCENES CONTEXT]")
    return "\n".join(lines)


def run_pipeline(
    query: str,
    audience_level: str = DEFAULT_AUDIENCE,
    run_id: str | None = None,
    from_step: int = 1,
    nudges: dict[int, str] | None = None,
    previous_scenes_context: list | None = None,
    force_fix_prompt: str | None = None,
    force_fix_image: str | None = None,
    model_provider: str = "google",
):
    """
    Runs the full educational video generation pipeline.

    Pass ``run_id`` + ``from_step`` to resume a previously interrupted run.
    Each completed step saves a JSON checkpoint so the pipeline can skip it
    on the next run.

    Args:
        query:          The educational topic or problem to explain.
        audience_level: Target audience, e.g., '7th grade student'.
        run_id:         Reuse an existing run directory (for resumption).
        from_step:      Which step to start from (1–5). Steps before this
                        are loaded from saved checkpoints.
        nudges:         Optional per-step extra instructions, keyed by step
                        number (1–4). Each nudge is appended only to that
                        step's prompt. E.g. {3: "use warmer colours", 4: "..."}
        previous_scenes_context: Optional list of SceneContext objects from
                        earlier scenes in a multi-scene project. Injected into
                        steps 1, 2, and 4 prompts for narrative continuity.
        force_fix_prompt: If set, the fix agent is called once at the start of
                        step 5 with this visual-issue description (no compilation
                        error required). Use this to correct layout or overlap
                        problems spotted in the rendered video.
    """
    if run_id is None:
        run_id = str(uuid.uuid4())

    run_dir = RUNS_DIR / run_id
    assets_dir = run_dir / "assets"
    audios_dir = run_dir / "audios"

    run_dir.mkdir(parents=True, exist_ok=True)
    assets_dir.mkdir(parents=True, exist_ok=True)
    audios_dir.mkdir(parents=True, exist_ok=True)

    print("====================================")
    print(f"Run ID:     {run_id}")
    print(f"Query:      {query}")
    print(f"Audience:   {audience_level}")
    print(f"Output:     {run_dir}/")
    print(f"From step:  {from_step}")
    print("====================================")

    # Write run metadata as JSON so multi-line queries are handled correctly
    with open(run_dir / "run_info.json", "w", encoding="utf-8") as f:
        json.dump({"run_id": run_id, "query": query, "audience": audience_level, "model_provider": model_provider}, f, ensure_ascii=False, indent=2)
    print(f"Model provider: {model_provider}")
    _ctx_block = _scene_context_block(previous_scenes_context or [])

    def _nudge(step: int) -> str:
        """Return the nudge suffix for the given step, or empty string."""
        text = (nudges or {}).get(step, "").strip()
        return f"\n\n[EXTRA INSTRUCTIONS — apply to this step only]\n{text}" if text else ""

    # --------------------------------------------------
    # Node 1: Analytical Solver
    # --------------------------------------------------
    if from_step <= 1:
        print("\n[Step 1] Solving / Analyzing the topic...")
        solver_agent = get_solver_agent(model_provider)
        _prompt1 = f"Audience Level: {audience_level}\nQuery: {query}" + _ctx_block + _nudge(1)
        solver_result = solver_agent.run_sync(_prompt1)
        solved_steps: SolvedSteps = solver_result.output
        _log_model_call(run_dir, 1, _prompt1, solver_result)
        _save_checkpoint(run_dir, 1, solved_steps)
    else:
        print("\n[Step 1] Loading from checkpoint (skipped)...")
        solved_steps: SolvedSteps = _load_checkpoint(run_dir, 1)

    print(f"  Topic: {solved_steps.topic}")
    for step in solved_steps.steps:
        print(f"  Step {step.step_number} [{step.concept}]: {step.description[:80]}...")

    # --------------------------------------------------
    # Node 2: Script & TTS Generator
    # --------------------------------------------------
    if from_step <= 2:
        print("\n[Step 2] Generating voiceover script...")
        script_agent = get_script_agent(model_provider)
        _prompt2 = (
            f"Audience Level: {audience_level}\n"
            f"Original Query: {query}\n\n"
            f"Analytical Solution:\n{solved_steps.model_dump_json(indent=2)}"
        ) + _ctx_block + _nudge(2)
        script_result = script_agent.run_sync(_prompt2)
        script: ScriptSegments = script_result.output
        _log_model_call(run_dir, 2, _prompt2, script_result)

        print("\n[Step 2 — review] Checking script/visual coherence...")
        review_agent = get_script_review_agent(model_provider)
        _prompt2_review = (
            f"Original Query: {query}\n\n"
            f"Analytical Solution:\n{solved_steps.model_dump_json(indent=2)}\n\n"
            f"Draft Script:\n{script.model_dump_json(indent=2)}"
        )
        review_result = review_agent.run_sync(_prompt2_review)
        script = review_result.output
        _log_model_call(run_dir, "2_review", _prompt2_review, review_result)

        _save_checkpoint(run_dir, 2, script)
        generate_sounds_from_api(script.segments, audios_dir)
    else:
        print("\n[Step 2] Loading from checkpoint (skipped)...")
        script: ScriptSegments = _load_checkpoint(run_dir, 2)

    print(f"  Generated {len(script.segments)} segments.")
    for seg in script.segments:
        print(f"  [{seg.id}] {seg.script[:40]}...")

    # --------------------------------------------------
    # Node 3: SVG Asset Generator
    # --------------------------------------------------
    if from_step <= 3:
        print("\n[Step 3] Generating SVG assets...")
        svg_agent = get_svg_agent(model_provider)
        _prompt3 = (
            f"Audience Level: {audience_level}\n"
            f"Original Query: {query}\n\n"
            f"Analytical Solution:\n{solved_steps.model_dump_json(indent=2)}\n\n"
            f"Voiceover Script:\n{script.model_dump_json(indent=2)}"
        ) + _nudge(3)
        svg_result = svg_agent.run_sync(_prompt3)
        svgs: VisualAssets = svg_result.output
        _log_model_call(run_dir, 3, _prompt3, svg_result)
        _save_checkpoint(run_dir, 3, svgs)

        assets_dict = {asset.name: asset.raw_svg_code for asset in svgs.assets}
        setup_assets_impl(assets_dir, assets_dict)
    else:
        print("\n[Step 3] Loading from checkpoint (skipped)...")
        svgs: VisualAssets = _load_checkpoint(run_dir, 3)

    print(f"  Generated {len(svgs.assets)} SVG assets.")
    for asset in svgs.assets:
        print(f"  [{asset.name}]: {asset.semantic_content[:60]}...")

    # Strip raw SVG from metadata before passing to Manim agent
    asset_metadata_list = [
        AssetMetadata(
            name=a.name,
            semantic_content=a.semantic_content,
            usage_description=a.usage_description,
        ).model_dump()
        for a in svgs.assets
    ]

    # --------------------------------------------------
    # Node 4: Manim Code Generator
    # --------------------------------------------------
    out_file = run_dir / "generated_scene.py"

    if from_step <= 4:
        print("\n[Step 4] Generating Manim scene code...")
        manim_agent = get_manim_agent(model_provider)
        _prompt4 = (
            f"Audience Level: {audience_level}\n"
            f"Original Query: {query}\n\n"
            f"Analytical Solution:\n{solved_steps.model_dump_json(indent=2)}\n\n"
            f"Voiceover Script (use segment ids exactly as they are for self.speech()):\n"
            f"{script.model_dump_json(indent=2)}\n\n"
            f"Available SVG Assets (load with self.get_svg(name)):\n"
            f"{asset_metadata_list}\n\n"
            f"Run directory (pass as run_dir to super().__init__ or handle via env): {run_dir}"
        ) + _ctx_block + _nudge(4)
        manim_result = manim_agent.run_sync(_prompt4)
        manim_code: ManimCode = manim_result.output
        _log_model_call(run_dir, 4, _prompt4, manim_result)
        _save_checkpoint(run_dir, 4, manim_code)

        code_content = extract_code_fence(manim_code.python_code)
        with open(out_file, "w", encoding="utf-8") as f:
            f.write(code_content)
        print(f"  Scene code written to {out_file}.")
    else:
        print("\n[Step 4] Loading from checkpoint (skipped)...")
        if not out_file.exists():
            # Reconstruct from checkpoint
            manim_code: ManimCode = _load_checkpoint(run_dir, 4)
            code_content = extract_code_fence(manim_code.python_code)
            with open(out_file, "w", encoding="utf-8") as f:
                f.write(code_content)
            print(f"  Scene code restored to {out_file}.")



    # --------------------------------------------------
    # Node 5: Compilation Validation Loop (self-correcting)
    # --------------------------------------------------
    if from_step <= 5:
        print("\n[Step 5] Compiling Manim scene (with self-correction)...")
        manim_bin = "/Users/aalamiid/miniconda3/envs/audio_tts/bin/manim"
        max_retries = 3
        run_env = {**os.environ, "MANIM_RUN_DIR": str(run_dir.resolve())}

        # Force-fix pass: apply user-described visual corrections before compilation
        if force_fix_prompt and force_fix_prompt.strip():
            print(f"\n  [force-fix] Applying visual fix: {force_fix_prompt[:80]}...")
            current_code = out_file.read_text(encoding="utf-8")
            _fix_text = (
                f"The following Manim Python file has VISUAL ISSUES reported by the user "
                f"(the code compiles and runs, but the animation looks wrong).\n\n"
                f"--- VISUAL ISSUE DESCRIPTION ---\n{force_fix_prompt.strip()}\n\n"
                f"--- CURRENT SOURCE ---\n{current_code}"
            )
            if force_fix_image:
                image_bytes = Path(force_fix_image).read_bytes()
                import imghdr
                _mime = f"image/{imghdr.what(force_fix_image) or 'png'}"
                _fix_prompt = [_fix_text, BinaryContent(data=image_bytes, media_type=_mime)]
                print(f"  [force-fix] Attaching screenshot ({len(image_bytes)} bytes, {_mime})")
            else:
                _fix_prompt = _fix_text
            fix_result = get_manim_fix_agent(model_provider).run_sync(_fix_prompt)
            _log_model_call(run_dir, "manim_fix", _fix_prompt, fix_result)
            patch = fix_result.output
            print(f"  Force-fix explanation: {patch.explanation}")
            patched_code = current_code
            applied = 0
            for change in patch.changes:
                if change.old_code in patched_code:
                    patched_code = patched_code.replace(change.old_code, change.new_code, 1)
                    applied += 1
                else:
                    print(f"  ⚠️  Could not find snippet to patch:\n{change.old_code[:120]}...")
            print(f"  Applied {applied}/{len(patch.changes)} force-fix patch(es).")
            out_file.write_text(patched_code, encoding="utf-8")

        for attempt in range(max_retries):
            print(f"  Attempt {attempt + 1}/{max_retries}...")
            compilation = subprocess.run(
                [manim_bin, "-ql", "--dry_run", "--verbosity", "WARNING", str(out_file), "GeneratedEducationalScene"],
                capture_output=True,
                text=True,
                env=run_env,
                cwd="/Users/aalamiid/Documents/arabic_tts",
            )

            if compilation.returncode == 0:
                print("\n✅ Manim compilation successful!")
                break
            else:
                error_trace = (compilation.stderr or "") + (compilation.stdout or "")
                print(f"\n  ❌ Compilation failed. Error:\n{error_trace}")

                current_code = out_file.read_text(encoding="utf-8")
                _fix_prompt = (
                    f"The following Manim Python file failed to compile.\n\n"
                    f"--- COMPILATION ERROR ---\n{error_trace}\n\n"
                    f"--- CURRENT SOURCE ---\n{current_code}"
                )
                fix_result = get_manim_fix_agent(model_provider).run_sync(_fix_prompt)
                _log_model_call(run_dir, "manim_fix", _fix_prompt, fix_result)

                patch = fix_result.output
                print(f"  Fix explanation: {patch.explanation}")
                patched_code = current_code
                applied = 0
                for change in patch.changes:
                    if change.old_code in patched_code:
                        patched_code = patched_code.replace(change.old_code, change.new_code, 1)
                        applied += 1
                    else:
                        print(f"  ⚠️  Could not find snippet to patch:\n{change.old_code[:120]}...")
                print(f"  Applied {applied}/{len(patch.changes)} patch(es).")
                out_file.write_text(patched_code, encoding="utf-8")
        else:
            print("\n⚠️  Could not compile after max retries. Inspect the file manually.")

    print(f"\nDone! Run artifacts saved to: {run_dir}/")
    print("To render the video, run:")
    print(f"MANIM_RUN_DIR={run_dir} manim -qm {out_file} GeneratedEducationalScene")
    return run_dir


def resume_pipeline(run_id: str, from_step: int | None = None):
    """
    Resume a previously interrupted pipeline run.

    If ``from_step`` is not given, it is auto-detected as the step after
    the last completed checkpoint found in the run directory.

    Args:
        run_id:    The UUID of the existing run (folder name under runs/).
        from_step: Step to restart from (1–5). Auto-detected if omitted.
    """
    run_dir = RUNS_DIR / run_id
    if not run_dir.exists():
        raise FileNotFoundError(f"Run directory not found: {run_dir}")

    # Load query / audience from run_info.json (falls back to legacy run_info.txt)
    info_json = run_dir / "run_info.json"
    info_txt = run_dir / "run_info.txt"
    if info_json.exists():
        info = json.loads(info_json.read_text(encoding="utf-8"))
        query = info.get("query", "")
        audience_level = info.get("audience", DEFAULT_AUDIENCE)
    elif info_txt.exists():
        info = {}
        for line in info_txt.read_text(encoding="utf-8").splitlines():
            if ": " in line:
                k, v = line.split(": ", 1)
                info[k.strip()] = v.strip()
        query = info.get("Query", "")
        audience_level = info.get("Audience", DEFAULT_AUDIENCE)
    else:
        raise FileNotFoundError(f"run_info.json missing in {run_dir}")

    if from_step is None:
        completed = _detect_completed_steps(run_dir)
        from_step = (max(completed) + 1) if completed else 1
        print(f"Auto-detected resume point: step {from_step} "
              f"(completed steps: {completed or 'none'})")

    return run_pipeline(
        query=query,
        audience_level=audience_level,
        run_id=run_id,
        from_step=from_step,
    )


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Run or resume the educational video generation pipeline."
    )
    subparsers = parser.add_subparsers(dest="command")

    # --- run ---
    run_parser = subparsers.add_parser("run", help="Start a new pipeline run.")
    run_parser.add_argument("query", help='Educational topic, e.g. "how does gravity work"')
    run_parser.add_argument(
        "--audience", default=DEFAULT_AUDIENCE, help="Target audience level."
    )

    # --- resume ---
    resume_parser = subparsers.add_parser("resume", help="Resume an interrupted run.")
    resume_parser.add_argument("run_id", help="UUID of the run to resume.")
    resume_parser.add_argument(
        "--from-step",
        type=int,
        choices=[1, 2, 3, 4, 5],
        default=None,
        help="Force restart from this step (auto-detected if omitted).",
    )

    args = parser.parse_args()

    if args.command == "run":
        run_pipeline(args.query, audience_level=args.audience)
    elif args.command == "resume":
        resume_pipeline(args.run_id, from_step=args.from_step)
    else:
        # Legacy positional-arg fallback
        if len(sys.argv) < 2:
            parser.print_help()
            sys.exit(1)
        user_query = sys.argv[1]
        user_audience = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_AUDIENCE
        run_pipeline(user_query, audience_level=user_audience)


if __name__ == "__main__":
    main()
