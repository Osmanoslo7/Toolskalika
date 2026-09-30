import argparse

from .commands import auth, tools


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="toolskalika", description="Your personal API, from the terminal.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    auth.register(subparsers)
    tools.register(subparsers)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
