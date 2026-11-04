"""Load JSON manifests and check them against the JSON Schemas in schemas/."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator

from .paths import SCHEMA_DIR


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=None)
def _validator(name: str) -> Draft202012Validator:
    schema = load_json(SCHEMA_DIR / f"{name}.schema.json")
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def schema_errors(name: str, data) -> list[str]:
    """Return human-readable schema errors for `data` against schemas/<name>.schema.json."""
    errors = sorted(_validator(name).iter_errors(data), key=lambda e: [str(p) for p in e.absolute_path])
    return [f"{'.'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}" for e in errors]
