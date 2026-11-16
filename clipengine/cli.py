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
