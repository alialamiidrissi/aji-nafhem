from pydantic import BaseModel, Field
from typing import List, Optional


class ProblemStep(BaseModel):
    step_number: int
    concept: str = Field(description="The core educational concept being taught here.")
    description: str = Field(
        description=(
            "A clear educational explanation of this step, adapted to the target audience level. "
            "Mix prose with LaTeX-style equations inline where relevant, "
            "e.g., \"The force applied is given by $F = ma$, so doubling the mass doubles the force needed.\""
        )
    )


class SolvedSteps(BaseModel):
    topic: str = Field(description="The main topic of the query.")
    steps: List[ProblemStep] = Field(description="The logical steps to solve or explain the query.")


class ScriptSegment(BaseModel):
    id: str = Field(description="A unique identifier for this segment, e.g., '1_intro'. Should be a valid filename.")
    script: str = Field(
        description=(
            "The Moroccan Darija script for the voiceover. Write only in Arabic letters with tachkeel (diacritics). "
            "Keep it natural, fun, and engaging. "
            "Avoid Darija words that are phonetically complex or hard for a TTS model to pronounce — "
            "prefer simpler phonetic alternatives and add tachkeel throughout to guide correct pronunciation. "
            "Each segment covers one complete thought — aim for ~5-10 seconds of speech."
        )
    )
    visual_action: str = Field(
        description=(
            "A clear description of what happens visually on screen during this segment. "
            "Must be tightly coupled to the spoken text so animations feel synchronized."
        )
    )


class ScriptSegments(BaseModel):
    segments: List[ScriptSegment] = Field(
        description=(
            "List of script segments, each covering one coherent idea or thought. "
            "Segments should flow naturally like a fun educational video — not too choppy, not too long. "
            "Each segment should feel like a complete mini-thought (~5-10 seconds of speech)."
        )
    )


class SVGAsset(BaseModel):
    name: str = Field(description="The unique filename for the svg, e.g., 'battery.svg'.")
    semantic_content: str = Field(
        description=(
            "A description of what the SVG actually contains visually. Be specific and vivid, "
            "e.g., 'a shiny yellow cylindrical battery with + and - terminals', "
            "'a glowing orange candle flame with a white wax body'."
        )
    )
    raw_svg_code: str = Field(description="The raw XML/SVG code for this asset.")
    usage_description: str = Field(
        description="Instructions on how this SVG should be positioned or animated in the scene."
    )


class VisualAssets(BaseModel):
    assets: List[SVGAsset] = Field(description="The list of all SVG assets generated for the scene.")


class AssetMetadata(BaseModel):
    name: str = Field(description="The unique filename for the asset, e.g., 'battery.svg' or 'middle_east_map.png'.")
    asset_type: str = Field(default="svg", description="'svg' or 'image'. SVG assets are loaded with self.get_svg(name); image assets (PNG maps) are loaded with self.get_image(name).")
    semantic_content: str = Field(description="A description of what the asset visually represents.")
    usage_description: str = Field(description="Instructions on how this asset should be positioned or animated in the scene.")
    viewbox: Optional[str] = Field(default=None, description="SVG only. The viewBox attribute of the SVG root element, e.g., '0 0 200 200'. Use this to understand the asset's coordinate space and aspect ratio for correct scaling and placement in Manim.")
    pixel_dimensions: Optional[str] = Field(default=None, description="Image only. Pixel dimensions of the PNG, e.g., '2100x1350'. Use this to compute the correct scale when placing the image in a Manim scene whose frame is 1920×1080 (14.22×8 Manim units).")
    map_metadata: Optional[dict] = Field(default=None, description=(
        "Map assets only. Keys: 'highlight_countries' (name→hex color), "
        "'markers' (list of {label, dot_color}), 'water_labels' (label→[lon,lat]), "
        "'bbox' ([W,S,E,N]), 'title'. Use highlight_countries colors when adding "
        "matching Manim labels over the map image."
    ))


class MapMarker(BaseModel):
    lon: float = Field(description="Longitude of the marker point.")
    lat: float = Field(description="Latitude of the marker point.")
    label: str = Field(description="Short text label shown next to the dot, e.g., 'Tehran'.")
    dot_color: str = Field(default="#FFD700", description="Hex color for the marker dot, e.g., '#C0392B'.")


class MapRequest(BaseModel):
    name: str = Field(description="Output filename for the PNG, e.g., 'middle_east_map.png'.")
    bbox: List[float] = Field(description="Bounding box as [west, south, east, north] in decimal degrees, e.g., [22, 10, 68, 43].")
    highlight_countries: dict = Field(default_factory=dict, description="Mapping of Natural Earth country name (exact English) to hex fill color, e.g., {'Iran': '#C0392B', 'Israel': '#2980B9'}.")
    water_labels: dict = Field(default_factory=dict, description="Mapping of label text to [lon, lat] for seas/straits, e.g., {'Persian Gulf': [50.5, 27.5]}. Do NOT add a water label for a place that already has a marker.")
    markers: List[MapMarker] = Field(default_factory=list, description="Specific point markers for cities, chokepoints, etc.")
    title: str = Field(default="", description="Optional title shown at the top of the map.")


class MapRequestList(BaseModel):
    requests: List[MapRequest] = Field(
        default_factory=list,
        description=(
            "List of map generation requests. Return an empty list if the scene does not require "
            "any geographic map (i.e., the content is purely conceptual or mathematical)."
        ),
    )


class ManimCode(BaseModel):
    python_code: str = Field(
        description=(
            "Complete valid Python code for the Manim scene. "
            "Must subclass BaseEducationalScene and be named exactly GeneratedEducationalScene."
        )
    )


class CodeChange(BaseModel):
    old_code: str = Field(
        description="The exact verbatim code snippet to find and replace. Must match character-for-character."
    )
    new_code: str = Field(
        description="The replacement code snippet."
    )


class ManimPatch(BaseModel):
    changes: List[CodeChange] = Field(
        description=(
            "Ordered list of search-and-replace edits to apply to the existing Python file. "
            "Each change must contain an exact verbatim snippet from the current file."
        )
    )
    explanation: str = Field(description="Brief explanation of what was fixed and why.")


class SceneContext(BaseModel):
    scene_index: int
    query: str
    script: "ScriptSegments"
    solver_result: Optional["SolvedSteps"] = None  # only if carry_solver_context=True
