"""Thin Claude wrapper used by tools. If no ANTHROPIC_API_KEY is configured,
callers fall back to local template generation instead of failing — the
API stays usable offline, just less creative.
"""

from .config import get_settings


def is_available() -> bool:
    return bool(get_settings().anthropic_api_key)


def generate(system: str, prompt: str, max_tokens: int = 1024) -> str:
    """Raises if no key is configured — callers should check is_available()
    first and use their own fallback when it's False."""
    settings = get_settings()
    if not settings.anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not configured")

    import anthropic

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    response = client.messages.create(
        model=settings.anthropic_model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(block.text for block in response.content if block.type == "text").strip()
