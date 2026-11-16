"""Phase 4 — minimal local review dashboard (standard library only).

Binds to 127.0.0.1 by default. Serves only files inside the workspace. Long tasks
(import, analysis, rendering) run one at a time on a background worker thread.
"""
from __future__ import annotations

import json
import mimetypes
import queue
import re
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

from ..config import workspace

INDEX = Path(__file__).with_name("index.html")


class LockedDB:
    """Serialise all database access across request and worker threads."""

    def __init__(self, db):
        self._db, self._lock = db, threading.RLock()

    def __getattr__(self, name):
        attr = getattr(self._db, name)
        if not callable(attr):
            return attr

        def call(*a, **kw):
            with self._lock:
                return attr(*a, **kw)
        return call


class App:
    def __init__(self, cfg: dict, db):
        self.cfg, self.db = cfg, LockedDB(db)
        self.ws = workspace(cfg)
        self.jobs: list[dict] = []
        self.q: queue.Queue = queue.Queue()
        threading.Thread(target=self._worker, daemon=True).start()

    # --- background jobs -------------------------------------------------------------------
    def submit(self, kind: str, **params) -> dict:
        job = {"id": len(self.jobs) + 1, "kind": kind, "params": params, "status": "queued",
               "message": "", "created": time.time()}
        self.jobs.append(job)
        self.q.put(job)
        return job

    def _worker(self):
        from ..detect import analyze
        from ..ingest import ingest_paths
        from ..qa import check_render
        from ..render import render_all_presets
        while True:
            job = self.q.get()
            job["status"] = "running"
            try:
                p = job["params"]
                if job["kind"] == "import":
                    msgs = []
                    for r in ingest_paths([p["path"]], self.cfg, self.db):
                        msgs.append(f"{Path(r.path).name}: {r.status} {r.message}")
                        if r.status == "ingested":
                            n = len(analyze(r.media_id, self.cfg, self.db))
                            msgs.append(f"{n} candidate(s)")
                    job["message"] = "; ".join(msgs) or "no supported files found"
                elif job["kind"] == "analyze":
                    job["message"] = f"{len(analyze(p['media_id'], self.cfg, self.db))} candidate(s)"
                elif job["kind"] == "render":
                    out = []
                    for r in render_all_presets(p["candidate_id"], self.cfg, self.db):
                        out.append(f"{r['preset']}: QA {check_render(r, self.cfg, self.db)['status']}")
                    job["message"] = ", ".join(out)
                job["status"] = "done"
            except Exception as exc:  # report, keep the worker alive
                job["status"] = "error"
                job["message"] = f"{type(exc).__name__}: {exc}"
                traceback.print_exc()
            job["finished"] = time.time()

    # --- views -------------------------------------------------------------------------------
    def url(self, path: str | None) -> str | None:
        if not path:
            return None
        try:
            rel = Path(path).resolve().relative_to(self.ws)
        except ValueError:
            return None
        return "/files/" + quote(str(rel))

    def media_list(self) -> list[dict]:
        out = []
        for m in self.db.list_media():
            cands = self.db.candidates(m["id"])
            out.append({**m, "thumb_url": self.url(m.get("thumb")), "name": Path(m["path"]).name,
                        "approved": sum(c["status"] == "approved" for c in cands),
                        "rejected": sum(c["status"] == "rejected" for c in cands)})
        return out

    def media_detail(self, media_id: int) -> dict | None:
        m = self.db.get_media(media_id)
        if not m:
            return None
        cands = self.db.candidates(media_id)
        for c in cands:
            c["renders"] = [{**r, "url": self.url(r["path"]), "thumb_url": self.url(r["thumb_path"])}
                            for r in self.db.renders(c["id"])]
        tl_path = self.ws / "analysis" / str(media_id) / "timeline.json"
        timeline = json.loads(tl_path.read_text()) if tl_path.exists() else None
        if timeline:
            timeline.pop("signals", None)
        return {"media": {**m, "name": Path(m["path"]).name},
                "thumbnails": [{**t, "url": self.url(t["path"])} for t in self.db.thumbnails(media_id)],
                "candidates": cands, "timeline": timeline}


class Handler(BaseHTTPRequestHandler):
    app: App = None  # set by make_server
    server_version = "ClipEngine/0.1"

    def log_message(self, fmt, *args):  # quieter console
        pass

    # --- helpers ---------------------------------------------------------------------------
    def _json(self, data, code: int = 200):
        body = json.dumps(data, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n))
        except json.JSONDecodeError:
            return {}

    def _file(self, rel: str):
        ws = self.app.ws
        target = (ws / rel).resolve()
        if ws not in target.parents or not target.is_file():
            return self._json({"error": "not found"}, 404)
        size = target.stat().st_size
        ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        start, end = 0, size - 1
        rng = self.headers.get("Range")
        m = re.match(r"bytes=(\d*)-(\d*)", rng or "")
        if m and (m.group(1) or m.group(2)):
            if m.group(1):
                start = int(m.group(1))
                end = int(m.group(2)) if m.group(2) else size - 1
            else:
                start = max(0, size - int(m.group(2)))
            end = min(end, size - 1)
            if start > end:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.end_headers()
                return
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        else:
            self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end - start + 1))
        self.end_headers()
        with open(target, "rb") as fh:
            fh.seek(start)
            left = end - start + 1
            while left > 0:
                chunk = fh.read(min(1 << 20, left))
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    return
                left -= len(chunk)

    # --- routes ----------------------------------------------------------------------------
    def do_GET(self):
        u = urlparse(self.path)
        p = u.path
        if p in ("/", "/index.html"):
            body = INDEX.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif p.startswith("/files/"):
            from urllib.parse import unquote
            self._file(unquote(p[len("/files/"):]))
        elif p == "/api/media":
            self._json(self.app.media_list())
        elif m := re.fullmatch(r"/api/media/(\d+)", p):
            d = self.app.media_detail(int(m.group(1)))
            self._json(d if d else {"error": "not found"}, 200 if d else 404)
        elif p == "/api/jobs":
            self._json(self.app.jobs[-20:][::-1])
        elif p == "/api/report":
            from ..report import collect
            self._json(collect(self.app.cfg, self.app.db))
        else:
            self._json({"error": "not found", "query": parse_qs(u.query)}, 404)

    def do_POST(self):
        p = urlparse(self.path).path
        body = self._body()
        app = self.app
        if m := re.fullmatch(r"/api/candidates/(\d+)/status", p):
            try:
                app.db.set_candidate_status(int(m.group(1)), body.get("status", ""))
            except ValueError as exc:
                return self._json({"error": str(exc)}, 400)
            self._json({"ok": True})
        elif m := re.fullmatch(r"/api/candidates/(\d+)/render", p):
            self._json(app.submit("render", candidate_id=int(m.group(1))))
        elif m := re.fullmatch(r"/api/media/(\d+)/analyze", p):
            self._json(app.submit("analyze", media_id=int(m.group(1))))
        elif p == "/api/import":
            path = (body.get("path") or "").strip()
            if not path:
                return self._json({"error": "path required"}, 400)
            self._json(app.submit("import", path=path))
        elif p == "/api/export":
            from ..export import export_approved
            m = export_approved(app.cfg, app.db)
            self._json({"path": m["path"], "exported": len(m["exported"]), "skipped": m["skipped"]})
        else:
            self._json({"error": "not found"}, 404)


def make_server(cfg: dict, db, host: str | None = None, port: int | None = None) -> ThreadingHTTPServer:
    app = App(cfg, db)
    handler = type("BoundHandler", (Handler,), {"app": app})
    host = host or cfg["dashboard"]["host"]
    port = cfg["dashboard"]["port"] if port is None else port
    srv = ThreadingHTTPServer((host, port), handler)
    srv.app = app
    return srv


def serve(cfg: dict, db, host: str | None = None, port: int | None = None) -> None:
    srv = make_server(cfg, db, host, port)
    h, p = srv.server_address[:2]
    print(f"Review dashboard: http://{h}:{p}/   (Ctrl+C to stop)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
