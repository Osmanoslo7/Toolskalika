# Toolskalika

Your own personal API. One operator, gated by a passkey (Face ID / Touch ID /
Windows Hello), reachable from a CLI or anything else that can call HTTP.
It ships with tools for brainstorming, writing, memes, engineering
concepts, and music/video briefs — and it's built to grow: add a Python
file under `api/app/tools/`, decorate a function, and it's a new tool.

## How the single-operator / Face ID part actually works

Face ID and Touch ID never talk to a server — they unlock a passkey stored
in your device's secure hardware, and *that* passkey talks to the server
using the [WebAuthn](https://webauthn.guide/) standard. That's exactly what
this API uses:

- **Registration** is a one-time ceremony. The server refuses it a second
  time — once one passkey exists, nobody else can ever register. That's
  the "only one operator" guarantee, enforced in the database, not just
  in the UI.
- **Login** re-runs the WebAuthn ceremony (Face ID prompt, etc.) and, on
  success, the API issues a personal access token (PAT) for the CLI to
  use — so you don't have to Face-ID-auth on every single command.
- **At rest**, any secret the API stores for you (e.g. a third-party API
  key) is encrypted with Fernet before hitting the database.

Because the ceremony requires a real browser talking to a real platform
authenticator, it can't be exercised from a headless environment — you'll
run the login page (`api/static/login.html`) in an actual browser on a
device with Face ID / Touch ID / Windows Hello.

## Layout

```
api/    FastAPI backend — auth, tool registry, SQLite storage
cli/    `toolskalika` command-line client
```

## Running the API

```bash
cd api
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in OWNER_NAME, OWNER_EMAIL, RP_ID, ORIGIN
uvicorn app.main:app --reload
```

`RP_ID` must be the bare domain the browser is actually pointed at
(`localhost` for local use, or your real domain once you host this
somewhere with HTTPS — WebAuthn requires either `localhost` or TLS).

Open `http://localhost:8000/static/login.html`, hit **Register this
device as the operator**, complete the Face ID / Touch ID / Windows Hello
prompt, and copy the token it shows you.

Optional: set `ANTHROPIC_API_KEY` in `.env` to power the content tools
with real Claude output. Without it, every tool still works — it falls
back to a local, template-based scaffold instead of failing.

## Installing the CLI

```bash
cd cli
pip install -e .
toolskalika auth url http://localhost:8000
toolskalika auth token <paste the token from the browser>
toolskalika tools
toolskalika run brainstorm "ideas for a personal API"
toolskalika run engineering "a compact electric turbine"
toolskalika history
toolskalika auth logout   # revokes every issued token, everywhere
```

## Adding a new tool

Drop a file in `api/app/tools/`:

```python
from .. import llm
from .base import register

@register("your-tool", "What it does, one line.")
def run(prompt: str) -> tuple[str, bool]:
    if llm.is_available():
        return llm.generate("system prompt for this tool", prompt), True
    return "local fallback text", False
```

Import it from `api/app/tools/__init__.py` and it shows up in
`toolskalika tools` and `POST /tools/your-tool/run` immediately.

## What this is not (yet)

The music/video tools produce concept briefs (genre, structure, shot
lists), not rendered audio or video — wire in a generation API from your
own account if you want actual media output. Treat that as the next
thing to bolt on, not a limitation of the architecture.
