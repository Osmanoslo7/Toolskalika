from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .auth.routes import router as auth_router
from .db import init_db
from .tools import base as tools_base
from .tools.routes import router as tools_router

app = FastAPI(
    title="Toolskalika",
    description=(
        "A single-operator personal API. Registration is gated by a "
        "WebAuthn passkey (Face ID / Touch ID / Windows Hello via the "
        "platform authenticator) and only ever accepts one operator."
    ),
)


@app.on_event("startup")
def _startup() -> None:
    init_db()


@app.get("/health")
def health():
    return {"status": "ok", "tools": len(tools_base.all_tools())}


app.include_router(auth_router)
app.include_router(tools_router)

_static_dir = Path(__file__).resolve().parent.parent / "static"
app.mount("/static", StaticFiles(directory=str(_static_dir), html=True), name="static")
