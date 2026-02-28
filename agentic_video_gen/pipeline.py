import json
import os
import re
import sys
import uuid
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv
from pydantic_ai.messages import ModelResponse, TextPart

from agentic_video_gen.schemas import (
    SolvedSteps,
    ScriptSegments,
    VisualAssets,
    AssetMetadata,
    ManimCode,
)
from agentic_video_gen.agents import (
    get_solver_agent,
    get_script_agent,
    get_svg_agent,
    get_manim_agent,
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


def _log_model_call(run_dir: Path, step: int | str, prompt: str, result) -> None:
    """Append one JSONL entry to logs/model_interactions.jsonl for every agent call."""
    logs_dir = run_dir / "logs"
    logs_dir.mkdir(exist_ok=True)

    # Extract raw text parts from the model response messages
    response_texts = []
    for msg in result.all_messages():
        if isinstance(msg, ModelResponse):
            for part in msg.parts:
                if isinstance(part, TextPart):
                    response_texts.append(part.content)

    # Token usage (may not always be populated)
    usage = result.usage()
    usage_dict = {
        "requests": usage.requests,
        "request_tokens": usage.request_tokens,
        "response_tokens": usage.response_tokens,
        "total_tokens": usage.total_tokens,
    }

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "step": step,
        "step_name": _STEP_NAMES.get(step, str(step)),
        "prompt": prompt,
        "response_text": "\n---\n".join(response_texts),
        "output": json.loads(result.output.model_dump_json()),
        "usage": usage_dict,
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


def run_pipeline(
    query: str,
    audience_level: str = DEFAULT_AUDIENCE,
    run_id: str | None = None,
    from_step: int = 1,
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

    # --------------------------------------------------
    # Node 1: Analytical Solver
    # --------------------------------------------------
    if from_step <= 1:
        print("\n[Step 1] Solving / Analyzing the topic...")
        solver_agent = get_solver_agent()
        _prompt1 = f"Audience Level: {audience_level}\nQuery: {query}"
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
        script_agent = get_script_agent()
        _prompt2 = (
            f"Audience Level: {audience_level}\n"
            f"Original Query: {query}\n\n"
            f"Analytical Solution:\n{solved_steps.model_dump_json(indent=2)}"
        )
        script_result = script_agent.run_sync(_prompt2)
        script: ScriptSegments = script_result.output
        _log_model_call(run_dir, 2, _prompt2, script_result)
        _save_checkpoint(run_dir, 2, script)
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
        svg_agent = get_svg_agent()
        _prompt3 = (
            f"Audience Level: {audience_level}\n"
            f"Original Query: {query}\n\n"
            f"Analytical Solution:\n{solved_steps.model_dump_json(indent=2)}\n\n"
            f"Voiceover Script:\n{script.model_dump_json(indent=2)}"
        )
        svg_result = svg_agent.run_sync(_prompt3)
        svgs: VisualAssets = svg_result.output
        _log_model_call(run_dir, 3, _prompt3, svg_result)
        _save_checkpoint(run_dir, 3, svgs)

        assets_dict = {asset.name: asset.raw_svg_code for asset in svgs.assets}
        setup_assets_impl(assets_dir, assets_dict)
        generate_sounds_from_api(script.segments, audios_dir)
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
        manim_agent = get_manim_agent()
        _prompt4 = (
            f"Audience Level: {audience_level}\n"
            f"Original Query: {query}\n\n"
            f"Analytical Solution:\n{solved_steps.model_dump_json(indent=2)}\n\n"
            f"Voiceover Script (use segment ids exactly as they are for self.speech()):\n"
            f"{script.model_dump_json(indent=2)}\n\n"
            f"Available SVG Assets (load with self.get_svg(name)):\n"
            f"{asset_metadata_list}\n\n"
            f"Run directory (pass as run_dir to super().__init__ or handle via env): {run_dir}"
        )
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

    # Also write a small metadata file for reference
    with open(run_dir / "run_info.txt", "w", encoding="utf-8") as f:
        f.write(f"Run ID: {run_id}\nQuery: {query}\nAudience: {audience_level}\n")

    # --------------------------------------------------
    # Node 5: Compilation Validation Loop (self-correcting)
    # --------------------------------------------------
    if from_step <= 5:
        print("\n[Step 5] Compiling Manim scene (with self-correction)...")
        manim_bin = "/Users/aalamiid/miniconda3/envs/audio_tts/bin/manim"
        max_retries = 3
        run_env = {**os.environ, "MANIM_RUN_DIR": str(run_dir.resolve())}

        for attempt in range(max_retries):
            print(f"  Attempt {attempt + 1}/{max_retries}...")
            compilation = subprocess.run(
                [manim_bin, "-ql", "--dry_run", str(out_file), "GeneratedEducationalScene"],
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
                print(f"\n  ❌ Compilation failed. Error:\n{error_trace[:500]}")

                _fix_prompt = (
                    f"Your Manim code failed to compile. Error:\n{error_trace}\n\n"
                    f"Please fix the code and return the complete corrected Python file."
                )
                fix_result = get_manim_agent().run_sync(_fix_prompt)
                _log_model_call(run_dir, "manim_fix", _fix_prompt, fix_result)
                fixed_code = extract_code_fence(fix_result.output.python_code)
                with open(out_file, "w", encoding="utf-8") as f:
                    f.write(fixed_code)
        else:
            print("\n⚠️  Could not compile after max retries. Inspect the file manually.")

    print(f"\nDone! Run artifacts saved to: {run_dir}/")
    print("To render the video, run:")
    print(f"  manim -qm {out_file} GeneratedEducationalScene")
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

    # Load query / audience from run_info.txt
    info_file = run_dir / "run_info.txt"
    if not info_file.exists():
        raise FileNotFoundError(f"run_info.txt missing in {run_dir}")

    info = {}
    for line in info_file.read_text(encoding="utf-8").splitlines():
        if ": " in line:
            k, v = line.split(": ", 1)
            info[k.strip()] = v.strip()

    query = info.get("Query", "")
    audience_level = info.get("Audience", DEFAULT_AUDIENCE)

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
