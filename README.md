# Aji Nafhem — أجي نفهم
### AI-Powered Moroccan Darija Educational Video Generator

**Aji Nafhem** (أجي نفهم, "come, let's understand" in Moroccan Darija) is an agentic pipeline that turns any educational topic into a fully animated, voiced video — with narration in Moroccan Darija and Manim-rendered visuals.

---

## How It Works

The pipeline runs five sequential AI-powered steps:

```
Topic / Question
      │
      ▼
[Step 1] Analytical Solver        → breaks the topic into logical steps
      │
      ▼
[Step 2] Script & TTS             → writes a Darija voiceover script + generates audio
      │
      ▼
[Step 3] SVG Asset Generator      → creates flat-design vector illustrations
      │
      ▼
[Step 4] Manim Code Generator     → writes a complete animated Python scene
      │
      ▼
[Step 5] Compile & Auto-Fix       → runs Manim, self-corrects errors (up to 3 retries)
      │
      ▼
  MP4 Video
```

Each step saves a JSON checkpoint so runs can be resumed or forked from any point.

---

## Features

- **Moroccan Darija narration** — scripts written and voiced in Darija Arabic with full tashkeel for TTS clarity
- **Agentic self-correction** — Manim compilation errors are automatically diagnosed and patched by a fix agent
- **Resumable runs** — every step is checkpointed; restart from any step without re-running earlier ones
- **Run forking** — resume a run as a copy, leaving the original untouched
- **Per-step nudges** — inject extra instructions into any step's LLM prompt when resuming (e.g. "use warmer colors", "add more humor")
- **Gradio UI** — browser interface for generating new videos and managing existing runs

---

## Project Structure

```
nafham/
├── agentic_video_gen/
│   ├── agents.py          # LLM agents (Gemini) for each pipeline step
│   ├── pipeline.py        # Orchestration logic + checkpoint management
│   ├── base_scene.py      # BaseEducationalScene — Manim base class with helpers
│   ├── schemas.py         # Pydantic models for all inter-step data
│   ├── utils.py           # TTS API client + asset writing
│   └── runs/              # One folder per run (UUID), containing all artifacts
│       └── <run-id>/
│           ├── run_info.json
│           ├── checkpoint_step1_solved.json
│           ├── checkpoint_step2_script.json
│           ├── checkpoint_step3_svgs.json
│           ├── checkpoint_step4_manim.json
│           ├── generated_scene.py
│           ├── assets/            # SVG files
│           ├── audios/            # WAV files per segment
│           └── logs/              # model_interactions.jsonl
├── gradio_app.py          # Browser UI
├── migrate_run_info.py    # Migrate old run_info.txt → run_info.json
└── .env                   # GEMINI_API_KEY
```

---

## Setup

**Requirements:** Python 3.11+, [Manim Community Edition](https://docs.manim.community/en/stable/installation.html)

```bash
# Install dependencies
uv pip install -r requirements.txt   # or: pip install -e .

# Set your Gemini API key
echo "GEMINI_API_KEY=your_key_here" > .env
```

### TTS Server

Aji Nafhem uses a local [Coqui XTTS](https://github.com/coqui-ai/TTS) model fine-tuned on Moroccan Darija, specifically [`medmac01/darija_xtt_2.0`](https://huggingface.co/medmac01/darija_xtt_2.0) from Hugging Face. The pipeline calls it at `http://localhost:8000/tts`.

**Download the model** from Hugging Face: [medmac01/darija_xtt_2.0](https://huggingface.co/medmac01/darija_xtt_2.0)

**Required files** — place these under `model/` in the project root:

```
model/
├── model.pth               # fine-tuned XTTS checkpoint
├── config.json             # XTTS config
├── vocab.json              # vocabulary
└── speaker_reference.wav   # reference audio for voice cloning
```

**Start the server** before running any pipeline:

```bash
# Runs on port 8000, uses Apple MPS by default (change device in coqui_server.py for CUDA/CPU)
python coqui_server.py
```

Health check: `curl http://localhost:8000/health` → `{"status": "ok"}`

> If the TTS server is unreachable, the pipeline will substitute 1-second silent WAV files so Manim can still compile and render — the video will have no voiceover but all animations will be present.

---

## Usage

### Gradio UI (recommended)

```bash
python gradio_app.py
# Opens at http://localhost:7861
```

**New Video tab** — enter a topic and audience level, click Generate.

**Resume Run tab** — pick an existing run, choose which step to restart from, optionally:
- Check *Copy to new run* to fork instead of overwrite
- Expand *Per-step nudges* to add extra instructions to any step's prompt

### CLI

```bash
# New run
python -m agentic_video_gen.pipeline run "How does photosynthesis work?" --audience "7th grade student"

# Resume from a specific step
python -m agentic_video_gen.pipeline resume <run-id> --from-step 3
```

### Render a finished scene

```bash
MANIM_RUN_DIR=agentic_video_gen/runs/<run-id> \
  manim -qm agentic_video_gen/runs/<run-id>/generated_scene.py GeneratedEducationalScene
```

---

## Models

| Step | Model |
|------|-------|
| Solver, Script, SVG, Manim, Fix | `gemini-3-flash-preview` |

Configure in `agentic_video_gen/agents.py`.

---

## Migrating Old Runs

If you have runs with the legacy `run_info.txt` format:

```bash
python migrate_run_info.py --dry-run   # preview
python migrate_run_info.py             # apply
```
