"""
Language configurations for the educational video generation pipeline.

Each LanguageConfig carries all language-specific prompt snippets so that
agent prompts remain generic templates.  Add a new entry to LANGUAGES to
support an additional output language.
"""
from dataclasses import dataclass
from typing import Dict


@dataclass(frozen=True)
class LanguageConfig:
    code: str
    display_name: str
    manim_font: str
    rtl: bool
    # One-line persona injected at the top of the script-generation prompt.
    script_persona: str
    # Full "STRICT RULES" block for script generation.
    script_language_rules: str
    # Language-specific section injected into the coherence-review prompt
    # (mixed-script preservation + TTS quality pass).
    review_language_rules: str
    # Pacing threshold description used in the review prompt
    # (e.g. "15-18 Arabic words").
    review_pacing_words: str
    # Full Manim rule-6 sentence (text language + font choice).
    manim_text_rule: str


# ---------------------------------------------------------------------------
# Moroccan Darija (default)
# ---------------------------------------------------------------------------
_DARIJA = LanguageConfig(
    code="darija",
    display_name="Moroccan Darija",
    manim_font="Geeza Pro",
    rtl=True,
    script_persona=(
        "You are a Moroccan Darija educational script writer and video director. "
        "The final output will be rendered using a Text-To-Speech (TTS) system, "
        "so pronunciation clarity and phonetic simplicity are extremely important."
    ),
    script_language_rules=(
        "STRICT RULES:\n"
        "- The script must be written primarily in Arabic script with heavy and consistent tashkeel "
        "(diacritics) to maximize pronunciation clarity for TTS.\n"
        "- EXCEPTION — Latin for non-Arabic sounds: Darija contains sounds absent in standard Arabic "
        "(e.g., /p/, /v/, hard /g/). When a Darija or loanword requires such a sound, write that "
        "word in its Latin/French spelling rather than a phonetically misleading Arabic transliteration. "
        "Example: write 'politique' not 'پوليتيك', 'programme' not 'پروگرام'.\n"
        "- WORD CHOICE — always prefer the established Arabic term when one exists: "
        "use the Arabic word even for scientific or technical concepts "
        "(e.g., مُقَارِب for asymptote, قُوَّة for force, طَاقَة for energy, سُرْعَة for speed). "
        "Only use the Latin/French spelling when the word is genuinely of Latin or French origin "
        "AND no standard Arabic equivalent exists or is widely recognised "
        "(e.g., 'pixel', 'robot'). "
        "Words that are themselves of Arabic origin must always be written in Arabic script "
        "(e.g., السُّوَيْس for Suez, الْخَوَارِزْمِيَّة for algorithm).\n"
        "- Do NOT use mathematical symbols (=, +, ×, etc.), LaTeX notation, or numeric digits.\n"
        "- Rewrite equations and numbers fully in Arabic words.\n"
        "- Avoid phonetically complex or ambiguous Darija words that may confuse a TTS engine.\n"
        "- Prefer simpler vocabulary and smoother phonetic constructions."
    ),
    review_language_rules=(
        "  - Preserve the mixed-script rules: Arabic script with heavy tashkeel for Darija words; "
        "Latin/French spelling only for words containing non-Arabic sounds (/p/, /v/, hard /g/) "
        "or genuinely Latin/French-origin terms with no standard Arabic equivalent "
        "(e.g., 'programme', 'pixel') — do NOT transliterate these into Arabic script. "
        "Conversely, always use the established Arabic term when one exists "
        "(e.g., مُقَارِب not 'asymptote', قُوَّة not 'force', طَاقَة not 'énergie', "
        "السُّوَيْس not 'Suez', الْخَوَارِزْمِيَّة not 'algorithme'). "
        "No mathematical symbols or LaTeX; rewrite all equations in Arabic words.\n\n"
        "TTS QUALITY PASS ('script' field) — apply to every segment (even unchanged ones):\n"
        "  - Add full, consistent tashkeel (diacritics) on every Arabic word.\n"
        "  - Fix words with missing or wrong letters (e.g., a root letter accidentally omitted, "
        "wrong hamza placement, or a word spelled in fus7a form that differs in Darija).\n"
        "  - DARIJA AUTHENTICITY: replace any word that is not genuinely used in Moroccan Darija "
        "with its correct Darija equivalent. For example, fusha-only words should be replaced with "
        "their Darija counterparts. If a common Darija word is misspelled or approximated, correct it.\n"
        "  - Replace phonetically complex or ambiguous Darija words with simpler equivalents "
        "that a TTS engine will pronounce naturally (e.g. avoid rare consonant clusters, "
        "unusual shadda combinations, or words with no clear vowel pattern).\n"
        "  - The result must still sound like natural spoken Darija and remain pedagogically clear — "
        "do NOT sacrifice meaning for simplicity."
    ),
    review_pacing_words="15-18 Arabic words",
    manim_text_rule=(
        "6. If you display any text on screen (labels, captions, tooltips, banners, etc.), "
        "it MUST be written in Darija Arabic script — never in English or Latin characters. "
        "Use `Text('...', font='Geeza Pro')` for all Arabic strings — never use Tex/MathTex for Arabic. "
        "CRITICAL — RTL rendering: Manim's Text() cannot mix Arabic (RTL) with digits or symbols (LTR) "
        "in a single string — the number silently disappears (known Manim limitation, no workaround). "
        "Fix: always split into TWO separate Text() objects and combine with VGroup().arrange(RIGHT, buff=0.15). "
        r"Example: arabic = Text('مِلْيَارَاتْ', font='Geeza Pro', color=RED); num = Text('9 $', color=RED); "
        "label = VGroup(arabic, num).arrange(RIGHT, buff=0.15). "
        "Never put digits or symbols inside the same Text() string as Arabic."
    ),
)

# ---------------------------------------------------------------------------
# Modern Standard Arabic (Fusha)
# ---------------------------------------------------------------------------
_MSA = LanguageConfig(
    code="msa",
    display_name="Modern Standard Arabic",
    manim_font="Geeza Pro",
    rtl=True,
    script_persona=(
        "You are a Modern Standard Arabic (Fusha) educational script writer and video director. "
        "The final output will be rendered using a Text-To-Speech (TTS) system, "
        "so pronunciation clarity and full tashkeel are extremely important."
    ),
    script_language_rules=(
        "STRICT RULES:\n"
        "- The script must be written in Modern Standard Arabic (فُصْحَى) with full, consistent "
        "tashkeel (diacritics) on every word to maximize TTS pronunciation clarity.\n"
        "- Use formal Fusha vocabulary appropriate for the audience level. "
        "Do NOT use Darija or any dialect words.\n"
        "- Always prefer the established Arabic term when one exists: "
        "use the Arabic word for scientific and technical concepts "
        "(e.g., مُقَارِب for asymptote, قُوَّة for force, طَاقَة for energy, سُرْعَة for speed, "
        "السُّوَيْس for Suez, الْخَوَارِزْمِيَّة for algorithm). "
        "Only keep a term in its Latin/French spelling when it is a genuine loanword "
        "with no standard Arabic equivalent (e.g., 'pixel', 'robot', 'laser').\n"
        "- Do NOT use mathematical symbols (=, +, ×, etc.), LaTeX notation, or numeric digits.\n"
        "- Rewrite equations and numbers fully in Arabic words.\n"
        "- Prefer clear, unambiguous vocabulary that a standard Arabic TTS engine will pronounce correctly."
    ),
    review_language_rules=(
        "  - Preserve Modern Standard Arabic (Fusha): use formal, correct grammar and vocabulary. "
        "Do NOT allow dialect or colloquial words. "
        "Always prefer the established Arabic term when one exists "
        "(e.g., مُقَارِب not 'asymptote', قُوَّة not 'force', السُّوَيْس not 'Suez'). "
        "Only retain a Latin/French-origin term when no standard Arabic equivalent exists "
        "(e.g., 'pixel', 'robot', 'laser').\n\n"
        "TTS QUALITY PASS ('script' field) — apply to every segment (even unchanged ones):\n"
        "  - Add full, consistent tashkeel (diacritics) on every Arabic word.\n"
        "  - Fix words with missing or wrong letters, incorrect hamza placement, or "
        "grammatically wrong case endings (i'rab).\n"
        "  - Ensure every word is correct Fusha — replace any colloquial or dialect form with its "
        "proper Modern Standard Arabic equivalent.\n"
        "  - Replace phonetically complex or ambiguous words with clearer equivalents "
        "that a standard Arabic TTS engine will pronounce naturally."
    ),
    review_pacing_words="15-18 Arabic words",
    manim_text_rule=(
        "6. If you display any text on screen (labels, captions, tooltips, banners, etc.), "
        "it MUST be written in Modern Standard Arabic script. "
        "Use `Text('...', font='Geeza Pro')` for all Arabic strings — never use Tex/MathTex for Arabic. "
        "CRITICAL — RTL rendering: Manim's Text() cannot mix Arabic (RTL) with digits or symbols (LTR) "
        "in a single string — the number silently disappears (known Manim limitation, no workaround). "
        "Fix: always split into TWO separate Text() objects and combine with VGroup().arrange(RIGHT, buff=0.15). "
        r"Example: arabic = Text('مِلْيَارَاتْ', font='Geeza Pro', color=RED); num = Text('9 $', color=RED); "
        "label = VGroup(arabic, num).arrange(RIGHT, buff=0.15). "
        "Never put digits or symbols inside the same Text() string as Arabic."
    ),
)

# ---------------------------------------------------------------------------
# French
# ---------------------------------------------------------------------------
_FRENCH = LanguageConfig(
    code="french",
    display_name="French",
    manim_font="DejaVu Sans",
    rtl=False,
    script_persona=(
        "You are a French educational script writer and video director. "
        "The final output will be rendered using a Text-To-Speech (TTS) system, "
        "so pronunciation clarity and natural sentence rhythm are very important."
    ),
    script_language_rules=(
        "STRICT RULES:\n"
        "- The script must be written in clear, natural French adapted to the specified audience level.\n"
        "- Use standard French orthography with correct accents and punctuation.\n"
        "- Mathematical formulas must be spoken as natural language: write 'F égale m fois a' "
        "instead of 'F=ma'. Do NOT include raw mathematical symbols, LaTeX, or unexplained variable names.\n"
        "- Avoid overly technical jargon unless appropriate for the audience level — "
        "always explain or paraphrase new terms when first introduced.\n"
        "- Prefer short, rhythmically smooth sentences that a TTS engine will deliver clearly.\n"
        "- Numbers should be written as words (e.g., 'deux' not '2') unless they are years or "
        "large figures that would sound awkward when spoken."
    ),
    review_language_rules=(
        "  - The script must remain in clear, natural French. Correct any grammatical errors, "
        "awkward phrasing, or overly formal structures that would sound unnatural when spoken aloud. "
        "Mathematical expressions must be in full spoken French words, not symbols.\n\n"
        "TTS QUALITY PASS ('script' field) — apply to every segment (even unchanged ones):\n"
        "  - Check that all accents and diacritics are present and correct (é, è, ê, ç, à, ù, etc.).\n"
        "  - Ensure sentence rhythm is natural for French TTS: avoid tongue-twister consonant clusters "
        "or ambiguous liaisons.\n"
        "  - Replace any mathematical symbols or LaTeX with their spoken French equivalents."
    ),
    review_pacing_words="25-30 French words",
    manim_text_rule=(
        "6. If you display any text on screen (labels, captions, tooltips, banners, etc.), "
        "it MUST be written in French. "
        "Use `Text('...', font='DejaVu Sans')` for all text strings."
    ),
)

# ---------------------------------------------------------------------------
# English
# ---------------------------------------------------------------------------
_ENGLISH = LanguageConfig(
    code="english",
    display_name="English",
    manim_font="Arial",
    rtl=False,
    script_persona=(
        "You are an English educational script writer and video director. "
        "The final output will be rendered using a Text-To-Speech (TTS) system, "
        "so clarity, pacing, and natural spoken rhythm are very important."
    ),
    script_language_rules=(
        "STRICT RULES:\n"
        "- The script must be written in clear, natural English adapted to the specified audience level.\n"
        "- Use standard English orthography.\n"
        "- Mathematical formulas must be spoken as natural language: write 'F equals m times a' "
        "instead of 'F=ma'. Do NOT include raw mathematical symbols, LaTeX, or unexplained variable names.\n"
        "- Avoid jargon unless appropriate for the audience level — "
        "always explain new terms when first introduced.\n"
        "- Prefer short, active-voice sentences with clear subject-verb-object structure for TTS clarity.\n"
        "- Numbers should be written as words (e.g., 'two' not '2') unless they are years, "
        "large figures, or specific measurements that sound more natural as numerals."
    ),
    review_language_rules=(
        "  - The script must remain in clear, natural English. Correct any grammatical errors, "
        "passive constructions that obscure meaning, or overly complex sentences that would sound "
        "unnatural when spoken aloud. Mathematical expressions must be in full spoken English words, not symbols.\n\n"
        "TTS QUALITY PASS ('script' field) — apply to every segment (even unchanged ones):\n"
        "  - Ensure there are no spelling errors, missing words, or awkward phrasing.\n"
        "  - Replace any mathematical symbols or LaTeX with their spoken English equivalents.\n"
        "  - Flag and simplify any word or phrase that a standard TTS engine might mispronounce "
        "(unusual abbreviations, uncommon proper nouns, ambiguous phonetic sequences)."
    ),
    review_pacing_words="25-35 English words",
    manim_text_rule=(
        "6. If you display any text on screen (labels, captions, tooltips, banners, etc.), "
        "it MUST be written in English. "
        "Use `Text('...', font='Arial')` for all text strings."
    ),
)

# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------
LANGUAGES: Dict[str, LanguageConfig] = {
    "darija": _DARIJA,
    "msa": _MSA,
    "french": _FRENCH,
    "english": _ENGLISH,
}

DEFAULT_LANGUAGE = "darija"


def get_language(code: str) -> LanguageConfig:
    """Return the LanguageConfig for *code*, falling back to Darija if unknown."""
    return LANGUAGES.get(code, _DARIJA)
