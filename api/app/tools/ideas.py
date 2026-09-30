"""Concept generation for music and video. This does not render audio or
video — it's the idea/brief stage. Wire a generation API (e.g. a music or
video model) into these handlers later if you want actual media output;
for now they hand you a concrete brief you could take to one.
"""

from .. import llm
from .base import register

_MUSIC_SYSTEM = (
    "You are the operator's private music collaborator. Given a topic, "
    "mood, or rough idea, produce a concrete musical brief: genre/BPM/key "
    "suggestion, instrumentation, a structural sketch (intro/verse/hook/"
    "etc.), and if relevant a few lines of lyric direction or hook text. "
    "Specific and usable, not generic. No disclaimers."
)

_VIDEO_SYSTEM = (
    "You are the operator's private video/film collaborator. Given a topic "
    "or rough idea, produce a concrete shot-level brief: concept in one "
    "line, format (short/long, aspect ratio, style reference), a shot list "
    "or beat sheet, and the single most important visual moment to nail. "
    "Specific and usable, not generic. No disclaimers."
)


def _fallback(kind: str, prompt: str) -> str:
    return (
        f"{kind} brief for: {prompt}\n\n"
        "1. One-line concept.\n"
        "2. Reference points — 2-3 existing works this sits near.\n"
        "3. Structure — the beats/sections in order.\n"
        "4. The one moment that has to land.\n\n"
        "(Set ANTHROPIC_API_KEY for the API to actually draft this instead "
        "of a scaffold.)"
    )


@register("music", "Music concept briefs — genre, structure, lyric direction.")
def run_music(prompt: str) -> tuple[str, bool]:
    if llm.is_available():
        return llm.generate(_MUSIC_SYSTEM, prompt), True
    return _fallback("Music", prompt), False


@register("video", "Video/film concept briefs — shot list, beats, key moment.")
def run_video(prompt: str) -> tuple[str, bool]:
    if llm.is_available():
        return llm.generate(_VIDEO_SYSTEM, prompt), True
    return _fallback("Video", prompt), False
