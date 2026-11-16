"""Command-line interface: python -m clipengine <command> ..."""
from __future__ import annotations

import argparse
import sys

from . import ffmpeg
from .config import load_config, workspace
from .db import open_db


def _ctx(args):
    cfg = load_config(args.config, {"workspace": args.workspace} if args.workspace else None)
    return cfg, open_db(workspace(cfg))


def cmd_ingest(args) -> int:
    from .ingest import ingest_paths
    cfg, db = _ctx(args)
    results = ingest_paths(args.paths, cfg, db)
    for r in results:
        mid = f"#{r.media_id}" if r.media_id else "-"
        print(f"{r.status:9} {mid:5} {r.path}  {r.message}")
    return 0 if all(r.status != "rejected" for r in results) else 1


def _media_ids(db, which: list[str]) -> list[int]:
    if which == ["all"]:
        return [m["id"] for m in db.list_media()]
    return [int(x.lstrip("#")) for x in which]


def cmd_analyze(args) -> int:
    from .detect import analyze
    cfg, db = _ctx(args)
    for mid in _media_ids(db, args.media):
        cands = analyze(mid, cfg, db, force=args.force)
        print(f"#{mid}: {len(cands)} candidate(s)")
        for c in cands:
            print(f"  cand #{c['id']:<4} {c['start_s']:7.1f}-{c['end_s']:<7.1f} ({c['duration_s']:.1f}s) "
                  f"conf={c['confidence']:.2f}  {c['description']}")
            for r in c["reasons"]["signals"]:
                print(f"      - {r['text']}")
            for n in c["reasons"]["notes"]:
                print(f"      * {n}")
    return 0


def _render_and_check(cand_ids, cfg, db, presets=None, qa=True) -> int:
    from .qa import check_render
    from .render import render_all_presets
    failed = 0
    for cid in cand_ids:
        for r in render_all_presets(cid, cfg, db, presets):
            status = check_render(r, cfg, db)["status"] if qa else "unchecked"
            failed += status == "failed"
            print(f"  cand #{cid:<4} {r['preset']:9} {r['width']}x{r['height']} {r['duration_s']:.1f}s "
                  f"render {r['render_s']:.1f}s  QA {status:8} {r['path']}")
    return failed


def cmd_render(args) -> int:
    cfg, db = _ctx(args)
    ids = [int(x) for x in args.candidates]
    if args.media is not None:
        ids += [c["id"] for c in db.candidates(args.media)][: args.top]
    if not ids:
        print("nothing to render: give candidate ids or --media")
        return 1
    return 1 if _render_and_check(ids, cfg, db, args.presets, not args.no_qa) else 0


def cmd_qa(args) -> int:
    from .qa import check_render
    cfg, db = _ctx(args)
    renders = db.renders() if args.renders == ["all"] else [r for r in db.renders() if str(r["id"]) in args.renders]
    for r in renders:
        q = check_render(r, cfg, db)
        print(f"render #{r['id']} {r['preset']:9} {q['status']}")
        for c in q["checks"]:
            if c["level"] != "pass" or args.verbose:
                print(f"    {c['level']:4} {c['name']}: {c['message']}")
    return 0


def cmd_run(args) -> int:
    """Ingest → analyse → render top N → QA, in one go."""
    from .detect import analyze
    from .ingest import ingest_paths
    cfg, db = _ctx(args)
    failed = 0
    for r in ingest_paths(args.paths, cfg, db):
        print(f"{r.status}: {r.path} {r.message}")
        if r.media_id is None:
            continue
        cands = analyze(r.media_id, cfg, db)
        print(f"  {len(cands)} candidate(s)")
        failed += _render_and_check([c["id"] for c in cands[: args.top]], cfg, db, args.presets)
    print("review them with:  python -m clipengine serve")
    return 1 if failed else 0


def cmd_export(args) -> int:
    from .export import export_approved
    cfg, db = _ctx(args)
    m = export_approved(cfg, db, args.dest)
    print(f"exported {len(m['exported'])} file(s) to {m['path']}; skipped {len(m['skipped'])}")
    for s in m["skipped"]:
        print(f"  skipped cand #{s['candidate_id']} {s.get('preset', '')}: {s['reason']}")
    return 0


def cmd_report(args) -> int:
    from .report import build_report
    cfg, db = _ctx(args)
    print(build_report(cfg, db))
    return 0


def cmd_serve(args) -> int:
    from .dashboard.server import serve
    cfg, db = _ctx(args)
    serve(cfg, db, host=args.host, port=args.port)
    return 0


def cmd_list(args) -> int:
    cfg, db = _ctx(args)
    for m in db.list_media():
        print(f"#{m['id']:<4} {m['status']:10} {m['duration_s']:7.1f}s {m['width']}x{m['height']} "
              f"cands={m['n_candidates']:<3} {m['path']}")
        if args.candidates:
            for c in db.candidates(m["id"]):
                print(f"      cand #{c['id']:<4} {c['start_s']:7.1f}-{c['end_s']:<7.1f} conf={c['confidence']:.2f} "
                      f"{c['status']:8} {c['description']}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="clipengine", description="Vice City Clip Engine (local beta)")
    p.add_argument("--config", help="YAML file merged over config/default.yaml")
    p.add_argument("--workspace", help="override the workspace directory")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("ingest", help="register recordings (files or directories)")
    s.add_argument("paths", nargs="+")
    s.set_defaults(func=cmd_ingest)

    s = sub.add_parser("analyze", help="detect highlight candidates")
    s.add_argument("media", nargs="+", help="media ids, or 'all'")
    s.add_argument("--force", action="store_true", help="re-decode instead of using cached features")
    s.set_defaults(func=cmd_analyze)

    s = sub.add_parser("render", help="render candidates (landscape + vertical) and run QA")
    s.add_argument("candidates", nargs="*", help="candidate ids")
    s.add_argument("--media", type=int, help="render the top candidates of this recording")
    s.add_argument("--top", type=int, default=3)
    s.add_argument("--presets", nargs="+", help="subset of presets (default: all)")
    s.add_argument("--no-qa", action="store_true")
    s.set_defaults(func=cmd_render)

    s = sub.add_parser("qa", help="re-run quality checks on renders")
    s.add_argument("renders", nargs="+", help="render ids, or 'all'")
    s.add_argument("-v", "--verbose", action="store_true")
    s.set_defaults(func=cmd_qa)

    s = sub.add_parser("run", help="ingest, analyse, render top clips and QA in one step")
    s.add_argument("paths", nargs="+")
    s.add_argument("--top", type=int, default=3)
    s.add_argument("--presets", nargs="+")
    s.set_defaults(func=cmd_run)

    s = sub.add_parser("export", help="export approved clips that passed QA")
    s.add_argument("--dest")
    s.set_defaults(func=cmd_export)

    s = sub.add_parser("report", help="processing time, resources and storage summary")
    s.set_defaults(func=cmd_report)

    s = sub.add_parser("serve", help="start the local review dashboard")
    s.add_argument("--host")
    s.add_argument("--port", type=int)
    s.set_defaults(func=cmd_serve)

    s = sub.add_parser("list", help="list recordings")
    s.add_argument("-c", "--candidates", action="store_true", help="also list candidates")
    s.set_defaults(func=cmd_list)
    return p


def main(argv: list[str] | None = None) -> int:
    ffmpeg.require_tools()
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
