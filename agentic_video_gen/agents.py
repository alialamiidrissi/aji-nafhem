import os
from typing import List, Optional
from dotenv import load_dotenv
from pydantic_ai import Agent, WebSearchTool
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.providers.google import GoogleProvider
from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.models.openrouter import OpenRouterModel
from pydantic_ai.providers.openrouter import OpenRouterProvider
from agentic_video_gen.schemas import (
    SolvedSteps,
    ScriptSegments,
    VisualAssets,
    MapRequestList,
    ManimCode,
    ManimPatch,
)
from agentic_video_gen.languages import LanguageConfig, get_language, DEFAULT_LANGUAGE
import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)


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

# Model names — Google
_GOOGLE_FLASH = "gemini-3-flash-preview"
_GOOGLE_PRO = "gemini-3-flash-preview"

# Model names — OpenAI
_OPENAI_FLASH = "gpt-5-mini"
_OPENAI_PRO = "gpt-5.2"

_SEARCH_PROVIDERS = ["google", "openai"]
# Model names — OpenRouter (override via env vars OPENROUTER_FLASH_MODEL / OPENROUTER_PRO_MODEL)
_OPENROUTER_FLASH = os.environ.get(
    "OPENROUTER_FLASH_MODEL", "google/gemini-3-flash-preview"
)
_OPENROUTER_PRO = os.environ.get(
    "OPENROUTER_PRO_MODEL", "google/gemini-3-flash-preview"
)

_MODEL_MAP = {
    "google": {"flash": _GOOGLE_FLASH, "pro": _GOOGLE_PRO},
    "openai": {"flash": _OPENAI_FLASH, "pro": _OPENAI_PRO},
    "openrouter": {"flash": _OPENROUTER_FLASH, "pro": _OPENROUTER_PRO},
}


def _active_provider(provider: str) -> str:
    """Return 'openrouter' if OPENROUTER_API_KEY is set, otherwise the requested provider."""
    return provider


def _make_agent(
    model_name: str,
    output_type,
    system_prompt: str,
    provider: str = "google",
    tools: Optional[List] = None,
) -> Agent:
    """
    Create an agent for the given provider.  provider is 'google', 'openai', or 'openrouter'.
    If OPENROUTER_API_KEY is set, all calls are routed through OpenRouter regardless of provider.
    Defers model creation to call time so API keys are already loaded.
    """
    provider = _active_provider(provider)

    if provider == "openrouter":
        return Agent(
            model=OpenRouterModel(model_name, provider=OpenRouterProvider()),
            output_type=output_type,
            system_prompt=system_prompt,
            builtin_tools=tools if tools is not None else (),
        )
    if provider == "openai":
        openai_provider = OpenAIProvider()
        return Agent(
            model=OpenAIResponsesModel(model_name, provider=openai_provider),
            output_type=output_type,
            system_prompt=system_prompt,
            builtin_tools=tools if tools is not None else (),
        )
    # default: google
    google_provider = GoogleProvider(http_client=client)
    return Agent(
        model=GoogleModel(model_name, provider=google_provider),
        output_type=output_type,
        system_prompt=system_prompt,
        builtin_tools=tools if tools is not None else (),
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
    'where relevant, e.g., "The force is $F = ma$, so doubling mass doubles the force required." '
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
def _build_script_prompt(lang_cfg: LanguageConfig) -> str:
    return (
        f"{lang_cfg.script_persona}\n\n"
        "Your input contains three structured fields:\n"
        "  - ‘Audience Level’: the educational level of the target learner.\n"
        "  - ‘Original Query’: the learner’s original question.\n"
        "  - ‘Analytical Solution’: a JSON object containing the topic and an ordered list of solved steps. "
        "Each step includes a concept name and a detailed explanation (which may contain inline LaTeX equations).\n\n"
        f"Your task is to transform this into a fun, engaging, and pedagogically clear voiceover script "
        f"in {lang_cfg.display_name}.\n\n"
        f"{lang_cfg.script_language_rules}\n"
        "- Adapt tone, humor, and vocabulary complexity to the specified Audience Level.\n"
        "- Use relatable examples, light humor, and analogies when helpful for understanding.\n\n"
        "STRUCTURE REQUIREMENTS:\n"
        "- Divide the script into segments.\n"
        "- Each segment must express ONE complete idea only — a single short phrase or sentence, NOT two clauses.\n"
        "- Each segment should correspond to approximately three to six seconds of spoken audio. "
        "Shorter is better: a deliberate, unhurried pace is more educational than a fast one.\n"
        "- Avoid single-word segments.\n"
        "- Avoid long multi-sentence paragraphs in a single segment.\n"
        "- Between major concept shifts, include a brief transitional segment (e.g., a short summary line, "
        "a rhetorical question ...) that gives the viewer cognitive "
        "breathing room before the next idea starts.\n"
        "- For each segment, include a ‘visual_action’ field that precisely describes ONE visual action "
        "the viewer sees at the exact moment that segment is spoken. Keep the visual_action simple and atomic "
        "— one thing appearing, one formula revealed, one highlight — not a sequence of actions.\n"
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
    "Your input contains five fields:\n"
    "  - 'Audience Level': educational level of the target learner.\n"
    "  - 'Original Query': the user's original question.\n"
    "  - 'Analytical Solution': the solved steps JSON.\n"
    "  - 'Voiceover Script': a JSON list of segments, each with an id, "
    "a script line in the target language, and a visual_action description.\n"
    "  - 'Already Generated Map Assets': a (possibly empty) list of PNG map filenames "
    "already available in the assets folder. Do NOT generate an SVG for any visual element "
    "that is already covered by one of these maps.\n\n"
    "From the visual_action descriptions, identify all unique visual elements needed. "
    "Generate one SVG per element — excluding anything covered by a pre-generated map.\n\n"
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
def _build_manim_prompt(lang_cfg: LanguageConfig) -> str:
    return (
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
        "4. Loading assets — choose the right loader based on asset_type in the metadata:\n"
        "   - SVG assets  → `self.get_svg('filename.svg')` returns an SVGMobject.\n"
        "   - Image assets (PNG maps) → `self.get_image('filename.png')` returns an ImageMobject.\n"
        "   Never use get_svg() on a .png file or get_image() on a .svg file.\n"
        "4a. Placing map images — MANDATORY sizing rules:\n"
        "   - Each map asset metadata includes 'pixel_dimensions', e.g., '2100x1350'.\n"
        "   - The Manim frame is 1920×1080 pixels = 14.22×8 Manim units.\n"
        "   - To fill the full frame: `map_img.scale_to_fit_width(config.frame_width)`\n"
        "   - To fill a half-screen panel: `map_img.scale_to_fit_width(config.frame_width * 0.5)`\n"
        "   - Always call scale_to_fit_width (or scale_to_fit_height) immediately after get_image() "
        "before adding to the scene — never rely on the default ImageMobject size.\n"
        "   - After scaling, position with `.to_edge()` or `.move_to(ORIGIN)` as appropriate.\n"
        "5. Sync animations to audio using the context manager:\n"
        "   `with self.speech('segment_id'):`\n"
        "   Animations inside this block must visually match what is being spoken in that segment.\n"
        f"{lang_cfg.manim_text_rule}\n"
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
        "11. Pacing — CRITICAL for viewer comprehension:\n"
        "   - Use `run_time=1.5` or `run_time=2.0` for all major animations (Write, FadeIn, DrawBorderThenFill, "
        "ReplacementTransform, Transform). The default `run_time=1` is too fast for educational content.\n"
        "   - Insert `self.wait(0.5)` between sequential `self.play()` calls within the same speech block so "
        "each visual change registers before the next appears.\n"
        "   - The context manager yields the audio duration as a variable: "
        "`with self.speech('id') as duration:`. Use this only as a reference — do NOT manually call "
        "`self.wait(duration)`; the base class handles the remainder automatically.\n"
        "   - Plan each speech block so that animations occupy roughly the first 60-70% of the audio duration, "
        "leaving the final portion as static display time for the viewer to absorb the result. "
        "Do NOT cram more than 2-3 `self.play()` calls into a single speech block.\n"
        "12. Output must be completely valid, executable Python. Do NOT add markdown code fences."
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


_MAP_REQUEST_PROMPT = (
    "You are a geographic asset planner for an educational video pipeline.\n\n"
    "You will receive:\n"
    "  - 'Original Query': the topic being explained.\n"
    "  - 'Voiceover Script': a JSON ScriptSegments object whose visual_action fields describe "
    "what the viewer sees in each segment.\n\n"
    "Your task: decide whether any segment requires a real geographic map, and if so, "
    "output a MapRequestList describing exactly what maps to generate.\n\n"
    "Return an EMPTY list ('requests': []) if:\n"
    "  - The content is purely mathematical, conceptual, or scientific (no geography needed).\n"
    "  - The visual_actions only reference diagrams, equations, or abstract illustrations.\n\n"
    "Return one MapRequest per distinct map needed if:\n"
    "  - The content involves real-world geography: countries, regions, seas, straits, borders, "
    "conflict zones, trade routes, or geopolitical relationships.\n\n"
    "For each MapRequest:\n"
    "  - 'name': a descriptive PNG filename, e.g., 'middle_east_map.png'.\n"
    "  - 'bbox': tight bounding box [west, south, east, north] in decimal degrees that frames "
    "all relevant countries with ~5° padding. Example for Middle East: [22, 10, 68, 43]. "
    "CRITICAL: every marker lon/lat MUST fall inside this bbox — never add a marker for a "
    "location (e.g. Washington DC) that is geographically outside the region being mapped.\n"
    "  - 'highlight_countries': REQUIRED — always fill this with at least the main countries "
    "relevant to the scene. Use exact Natural Earth English country names "
    "(e.g., 'Iran', 'Saudi Arabia', 'United Arab Emirates', 'United States of America'). "
    "Assign distinct, visually contrasting hex colors. An empty dict produces a plain grey map.\n"
    "  - 'water_labels': label key seas, gulfs, and straits that appear in the bbox. "
    "Do NOT add a water label for a feature that already has a marker.\n"
    "  - 'markers': specific strategic points (cities, chokepoints, bases) that lie WITHIN the bbox. "
    "Each marker needs lon/lat (decimal degrees), a short label, and a dot_color.\n"
    "  - 'title': a concise English title for the map, or empty string.\n\n"
    "Longitude/latitude reference (decimal degrees):\n"
    "  Tehran: 51.4°E, 35.7°N | Tel Aviv: 34.8°E, 32.1°N | Baghdad: 44.4°E, 33.3°N\n"
    "  Riyadh: 46.7°E, 24.7°N | Strait of Hormuz: 56.5°E, 26.5°N\n"
    "  Strait of Gibraltar: -5.3°E, 35.9°N | Suez Canal: 32.5°E, 30.0°N\n"
    "  Moscow: 37.6°E, 55.7°N | Beijing: 116.4°E, 39.9°N | Washington DC: -77.0°E, 38.9°N\n"
)


def _model(provider: str, tier: str) -> str:
    """Resolve model name using the active provider (openrouter overrides if key is set)."""
    return _MODEL_MAP[_active_provider(provider)][tier]


def get_manim_fix_agent(provider: str = "google") -> Agent:
    return _make_agent(
        _model(provider, "flash"), ManimPatch, _MANIM_FIX_PROMPT, provider
    )


def get_map_request_agent(provider: str = "google") -> Agent:
    return _make_agent(
        _model(provider, "flash"), MapRequestList, _MAP_REQUEST_PROMPT, provider
    )


def get_solver_agent(provider: str = "google") -> Agent:
    return _make_agent(
        _model(provider, "pro"),
        SolvedSteps,
        _SOLVER_PROMPT,
        provider,
        tools=[WebSearchTool()] if provider in _SEARCH_PROVIDERS else (),
    )


def get_script_agent(
    provider: str = "google", lang_cfg: LanguageConfig | None = None
) -> Agent:
    cfg = lang_cfg or get_language(DEFAULT_LANGUAGE)
    return _make_agent(
        _model(provider, "flash"), ScriptSegments, _build_script_prompt(cfg), provider
    )


def _build_review_prompt(lang_cfg: LanguageConfig) -> str:
    return (
        f"You are a script coherence reviewer for {lang_cfg.display_name} educational videos.\n\n"
        "You will receive:\n"
        "  - 'Original Query': the learner's question.\n"
        "  - 'Analytical Solution': the solved steps JSON.\n"
        "  - 'Draft Script': a JSON ScriptSegments object with segments, each containing:\n"
        "      id, script (voiceover text), visual_action (what the viewer sees).\n\n"
        "Your task: return a corrected ScriptSegments where every segment's spoken 'script' "
        "is fully coherent with its 'visual_action'.\n\n"
        "For each segment, ask: 'Does the spoken text accurately narrate what the visual_action describes?'\n"
        "A segment is INCOHERENT if:\n"
        "  - The spoken text describes something different from what is shown.\n"
        "  - The spoken text references a formula, variable, or concept that does NOT appear in the visual_action.\n"
        "  - The visual_action shows a specific formula/result but the spoken text narrates a different formula.\n\n"
        "Correction rules:\n"
        f"  - Rewrite the 'script' field so it narrates exactly what the visual_action shows "
        f"(keep the text in {lang_cfg.display_name}).\n"
        "  - You may also fix the 'visual_action' if it is clearly wrong and the script is correct — "
        "but prefer fixing the script. The visual_action field does not have to be in the target language; "
        "keep it in its original language as it is not spoken by TTS.\n"
        "  - Do NOT change segment ids or reorder segments.\n"
        "  - Do NOT merge or split segments.\n"
        f"{lang_cfg.review_language_rules}\n"
        "  - If a segment is already coherent, copy it unchanged.\n\n"
        "PACING CHECK — apply to every segment:\n"
        f"  - A segment is TOO LONG if its 'script' text would take more than ~7 seconds to say at a natural pace "
        f"(roughly more than {lang_cfg.review_pacing_words}). Split such segments into two shorter ones.\n"
        "  - A segment is TOO DENSE if its 'visual_action' describes more than one distinct visual event "
        "(e.g., 'show X, then highlight Y, then replace with Z'). Split into atomic segments — one visual action each.\n"
        "  - When splitting, assign sequential ids (e.g., if splitting segment id=5, produce ids 5a and 5b).\n"
        "  - Between major concept transitions, insert a brief transitional segment if none exists.\n\n"
        "Return the full corrected ScriptSegments (all segments, even unchanged ones)."
    )


def get_script_review_agent(
    provider: str = "google", lang_cfg: LanguageConfig | None = None
) -> Agent:
    cfg = lang_cfg or get_language(DEFAULT_LANGUAGE)
    return _make_agent(
        _model(provider, "flash"), ScriptSegments, _build_review_prompt(cfg), provider
    )


def get_svg_agent(provider: str = "google") -> Agent:
    return _make_agent(_model(provider, "flash"), VisualAssets, _SVG_PROMPT, provider)


def get_manim_agent(
    provider: str = "google", lang_cfg: LanguageConfig | None = None
) -> Agent:
    cfg = lang_cfg or get_language(DEFAULT_LANGUAGE)
    return _make_agent(
        _model(provider, "flash"), ManimCode, _build_manim_prompt(cfg), provider
    )
