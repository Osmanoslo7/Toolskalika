from collections.abc import Callable
from dataclasses import dataclass

Handler = Callable[[str], tuple[str, bool]]  # prompt -> (output, used_llm)


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    handler: Handler


_REGISTRY: dict[str, Tool] = {}


def register(name: str, description: str) -> Callable[[Handler], Handler]:
    def decorator(fn: Handler) -> Handler:
        if name in _REGISTRY:
            raise ValueError(f"tool {name!r} already registered")
        _REGISTRY[name] = Tool(name=name, description=description, handler=fn)
        return fn

    return decorator


def all_tools() -> list[Tool]:
    return sorted(_REGISTRY.values(), key=lambda t: t.name)


def get_tool(name: str) -> Tool | None:
    return _REGISTRY.get(name)
