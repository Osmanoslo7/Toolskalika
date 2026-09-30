from .. import llm
from .base import register

_SYSTEM = (
    "You are the operator's private engineering collaborator — mechanical, "
    "electrical, or systems. Given a device, mechanism, or problem, produce "
    "a structured technical brainstorm: the core working principle, 2-3 "
    "concrete design approaches with real tradeoffs (materials, tolerances, "
    "power, cost, failure modes), and the first prototype you'd actually "
    "build to test the riskiest assumption. Be specific and technical, not "
    "motivational. No disclaimers."
)


def _fallback(prompt: str) -> str:
    return (
        f"Engineering brainstorm for: {prompt}\n\n"
        "1. Working principle — what physical effect or mechanism does the "
        "core function rely on?\n"
        "2. Design approach A — the straightforward version. What breaks it?\n"
        "3. Design approach B — a different tradeoff (simpler, cheaper, "
        "more precise, or more power-dense). What breaks it?\n"
        "4. Riskiest assumption — the one thing that, if wrong, kills the "
        "whole approach.\n"
        "5. Cheapest prototype — the fastest, roughest build that tests #4.\n\n"
        "(Set ANTHROPIC_API_KEY for the API to fill this in for your "
        "specific mechanism instead of the scaffold.)"
    )


@register(
    "engineering",
    "Technical brainstorm for mechanical/electrical engines, devices, and mechanisms.",
)
def run(prompt: str) -> tuple[str, bool]:
    if llm.is_available():
        return llm.generate(_SYSTEM, prompt), True
    return _fallback(prompt), False
