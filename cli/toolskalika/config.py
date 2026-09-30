import json
import os
from pathlib import Path

CONFIG_DIR = Path(os.environ.get("TOOLSKALIKA_HOME", Path.home() / ".toolskalika"))
CONFIG_PATH = CONFIG_DIR / "config.json"

DEFAULT_API_URL = "http://localhost:8000"


def load() -> dict:
    if not CONFIG_PATH.exists():
        return {}
    return json.loads(CONFIG_PATH.read_text())


def save(data: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(data, indent=2))
    os.chmod(CONFIG_PATH, 0o600)


def get_api_url() -> str:
    return os.environ.get("TOOLSKALIKA_API_URL") or load().get("api_url", DEFAULT_API_URL)


def get_token() -> str | None:
    return os.environ.get("TOOLSKALIKA_TOKEN") or load().get("token")


def set_api_url(url: str) -> None:
    data = load()
    data["api_url"] = url.rstrip("/")
    save(data)


def set_token(token: str) -> None:
    data = load()
    data["token"] = token
    save(data)


def clear_token() -> None:
    data = load()
    data.pop("token", None)
    save(data)
