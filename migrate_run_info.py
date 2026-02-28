"""
Migrate old run_info.txt files to run_info.json.

The old format is:
    Run ID: <uuid>
    Query: <query, possibly multi-line>
    Audience: <audience>

Strategy: anchor on the last occurrence of "\nAudience: " to split off the
audience, and on the first "Query: " to split off the run_id block, so
any newlines inside the query are captured correctly.
"""
import json
import re
import sys
from pathlib import Path

RUNS_DIR = Path("agentic_video_gen/runs")

# Matches the whole file: run_id on its own line, then query (greedy across
# newlines), then audience on its own line at the end.
_PATTERN = re.compile(
    r"^Run ID:\s*(?P<run_id>.+?)\n"
    r"Query:\s*(?P<query>[\s\S]+?)\n"
    r"Audience:\s*(?P<audience>.+?)\s*$",
    re.MULTILINE,
)


def migrate(runs_dir: Path, dry_run: bool = False) -> None:
    if not runs_dir.exists():
        print(f"Runs directory not found: {runs_dir}")
        sys.exit(1)

    txt_files = sorted(runs_dir.glob("*/run_info.txt"))
    if not txt_files:
        print("No run_info.txt files found.")
        return

    for txt_path in txt_files:
        json_path = txt_path.with_suffix(".json").with_name("run_info.json")
        run_id = txt_path.parent.name

        if json_path.exists():
            print(f"[SKIP]  {run_id} — run_info.json already exists")
            continue

        raw = txt_path.read_text(encoding="utf-8")
        m = _PATTERN.search(raw)
        if not m:
            print(f"[ERROR] {run_id} — could not parse run_info.txt, skipping")
            print(f"        Content: {raw!r}")
            continue

        data = {
            "run_id":   m.group("run_id").strip(),
            "query":    m.group("query").strip(),
            "audience": m.group("audience").strip(),
        }

        print(f"[{'DRY' if dry_run else 'OK'}]   {run_id}")
        print(f"        query    = {data['query'][:80]!r}{'...' if len(data['query']) > 80 else ''}")
        print(f"        audience = {data['audience']!r}")

        if not dry_run:
            json_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    print("\nDone.")


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    if dry_run:
        print("--- DRY RUN (no files written) ---\n")
    migrate(RUNS_DIR, dry_run=dry_run)
