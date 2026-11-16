"""SQLite storage. The only module that writes SQL."""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS media (
    id INTEGER PRIMARY KEY,
    path TEXT NOT NULL,
    fingerprint TEXT NOT NULL UNIQUE,
    size_bytes INTEGER NOT NULL,
    mtime REAL NOT NULL,
    container TEXT,
    duration_s REAL,
    width INTEGER,
    height INTEGER,
    fps REAL,
    video_codec TEXT,
    audio_codec TEXT,
    has_audio INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'ingested',
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS thumbnails (
    id INTEGER PRIMARY KEY,
    media_id INTEGER NOT NULL REFERENCES media(id) ON DELETE CASCADE,
    t_s REAL NOT NULL,
    path TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS candidates (
    id INTEGER PRIMARY KEY,
    media_id INTEGER NOT NULL REFERENCES media(id) ON DELETE CASCADE,
    start_s REAL NOT NULL,
    end_s REAL NOT NULL,
    duration_s REAL NOT NULL,
    peak_s REAL NOT NULL,
    description TEXT NOT NULL,
    confidence REAL NOT NULL,
    reasons_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'new',
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS renders (
    id INTEGER PRIMARY KEY,
    candidate_id INTEGER NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
    preset TEXT NOT NULL,
    path TEXT NOT NULL,
    thumb_path TEXT,
    width INTEGER,
    height INTEGER,
    duration_s REAL,
    size_bytes INTEGER,
    render_s REAL,
    qa_status TEXT NOT NULL DEFAULT 'pending',
    qa_json TEXT,
    created_at REAL NOT NULL,
    UNIQUE(candidate_id, preset)
);
CREATE TABLE IF NOT EXISTS stage_runs (
    id INTEGER PRIMARY KEY,
    stage TEXT NOT NULL,
    media_id INTEGER,
    wall_s REAL NOT NULL,
    cpu_s REAL NOT NULL,
    peak_rss_mb REAL,
    detail_json TEXT,
    created_at REAL NOT NULL
);
"""


class DB:
    def __init__(self, path: str | Path):
        self.path = str(path)
        # check_same_thread=False: the dashboard serves requests from worker threads.
        self.conn = sqlite3.connect(self.path, check_same_thread=False, timeout=30)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("PRAGMA journal_mode = WAL")
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    # --- generic helpers -------------------------------------------------
    def _insert(self, table: str, row: dict) -> int:
        cols = ", ".join(row)
        marks = ", ".join("?" for _ in row)
        cur = self.conn.execute(f"INSERT INTO {table} ({cols}) VALUES ({marks})", list(row.values()))
        self.conn.commit()
        return int(cur.lastrowid)

    def _all(self, sql: str, args: tuple = ()) -> list[dict]:
        return [dict(r) for r in self.conn.execute(sql, args).fetchall()]

    def _one(self, sql: str, args: tuple = ()) -> dict | None:
        r = self.conn.execute(sql, args).fetchone()
        return dict(r) if r else None

    # --- media -------------------------------------------------------------
    def add_media(self, **fields) -> int:
        fields.setdefault("created_at", time.time())
        return self._insert("media", fields)

    def media_by_fingerprint(self, fp: str) -> dict | None:
        return self._one("SELECT * FROM media WHERE fingerprint = ?", (fp,))

    def get_media(self, media_id: int) -> dict | None:
        return self._one("SELECT * FROM media WHERE id = ?", (media_id,))

    def list_media(self) -> list[dict]:
        return self._all(
            "SELECT m.*, (SELECT COUNT(*) FROM candidates c WHERE c.media_id = m.id) AS n_candidates,"
            " (SELECT path FROM thumbnails t WHERE t.media_id = m.id ORDER BY t_s LIMIT 1 OFFSET 1) AS thumb"
            " FROM media m ORDER BY m.id DESC")

    def set_media_status(self, media_id: int, status: str) -> None:
        self.conn.execute("UPDATE media SET status = ? WHERE id = ?", (status, media_id))
        self.conn.commit()

    def add_thumbnail(self, media_id: int, t_s: float, path: str) -> int:
        return self._insert("thumbnails", {"media_id": media_id, "t_s": t_s, "path": path})

    def thumbnails(self, media_id: int) -> list[dict]:
        return self._all("SELECT * FROM thumbnails WHERE media_id = ? ORDER BY t_s", (media_id,))

    # --- candidates ----------------------------------------------------------
    def replace_candidates(self, media_id: int, cands: list[dict]) -> list[int]:
        """Re-analysis replaces earlier candidates (and their renders) for that recording."""
        self.conn.execute("DELETE FROM candidates WHERE media_id = ?", (media_id,))
        self.conn.commit()
        ids = []
        for c in cands:
            ids.append(self._insert("candidates", {
                "media_id": media_id, "start_s": c["start_s"], "end_s": c["end_s"],
                "duration_s": c["duration_s"], "peak_s": c["peak_s"],
                "description": c["description"], "confidence": c["confidence"],
                "reasons_json": json.dumps(c["reasons"]), "created_at": time.time()}))
        return ids

    def candidates(self, media_id: int | None = None, status: str | None = None) -> list[dict]:
        sql, args = "SELECT * FROM candidates WHERE 1=1", []
        if media_id is not None:
            sql += " AND media_id = ?"
            args.append(media_id)
        if status:
            sql += " AND status = ?"
            args.append(status)
        rows = self._all(sql + " ORDER BY confidence DESC", tuple(args))
        for r in rows:
            r["reasons"] = json.loads(r.pop("reasons_json"))
        return rows

    def get_candidate(self, cand_id: int) -> dict | None:
        r = self._one("SELECT * FROM candidates WHERE id = ?", (cand_id,))
        if r:
            r["reasons"] = json.loads(r.pop("reasons_json"))
        return r

    def set_candidate_status(self, cand_id: int, status: str) -> None:
        if status not in ("new", "approved", "rejected"):
            raise ValueError(f"invalid status {status!r}")
        self.conn.execute("UPDATE candidates SET status = ? WHERE id = ?", (status, cand_id))
        self.conn.commit()

    # --- renders ---------------------------------------------------------------
    def upsert_render(self, **fields) -> int:
        fields.setdefault("created_at", time.time())
        self.conn.execute("DELETE FROM renders WHERE candidate_id = ? AND preset = ?",
                          (fields["candidate_id"], fields["preset"]))
        return self._insert("renders", fields)

    def set_render_qa(self, render_id: int, status: str, detail: dict) -> None:
        self.conn.execute("UPDATE renders SET qa_status = ?, qa_json = ? WHERE id = ?",
                          (status, json.dumps(detail), render_id))
        self.conn.commit()

    def renders(self, candidate_id: int | None = None) -> list[dict]:
        if candidate_id is None:
            rows = self._all("SELECT * FROM renders ORDER BY id")
        else:
            rows = self._all("SELECT * FROM renders WHERE candidate_id = ? ORDER BY preset", (candidate_id,))
        for r in rows:
            r["qa"] = json.loads(r.pop("qa_json")) if r.get("qa_json") else None
        return rows

    # --- metrics ---------------------------------------------------------------
    def add_stage_run(self, **fields) -> int:
        fields.setdefault("created_at", time.time())
        if isinstance(fields.get("detail_json"), dict):
            fields["detail_json"] = json.dumps(fields["detail_json"])
        return self._insert("stage_runs", fields)

    def stage_runs(self, media_id: int | None = None) -> list[dict]:
        if media_id is None:
            return self._all("SELECT * FROM stage_runs ORDER BY id")
        return self._all("SELECT * FROM stage_runs WHERE media_id = ? ORDER BY id", (media_id,))


def open_db(workspace: Path) -> DB:
    return DB(Path(workspace) / "library.db")
