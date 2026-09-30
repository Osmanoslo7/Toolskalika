import argparse
import sys

from ..client import ApiError, Client


def cmd_list(args: argparse.Namespace) -> None:
    client = Client()
    try:
        tools = client.get("/tools")
    except ApiError as exc:
        raise SystemExit(str(exc)) from exc
    for t in tools:
        print(f"{t['name']:<12} {t['description']}")


def cmd_run(args: argparse.Namespace) -> None:
    prompt = " ".join(args.prompt).strip()
    if not prompt:
        if sys.stdin.isatty():
            raise SystemExit("provide a prompt, e.g. toolskalika run brainstorm \"...\"")
        prompt = sys.stdin.read().strip()
    if not prompt:
        raise SystemExit("prompt must not be empty")

    client = Client()
    try:
        result = client.post(f"/tools/{args.tool}/run", {"prompt": prompt})
    except ApiError as exc:
        raise SystemExit(str(exc)) from exc

    print(result["output"])
    if not result.get("used_llm"):
        print("\n(local fallback — set ANTHROPIC_API_KEY on the server for real generation)", file=sys.stderr)


def cmd_history(args: argparse.Namespace) -> None:
    client = Client()
    try:
        runs = client.get(f"/tools/history?limit={args.limit}")
    except ApiError as exc:
        raise SystemExit(str(exc)) from exc
    for r in runs:
        print(f"[{r['created_at']}] {r['tool']}: {r['prompt'][:80]}")


def register(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser("tools", help="List available tools")
    p.set_defaults(func=cmd_list)

    p = subparsers.add_parser("run", help="Run a tool with a prompt")
    p.add_argument("tool", help="Tool name, see `toolskalika tools`")
    p.add_argument("prompt", nargs="*", help="The prompt (or pipe it via stdin)")
    p.set_defaults(func=cmd_run)

    p = subparsers.add_parser("history", help="Show recent tool runs")
    p.add_argument("--limit", type=int, default=20)
    p.set_defaults(func=cmd_history)
