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
    name: str = Field(description="The unique filename for the svg, e.g., 'battery.svg'.")
    semantic_content: str = Field(description="A description of what the SVG visually represents.")
    usage_description: str = Field(description="Instructions on how this SVG should be used in the scene.")


class ManimCode(BaseModel):
    python_code: str = Field(
        description=(
            "Complete valid Python code for the Manim scene. "
            "Must subclass BaseEducationalScene and be named exactly GeneratedEducationalScene."
        )
    )
