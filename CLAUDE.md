# Agentic Video Gen - Gemini Rules & Learnings

This file tracks rules, preferences, and corrections provided by the user to ensure the AI agent follows them in future interactions.

## 1. Models
- **Manim Generator**: Must use `gemini-3-flash` (do not default to Pro for the code generation unless explicitly requested, as Flash is preferred here).
- **Available Models**: Always verify the exact string names in the Google GenAI SDK (e.g., `gemini-3.1-pro-preview`, `gemini-3-flash`) rather than assuming `1.5` versions.

## 2. Environment & Package Management
- **Environment**: Always execute commands within the user's requested Conda environment (e.g., `audio_tts`).
- **Package Manager**: Use `uv` (or `uv pip`) for installing python packages instead of standard `pip` for speed and consistency.
- **Frontend Package Manager**: Use `pnpm` for Node.js/Next.js packages (not `npm` or `yarn`).
- **Running Python in the conda env**: The shell in this environment cannot run `conda activate`. Use the env's Python binary directly: `/Users/aalamiid/miniconda3/envs/audio_tts/bin/python <script>`. Do NOT use `conda activate` or `source` conda init scripts.

## 3. Architecture Context
- **Graphs over ReAct**: Prefer Directed acyclic sequential graphs (simple python functions passing Pydantic models) instead of ReAct conversational loops for linear generation tasks like video creation.
- **SVG Generation**: Strictly use standard vector tags (`path`, `rect`, `circle`, `polygon`). Avoid custom fonts, text embeddings, or drop shadows as Manim struggles to parse them. SVGs must contain a `semantic_content` description.
- **Audio Sync**: Voiceover scripts must be broken down into extremely small segments (a few words) so that the visual actions align tightly with the spoken audio in the generated Manim code.
