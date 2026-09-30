from .. import llm
from .base import register

_SYSTEM = (
    "You are the operator's private meme and joke writer. Given a topic or "
    "situation, produce 5-8 genuinely funny meme concepts: name a well-known "
    "template where relevant, give the exact top/bottom text, and land a "
    "real punchline. No disclaimers, no 'as an AI', no explaining the joke."
)

_TEMPLATES = [
    "Drake hotline bling (reject / prefer)",
    "Distracted boyfriend",
    "Expanding brain (four panels of escalating absurdity)",
    "This is fine (dog in burning room)",
    "Two buttons, sweating",
    "Galaxy brain / ape-to-astronaut",
]


def _fallback(prompt: str) -> str:
    lines = [f"Meme concepts for: {prompt}\n"]
    for template in _TEMPLATES:
        lines.append(f"- {template}: [fill in the punchline about \"{prompt}\"]")
    lines.append(
        "\n(Set ANTHROPIC_API_KEY for the API to actually write the punchlines "
        "instead of naming templates.)"
    )
    return "\n".join(lines)


@register("meme", "Meme concepts and captions for a topic or situation.")
def run(prompt: str) -> tuple[str, bool]:
    if llm.is_available():
        return llm.generate(_SYSTEM, prompt), True
    return _fallback(prompt), False
