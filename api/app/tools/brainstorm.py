from .. import llm
from .base import register

_SYSTEM = (
    "You are the operator's private brainstorming partner. Given a topic or "
    "problem, produce 6-10 sharp, concrete ideas or angles — no filler, no "
    "generic advice, no disclaimers. Favor specific, actionable, or "
    "surprising directions over safe ones. Use a numbered list."
)

_ANGLES = [
    "Combine it with something unrelated",
    "Do the opposite of the obvious approach",
    "Make it 10x bigger or 10x smaller in scope",
    "Remove the most expensive part and see what's left",
    "What would this look like built in a weekend?",
    "What's the version of this that only works for one person (you)?",
    "What existing tool almost does this, and what's missing?",
    "What would make this embarrassing to ship, and is that a feature?",
]


def _fallback(prompt: str) -> str:
    lines = [f"Brainstorm angles for: {prompt}\n"]
    for i, angle in enumerate(_ANGLES, start=1):
        lines.append(f"{i}. {angle} — apply this lens to \"{prompt}\".")
    lines.append(
        "\n(Set ANTHROPIC_API_KEY for the API to actually think about your "
        "specific prompt instead of listing lenses.)"
    )
    return "\n".join(lines)


@register("brainstorm", "General-purpose brainstorming on any topic or problem.")
def run(prompt: str) -> tuple[str, bool]:
    if llm.is_available():
        return llm.generate(_SYSTEM, prompt), True
    return _fallback(prompt), False
