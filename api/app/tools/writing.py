from .. import llm
from .base import register

_SYSTEM = (
    "You are the operator's private writing assistant. Given a prompt "
    "(a topic, a rough draft, or an instruction), produce polished written "
    "content that matches what was asked — an article, a caption, a script, "
    "a paragraph, whatever fits. No disclaimers, no meta-commentary about "
    "being an AI, just the writing."
)


def _fallback(prompt: str) -> str:
    return (
        f"Draft outline for: {prompt}\n\n"
        "1. Hook — the single most interesting claim or image related to this.\n"
        "2. Context — why this matters right now, in one or two sentences.\n"
        "3. Core — the 2-3 points that carry the piece.\n"
        "4. Turn — a twist, counterpoint, or specific example.\n"
        "5. Close — land on the hook again, or a clear next step.\n\n"
        "(Set ANTHROPIC_API_KEY for the API to write the actual prose instead "
        "of an outline.)"
    )


@register("write", "Draft or polish written content — articles, captions, scripts, copy.")
def run(prompt: str) -> tuple[str, bool]:
    if llm.is_available():
        return llm.generate(_SYSTEM, prompt), True
    return _fallback(prompt), False
