import json
import shutil
import threading
import time
import urllib.request

import pytest

from clipengine import cli
from clipengine.dashboard.server import make_server
from clipengine.detect import analyze
from clipengine.export import export_approved
from clipengine.ingest import ingest_file
from clipengine.qa import check_render
from clipengine.render import render_all_presets

from .conftest import sha256


@pytest.fixture
def server(cfg, db):
    srv = make_server(cfg, db, "127.0.0.1", 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv, f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()
    srv.server_close()


def get(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req) as r:
        return r.status, dict(r.headers), r.read()


def post(url, body):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


def wait_jobs(base, timeout=120):
    end = time.time() + timeout
    while time.time() < end:
        jobs = json.loads(get(base + "/api/jobs")[2])
        if jobs and all(j["status"] in ("done", "error") for j in jobs):
            return jobs
        time.sleep(0.3)
    raise TimeoutError


def test_dashboard_import_review_render_export(server, footage_dir, tmp_path):
    srv, base = server
    src = tmp_path / "clip.mp4"
    shutil.copy(footage_dir / "match.mp4", src)
    before = sha256(src)
    status, _, html = get(base + "/")
    assert status == 200 and b"Clip Review" in html

    post(base + "/api/import", {"path": str(src)})
    jobs = wait_jobs(base)
    assert jobs[0]["status"] == "done", jobs
    media = json.loads(get(base + "/api/media")[2])
    assert len(media) == 1 and media[0]["n_candidates"] >= 2 and media[0]["thumb_url"]
    detail = json.loads(get(base + f"/api/media/{media[0]['id']}")[2])
    assert detail["timeline"]["fused"] and detail["thumbnails"]
    top, other = detail["candidates"][0], detail["candidates"][1]

    post(base + f"/api/candidates/{top['id']}/render", {})
    jobs = wait_jobs(base)
    assert jobs[0]["status"] == "done", jobs
    assert post(base + f"/api/candidates/{top['id']}/status", {"status": "approved"})["ok"]
    assert post(base + f"/api/candidates/{other['id']}/status", {"status": "rejected"})["ok"]
    detail = json.loads(get(base + f"/api/media/{media[0]['id']}")[2])
    by_id = {c["id"]: c for c in detail["candidates"]}
    assert by_id[top["id"]]["status"] == "approved" and by_id[other["id"]]["status"] == "rejected"
    renders = by_id[top["id"]]["renders"]
    assert {r["preset"] for r in renders} == {"landscape", "vertical"}

    # video preview supports seeking (HTTP range requests)
    status, headers, body = get(base + renders[0]["url"], {"Range": "bytes=0-99"})
    assert status == 206 and len(body) == 100 and headers["Content-Range"].startswith("bytes 0-99/")

    exp = post(base + "/api/export", {})
    assert exp["exported"] == 2
    assert sha256(src) == before


def test_dashboard_refuses_files_outside_workspace(server):
    _, base = server
    for path in ("/files/../../etc/passwd", "/files/%2e%2e/%2e%2e/etc/passwd"):
        with pytest.raises(urllib.error.HTTPError) as e:
            get(base + path)
        assert e.value.code == 404
    with pytest.raises(urllib.error.HTTPError) as e:
        post(base + "/api/candidates/1/status", {"status": "bogus"})
    assert e.value.code == 400


def test_export_skips_unrendered_and_failed(footage_dir, cfg, db, tmp_path):
    r = ingest_file(footage_dir / "match.mp4", cfg, db)
    c1, c2 = analyze(r.media_id, cfg, db)[:2]
    for rend in render_all_presets(c1["id"], cfg, db, ["landscape"]):
        check_render(rend, cfg, db)
    db.set_candidate_status(c1["id"], "approved")
    db.set_candidate_status(c2["id"], "approved")          # approved but never rendered
    m = export_approved(cfg, db, tmp_path / "out")
    assert [e["preset"] for e in m["exported"]] == ["landscape"]
    assert m["skipped"] == [{"candidate_id": c2["id"], "reason": "not rendered"}]
    assert (tmp_path / "out" / "manifest.json").exists()
    rend = db.renders(c1["id"])[0]
    db.set_render_qa(rend["id"], "failed", {"checks": []})
    m = export_approved(cfg, db, tmp_path / "out2")
    assert m["exported"] == [] and any("QA failed" in s["reason"] for s in m["skipped"])


def test_cli_run_end_to_end(footage_dir, tmp_path, capsys):
    src = tmp_path / "rec.mp4"
    shutil.copy(footage_dir / "match.mp4", src)
    before = sha256(src)
    ws = str(tmp_path / "ws")
    assert cli.main(["--workspace", ws, "run", str(src), "--top", "2"]) == 0
    out = capsys.readouterr().out
    assert out.count("QA passed") + out.count("QA warning") == 4
    assert cli.main(["--workspace", ws, "report"]) == 0
    rep = capsys.readouterr().out
    assert "render:vertical" in rep and "Workspace storage" in rep
    assert sha256(src) == before
