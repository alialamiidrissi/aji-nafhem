import os
from dotenv import load_dotenv
from pydantic_ai import Agent
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.providers.google import GoogleProvider
from agentic_video_gen.schemas import (
    SolvedSteps,
    ScriptSegments,
    VisualAssets,
    ManimCode
)

# Load environment variables
load_dotenv(os.path.join(os.getcwd(), ".env"))

# Model names
_PRO = "gemini-3-flash-preview"
_FLASH = "gemini-3-flash-preview"


def _make_agent(model_name: str, output_type, system_prompt: str) -> Agent:
    """
    Defers GoogleModel creation to call time so GEMINI_API_KEY is
    already set in the environment when the provider initializes.
    """
    provider = GoogleProvider()
    return Agent(
        model=GoogleModel(model_name, provider=provider),
        output_type=output_type,
        system_prompt=system_prompt,
    )


# ---------------------------------------------------------
# Node 1: Analytical Solver
# INPUT:
#   - "Audience Level: <string>" — e.g., '7th grade student', 'grad student'
#   - "Query: <string>" — the raw user question or problem to solve
# ---------------------------------------------------------
_SOLVER_PROMPT = (
    "You are an expert science tutor. "
    "Your input contains two fields:\n"
    "  - 'Audience Level': the educational level of the target learner "
    "(e.g., '7th grade student', 'high school student', 'grad student').\n"
    "  - 'Query': the topic or problem to explain.\n\n"
    "Break the problem into clear, logical numbered steps perfectly suited to that audience level. "
    "For each step, write a 'description' that freely mixes prose with inline LaTeX-style equations "
    "where relevant, e.g., \"The force is $F = ma$, so doubling mass doubles the force required.\" "
    "Equations appear naturally alongside their explanation — not in a separate list. "
    "Do NOT write any visualization or animation code."
)

# ---------------------------------------------------------
# Node 2: Script & TTS Generator
# INPUT:
#   - "Audience Level: <string>" — the target learner level
#   - "Original Query: <string>" — the raw user question
#   - "Analytical Solution: <JSON>" — the SolvedSteps object from Node 1,
#     containing: topic, and list of steps (step_number, concept, description with inline equations)
# ---------------------------------------------------------
_SCRIPT_PROMPT = (
    "You are a Moroccan Darija educational script writer and video director. "
    "Your input contains three fields:\n"
    "  - 'Audience Level': the educational level of the target learner.\n"
    "  - 'Original Query': the user's original question.\n"
    "  - 'Analytical Solution': a JSON object that includes the topic and a list of solved steps, "
    "each containing a concept name and a description (which may include inline LaTeX equations).\n\n"
    "Using this information, create a fun, engaging, and accessible voiceover script in Moroccan Darija. "
    "Rules:\n"
    "- Write exclusively in Arabic letters with heavy tachkeel (diacritics) for TTS clarity.\n"
    "- Adjust the tone and vocabulary complexity to match the specified audience level.\n"
    "- Incorporate humor, analogies, and relatable examples where appropriate.\n"
    "- Avoid using Darija words that are phonetically complex or difficult for a TTS model to pronounce. "
    "  Instead, opt for simpler phonetic alternatives and include tachkeel throughout to assist with correct pronunciation.\n"
    "- Each segment should convey ONE complete idea or thought (~5-10 seconds of speech). "
    "  Avoid segments that are too short (single words are ineffective) or too long (multi-sentence blocks are undesirable).\n"
    "- For each segment, provide a clear visual_action that describes exactly what the viewer should see "
    "  while that segment is being spoken. Visuals must closely align with the spoken words."
)

# ---------------------------------------------------------
# Node 3: SVG Asset Generator
# INPUT:
#   - "Audience Level: <string>" — the target learner level
#   - "Original Query: <string>" — the user's original question
#   - "Analytical Solution: <JSON>" — the SolvedSteps object from Node 1
#   - "Voiceover Script: <JSON>" — the ScriptSegments object from Node 2,
#     containing: a list of segments (id, script text, visual_action description)
# ---------------------------------------------------------
_SVG_PROMPT = (
    "You are a professional vector graphic designer building illustration assets for Manim animations. "
    "Your input contains four fields:\n"
    "  - 'Audience Level': educational level of the target learner.\n"
    "  - 'Original Query': the user's original question.\n"
    "  - 'Analytical Solution': the solved steps JSON.\n"
    "  - 'Voiceover Script': a JSON list of segments, each with an id, "
    "a Darija script line, and a visual_action description.\n\n"
    "From the visual_action descriptions, identify all unique visual elements needed. "
    "Generate one SVG per element.\n\n"
    "Aesthetic Rules: Produce beautiful, colorful, modern flat-design vectors with vibrant colors. "
    "Use distinct shapes and thoughtful design — not ugly blobs.\n"
    "Technical Rules (STRICT — Manim SVGMobject cannot handle complex SVGs):\n"
    "- Use ONLY: <path>, <rect>, <circle>, <polygon> tags.\n"
    "- NO <text> tags, NO embedded fonts, NO drop shadows, NO complex filters, NO gradients.\n"
    "For each asset: provide a vivid semantic_content (e.g., 'a glowing orange candle with a white wax body'), "
    "the raw SVG code, and a usage_description explaining how to position and animate it."
)

# ---------------------------------------------------------
# Node 4: Manim Code Generator
# INPUT:
#   - "Audience Level: <string>" — the target learner level
#   - "Original Query: <string>" — the user's original question
#   - "Analytical Solution: <JSON>" — the SolvedSteps object from Node 1
#   - "Voiceover Script: <JSON>" — the ScriptSegments object from Node 2
#   - "Available SVG Assets: <list of dicts>" — each dict has: name (filename),
#     semantic_content (what it looks like), usage_description (how to use it in the scene).
#     NOTE: raw SVG code is NOT provided — assets are already saved to disk.
# ---------------------------------------------------------
_MANIM_PROMPT = (
    "You are an expert Python animator specializing in Manim Community Edition. "
    "Your input contains five fields:\n"
    "  - 'Audience Level': the target learner level.\n"
    "  - 'Original Query': the user's question.\n"
    "  - 'Analytical Solution': the solved steps JSON (concept + description per step).\n"
    "  - 'Voiceover Script': a JSON list of segments, each with: id, script text, and visual_action.\n"
    "  - 'Available SVG Assets': a list of asset dicts with name, semantic_content, and usage_description. "
    "Raw SVG code is NOT included — assets are already saved to disk and can be loaded by name.\n\n"
    "Write the complete Python code for a Manim scene that teaches the given concept.\n"
    "Rules:\n"
    "1. The class MUST be named exactly `GeneratedEducationalScene` and subclass `BaseEducationalScene`.\n"
    "2. Import ONLY: `from agentic_video_gen.base_scene import BaseEducationalScene` "
    "   and `from manim import *`.\n"
    "3. Inside `construct`, call `self.setup_assets()` first.\n"
    "4. Load SVGs with `self.get_svg('filename.svg')` — just use the filename, it's already on disk.\n"
    "5. Sync animations to audio using the context manager:\n"
    "   `with self.speech('segment_id'):`\n"
    "   Animations inside this block must visually match what is being spoken in that segment.\n"
    "6. Output must be completely valid, executable Python. Do NOT add markdown code fences."
)


def get_solver_agent() -> Agent:
    return _make_agent(_PRO, SolvedSteps, _SOLVER_PROMPT)

def get_script_agent() -> Agent:
    return _make_agent(_FLASH, ScriptSegments, _SCRIPT_PROMPT)

def get_svg_agent() -> Agent:
    return _make_agent(_FLASH, VisualAssets, _SVG_PROMPT)

def get_manim_agent() -> Agent:
    return _make_agent(_FLASH, ManimCode, _MANIM_PROMPT)
