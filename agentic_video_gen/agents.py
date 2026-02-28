import os
from dotenv import load_dotenv
from pydantic_ai import Agent
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.providers.google import GoogleProvider
from agentic_video_gen.schemas import (
    SolvedSteps,
    ScriptSegments,
    VisualAssets,
    ManimCode,
    ManimPatch,
)
import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential


class _RetryTransport(httpx.AsyncBaseTransport):
    """Retries on 429/5xx using tenacity with exponential backoff."""

    def __init__(self) -> None:
        self._inner = httpx.AsyncHTTPTransport()

    @retry(
        retry=retry_if_exception_type(httpx.HTTPStatusError),
        wait=wait_exponential(multiplier=2, min=2, max=60),
        stop=stop_after_attempt(50),
        reraise=True,
    )
    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        response = await self._inner.handle_async_request(request)
        if response.status_code in (429, 500, 502, 503, 504):
            print(f"----HTTP Error: {response.status_code}------")
            raise httpx.HTTPStatusError(
                message=f"HTTP {response.status_code}",
                request=request,
                response=response,
            )
        return response

    async def aclose(self) -> None:
        await self._inner.aclose()


client = httpx.AsyncClient(transport=_RetryTransport(), timeout=120.0)



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
    provider = GoogleProvider(http_client=client)
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
    "Do NOT write any visualization or animation code. "
    "If a [PREVIOUS SCENES CONTEXT] block is present in your input, respect it: do not repeat concepts "
    "already covered in earlier scenes, and build on them naturally to maintain narrative continuity."
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
    "The final output will be rendered using a Text-To-Speech (TTS) system, "
    "so pronunciation clarity and phonetic simplicity are extremely important.\n\n"

    "Your input contains three structured fields:\n"
    "  - 'Audience Level': the educational level of the target learner.\n"
    "  - 'Original Query': the learner’s original question.\n"
    "  - 'Analytical Solution': a JSON object containing the topic and an ordered list of solved steps. "
    "Each step includes a concept name and a detailed explanation (which may contain inline LaTeX equations).\n\n"

    "Your task is to transform this into a fun, engaging, and pedagogically clear voiceover script in Moroccan Darija.\n\n"

    "STRICT RULES:\n"
    "- The script MUST be written entirely in Arabic letters.\n"
    "- Use heavy and consistent tashkeel (diacritics) to maximize pronunciation clarity for TTS.\n"
    "- Do NOT use Latin letters, abbreviations, mathematical symbols, or special characters.\n"
    "- Rewrite equations, numbers, variables, and symbols fully in Arabic words.\n"
    "- Avoid phonetically complex or ambiguous Darija words that may confuse a TTS engine.\n"
    "- Prefer simpler vocabulary and smoother phonetic constructions.\n"
    "- Adapt tone, humor, and vocabulary complexity to the specified Audience Level.\n"
    "- Use relatable examples, light humor, and analogies when helpful for understanding.\n\n"

    "STRUCTURE REQUIREMENTS:\n"
    "- Divide the script into segments.\n"
    "- Each segment must express ONE complete idea only.\n"
    "- Each segment should correspond to approximately five to ten seconds of spoken audio.\n"
    "- Avoid single-word segments.\n"
    "- Avoid long multi-sentence paragraphs.\n"
    "- For each segment, include a 'visual_action' field that precisely describes what the viewer sees "
    "at the exact moment that segment is spoken.\n"
    "- Visuals must tightly synchronize with the spoken content.\n\n"

    "The final result must be optimized for spoken clarity, pacing, and audiovisual synchronization. "
    "If a [PREVIOUS SCENES CONTEXT] block is present in your input, do NOT repeat voiceover segments "
    "that already appeared in earlier scenes — pick up the narrative where the previous scene left off."
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
    "Write the complete Python code for a Manim scene that teaches the given concept.\n\n"
    "Rules:\n"
    "1. The class MUST be named exactly `GeneratedEducationalScene` and subclass `BaseEducationalScene`.\n"
    "2. Import ONLY: `from agentic_video_gen.base_scene import BaseEducationalScene` "
    "   and `from manim import *`.\n"
    "3. Inside `construct`, call `self.setup_assets()` first.\n"
    "4. Load SVGs with `self.get_svg('filename.svg')` — just use the filename, it's already on disk.\n"
    "5. Sync animations to audio using the context manager:\n"
    "   `with self.speech('segment_id'):`\n"
    "   Animations inside this block must visually match what is being spoken in that segment.\n"
    "6. If you display any text on screen (labels, captions, tooltips, banners, etc.), "
    "it MUST be written in Darija Arabic script — never in English or Latin characters. "
    "Use `Text('...', font='Geeza Pro')` for all Arabic strings — never use Tex/MathTex for Arabic.\n"
    "7. Transform animations — use the correct variant to avoid ghost objects:\n"
    "   - `ReplacementTransform(A, B)`: removes A from scene, adds B. Use this for sequential equation steps "
    "where each step REPLACES the previous one. This is the default choice for step-by-step derivations.\n"
    "   - `Transform(A, B)`: A morphs into B in-place; A stays in scene (now looking like B), B is never added. "
    "Use only when you want A to visually become B and keep referencing it as A.\n"
    "   - `TransformMatchingTex(A.copy(), B)` or `TransformFromCopy(A, B)`: A stays unchanged on screen AND B "
    "is added. Only use this when you intentionally want BOTH the original and the new version visible simultaneously.\n"
    "   - NEVER use `TransformMatchingTex(A.copy(), B)` just because you saw it in an example — if you don't "
    "want A to remain on screen, use `TransformMatchingTex(A, B)` (no `.copy()`) or `ReplacementTransform(A, B)`.\n\n"
    "8. Step-by-step derivations — prevent formula pile-up:\n"
    "   When building a mathematical proof or derivation across multiple segments, choose ONE strategy and "
    "apply it consistently:\n"
    "   Strategy A (replace): Show one step at a time. Use `ReplacementTransform(prev_step, next_step)` so "
    "each new line morphs from the previous one. Only one formula visible at a time.\n"
    "   Strategy B (accumulate with pre-planned layout): Decide upfront how many steps will be visible at once, "
    "create them all as a `VGroup(...).arrange(DOWN, buff=0.3)` anchored to `to_edge(UP)`, then reveal them "
    "one by one with `Write`. Never exceed what fits on screen — if more than 4 formulas, use Strategy A.\n"
    "   NEVER build up steps by appending `next_to(prev, DOWN)` across multiple segments without a cleanup plan — "
    "this causes unbounded vertical growth and overlap.\n\n"
    "9. Layout and overlap prevention — MANDATORY:\n"
    "   a) NEVER use raw `.move_to(np.array([x, y, 0]))` or large `.shift()` values. "
    "Always position elements relative to other elements or screen edges using "
    "`.to_edge(UP/DOWN/LEFT/RIGHT, buff=0.5)`, `.to_corner()`, or `.next_to(ref, direction, buff=0.4)`.\n"
    "   b) Axes/graph coexistence: when an `Axes` object is visible, ALL text and formulas must be anchored "
    "to the axes itself — use `next_to(axes, UP, buff=0.5)`. NEVER chain `next_to(..., DOWN)` from a "
    "top-of-screen element when axes occupy the lower portion — the chain drifts into the graph.\n"
    "   c) Always assign decorator objects to named variables — `SurroundingRectangle`, `DashedLine`, `Arrow`, "
    "`Dot`, `Brace`, etc. Never pass them directly into `self.play()` without a variable.\n"
    "   d) At the END of each `with self.speech(...)` block, explicitly `FadeOut` every object introduced in "
    "that block that should not persist. Do not defer cleanup to a later segment.\n"
    "   e) SVG assets that are missing from disk will render as a plain white `Square`. Never use such a "
    "placeholder as a layout anchor — if an SVG might be missing, position content relative to screen edges, "
    "not relative to the SVG object.\n"
    "10. Screen bounds (verified Manim defaults):\n"
    "   - True frame: x ∈ [-7.11, 7.11], y ∈ [-4.0, 4.0]. Safe content zone with 0.5-unit margin: "
    "x ∈ [-6.5, 6.5], y ∈ [-3.5, 3.5].\n"
    "   - When using `.shift()`, keep x-shifts within ±5.0 and y-shifts within ±3.0 from centre.\n"
    "11. Output must be completely valid, executable Python. Do NOT add markdown code fences."
)


_MANIM_FIX_PROMPT = (
    "You are an expert Python/Manim debugger. "
    "You will be given a Manim Python file that failed to compile, the compilation error, "
    "and the full current source of the file.\n\n"
    "Your task is to return a minimal set of search-and-replace edits that fix the error.\n\n"
    "Rules:\n"
    "1. Each 'old_code' MUST be an exact verbatim snippet copied from the current source — "
    "it will be used with a simple string replacement, so any mismatch will fail.\n"
    "2. Only change what is necessary to fix the error. Do not rewrite unrelated code.\n"
    "3. Prefer small, targeted edits over large block replacements.\n"
    "4. If the same pattern must be fixed in multiple places, create a separate change for each.\n"
    "5. In 'explanation', briefly state the root cause and what was changed."
)


def get_manim_fix_agent() -> Agent:
    return _make_agent(_FLASH, ManimPatch, _MANIM_FIX_PROMPT)


def get_solver_agent() -> Agent:
    return _make_agent(_PRO, SolvedSteps, _SOLVER_PROMPT)

def get_script_agent() -> Agent:
    return _make_agent(_FLASH, ScriptSegments, _SCRIPT_PROMPT)


_SCRIPT_REVIEW_PROMPT = (
    "You are a script coherence reviewer for Moroccan Darija educational videos.\n\n"

    "You will receive:\n"
    "  - 'Original Query': the learner's question.\n"
    "  - 'Analytical Solution': the solved steps JSON.\n"
    "  - 'Draft Script': a JSON ScriptSegments object with segments, each containing:\n"
    "      id, script (Darija voiceover text), visual_action (what the viewer sees).\n\n"

    "Your task: return a corrected ScriptSegments where every segment's spoken 'script' "
    "is fully coherent with its 'visual_action'.\n\n"

    "For each segment, ask: 'Does the spoken text accurately narrate what the visual_action describes?'\n"
    "A segment is INCOHERENT if:\n"
    "  - The spoken text describes something different from what is shown.\n"
    "  - The spoken text references a formula, variable, or concept that does NOT appear in the visual_action.\n"
    "  - The visual_action shows a specific formula/result but the spoken text narrates a different formula.\n\n"

    "Correction rules:\n"
    "  - Rewrite the 'script' field (Darija) so it narrates exactly what the visual_action shows.\n"
    "  - You may also fix the 'visual_action' if it is clearly wrong and the script is correct — "
    "but prefer fixing the script.\n"
    "  - Do NOT change segment ids or reorder segments.\n"
    "  - Do NOT merge or split segments.\n"
    "  - Preserve all original script rules: Arabic letters only, heavy tashkeel, no Latin/symbols, "
    "no mathematical notation — rewrite all formulas in Arabic words.\n"
    "  - If a segment is already coherent, copy it unchanged.\n\n"

    "TTS QUALITY PASS — apply to every segment (even unchanged ones):\n"
    "  - Add full, consistent tashkeel (diacritics) on every word.\n"
    "  - Replace phonetically complex or ambiguous Darija words with simpler equivalents "
    "that a TTS engine will pronounce naturally (e.g. avoid rare consonant clusters, "
    "unusual shadda combinations, or words with no clear vowel pattern).\n"
    "  - The result must still sound like natural spoken Darija and remain pedagogically clear — "
    "do NOT sacrifice meaning for simplicity.\n\n"

    "Return the full corrected ScriptSegments (all segments, even unchanged ones)."
)


def get_script_review_agent() -> Agent:
    return _make_agent(_FLASH, ScriptSegments, _SCRIPT_REVIEW_PROMPT)

def get_svg_agent() -> Agent:
    return _make_agent(_FLASH, VisualAssets, _SVG_PROMPT)

def get_manim_agent() -> Agent:
    return _make_agent(_FLASH, ManimCode, _MANIM_PROMPT)
