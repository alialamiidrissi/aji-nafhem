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
[Step 2r] Script Review           → checks script↔visual coherence, fixes tashkeel & pacing
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
- **Script review agent** — automatically checks that each spoken segment matches its visual action, fixes pacing, and enforces TTS-friendly phonetics
- **Agentic self-correction** — Manim compilation errors are automatically diagnosed and patched by a fix agent
- **Multi-provider LLM support** — switch between Google Gemini, OpenAI, or OpenRouter via a UI dropdown or environment variable
- **Multi-scene projects** — build long-form videos from multiple scenes, with optional context carry-over between scenes
- **Resumable runs** — every step is checkpointed; restart from any step without re-running earlier ones
- **Run forking** — resume a run as a copy, leaving the original untouched
- **Per-step nudges** — inject extra instructions into any step's LLM prompt when resuming
- **Next.js UI** — modern browser interface for generating new videos, managing projects, and re-running individual scenes

---

## Project Structure

```
aji-nafhem/
├── agentic_video_gen/
│   ├── agents.py           # LLM agents for each pipeline step
│   ├── pipeline.py         # Orchestration + checkpoint management
│   ├── base_scene.py       # BaseEducationalScene — Manim base class
│   ├── schemas.py          # Pydantic models for inter-step data
│   ├── utils.py            # TTS API client + asset writing
│   ├── projects.py         # Multi-scene project management
│   ├── stitch.py           # ffmpeg-based video stitching
│   └── runs/               # One folder per run (UUID)
│       ├── <run-id>/
│       │   ├── run_info.json
│       │   ├── checkpoint_step1_solved.json
│       │   ├── checkpoint_step2_script.json
│       │   ├── checkpoint_step3_svgs.json
│       │   ├── checkpoint_step4_manim.json
│       │   ├── generated_scene.py
│       │   ├── rendered_video.mp4
│       │   ├── assets/             # SVG files
│       │   ├── audios/             # WAV files per segment
│       │   └── logs/               # model_interactions.jsonl
│       └── projects/
│           └── <project-id>/
│               ├── project_info.json
│               └── scenes/
├── web_server.py           # FastAPI backend — REST + SSE endpoints (port 8080)
├── web_ui/                 # Next.js 16 + shadcn/ui frontend (port 3000)
│   ├── app/                # App Router pages + layout
│   ├── components/
│   │   ├── tabs/           # NewVideoTab, ResumeRunTab, ProjectsTab
│   │   ├── LogStream.tsx   # Live log output panel
│   │   ├── VideoPlayer.tsx # Video preview
│   │   └── ui/             # shadcn/ui components
│   ├── hooks/useSSE.ts     # SSE streaming hook
│   └── lib/api.ts          # Typed API client
├── start_ui.sh             # Launch backend + frontend together
├── gradio_app.py           # Legacy Gradio UI (still functional)
├── coqui_server.py         # Local XTTS TTS server (port 8000)
├── test_apis.py            # API health check script
├── migrate_run_info.py     # Migrate old run_info.txt → run_info.json
└── .env                    # API keys
```

---

## Setup

**Requirements:** Python 3.11+, Node.js 18+, [Manim Community Edition](https://docs.manim.community/en/stable/installation.html)

```bash
# Install main pipeline + FastAPI backend
uv pip install -e .

# Include legacy Gradio UI
uv pip install -e ".[gradio]"

# Install Node.js dependencies
cd web_ui && npm install
```

### API Keys

Create a `.env` file in the project root:

```bash
# Google Gemini (default)
GEMINI_API_KEY=your_key_here

# OpenRouter — when set, ALL model calls are routed through OpenRouter
OPENROUTER_API_KEY=your_key_here

# Optional: override the default OpenRouter models
OPENROUTER_FLASH_MODEL=google/gemini-3-flash-preview
OPENROUTER_PRO_MODEL=google/gemini-3-flash-preview

# ElevenLabs TTS (optional — local Coqui XTTS is used by default)
ELEVENLABS_API_KEY=your_key_here
ELEVENLABS_VOICE_ID=cgSgspJ2msm6clMCkdW9
ELEVENLABS_MODEL_ID=eleven_multilingual_v2
```

#### Check API status

```bash
python test_apis.py
```

### TTS Server

Aji Nafhem uses a local [Coqui XTTS](https://github.com/coqui-ai/TTS) model fine-tuned on Moroccan Darija — [`medmac01/darija_xtt_2.0`](https://huggingface.co/medmac01/darija_xtt_2.0).

```bash
# Install TTS server dependencies (torch + coqui-tts)
uv pip install -e ".[tts-server]"
# or, without the main package:
uv pip install -r requirements-tts-server.txt
```

**Required model files** — place under `model/` in the project root:

```
model/
├── model.pth
├── config.json
├── vocab.json
└── speaker_reference.wav
```

```bash
# Start TTS server (port 8000, Apple MPS by default)
python coqui_server.py
```

> If the TTS server is unreachable, the pipeline substitutes 1-second silent WAV files so Manim can still compile — the video will have no voiceover but all animations will render.

---

## Usage

### Web UI (recommended)

```bash
# Default — uses agentic_video_gen/runs/ for run storage
./start_ui.sh

# Custom runs directory
RUNS_DIR=/path/to/runs ./start_ui.sh
```

Opens:
- **Frontend:** http://localhost:3000
- **Backend API:** http://localhost:8080

**New Video tab** — enter a topic and audience level, pick a model + TTS provider, click Generate. Logs stream live and the video appears on completion.

**Resume Run tab** — pick an existing run and choose which step to restart from. Options:
- *Copy to new run* — fork instead of overwrite
- *Per-step nudges* — inject extra instructions into any step's prompt
- *Force-fix prompt* — describe a specific fix to apply at compile time

**Projects tab** — build multi-scene long-form videos:
- Create a project, add scenes one by one (each building on the previous)
- Toggle *Carry solver context* to pass prior scene knowledge into new scenes
- Import scenes from existing runs or other projects
- Re-run individual scenes from any step, with nudges and force-fix
- Stitch all scenes into a single MP4

### Legacy Gradio UI

```bash
python gradio_app.py
# Opens at http://localhost:7861
```

**New Video tab** — enter a topic and audience level, pick a model provider and TTS provider, click Generate.

**Resume Run tab** — pick an existing run, choose which step to restart from, optionally:
- Check *Copy to new run* to fork instead of overwrite
- Expand *Per-step nudges* to add extra instructions to any step's prompt
- Upload an image alongside the force-fix prompt for multimodal debugging

**Multi-Scene Project tab** — create projects made of multiple scenes:
- Add scenes one by one, each building on the previous
- Toggle *Carry solver context in prompts* to pass prior scene knowledge into new scenes
- Re-run individual scenes from any step
- Stitch all scenes into a single MP4

---

### CLI

```bash
# New run
python -m agentic_video_gen.pipeline run "How does photosynthesis work?" --audience "7th grade student"

# Resume from a specific step
python -m agentic_video_gen.pipeline resume <run-id> --from-step 3
```

### Render a finished scene manually

```bash
MANIM_RUN_DIR=agentic_video_gen/runs/<run-id> \
  manim -qm agentic_video_gen/runs/<run-id>/generated_scene.py GeneratedEducationalScene
```

---

## Models

| Step | Google | OpenRouter (default) |
|------|--------|----------------------|
| Solver | `gemini-3-flash-preview` | `google/gemini-3-flash-preview` |
| Script, SVG, Manim, Fix | `gemini-3-flash-preview` | `google/gemini-3-flash-preview` |

Override OpenRouter models via `OPENROUTER_FLASH_MODEL` / `OPENROUTER_PRO_MODEL`.

---

## TTS Providers

| Option | Backend |
|--------|---------|
| `local` | Coqui XTTS at `localhost:8000` (default) |
| `elevenlabs` | ElevenLabs API — requires `ELEVENLABS_API_KEY`; MP3 auto-converted to WAV |

---

## Migrating Old Runs

```bash
python migrate_run_info.py --dry-run   # preview
python migrate_run_info.py             # apply
```
