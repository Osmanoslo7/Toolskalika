import argparse

from .. import config
from ..client import ApiError, Client


def cmd_url(args: argparse.Namespace) -> None:
    if args.value:
        config.set_api_url(args.value)
        print(f"API URL set to {args.value}")
    else:
        print(config.get_api_url())


def cmd_login(args: argparse.Namespace) -> None:
    api_url = config.get_api_url()
    print(f"Open this in a browser on the device with your passkey:\n\n  {api_url}/static/login.html\n")
    print(
        "Complete the Face ID / Touch ID / Windows Hello prompt there, then copy the "
        "token it shows you and run:\n\n  toolskalika auth token <the-token>\n"
    )


def cmd_token(args: argparse.Namespace) -> None:
    config.set_token(args.value)
    client = Client()
    try:
        me = client.get("/auth/me")
    except ApiError as exc:
        config.clear_token()
        raise SystemExit(f"token rejected: {exc}") from exc
    print(f"Signed in as {me['name']} <{me['email']}>")


def cmd_whoami(args: argparse.Namespace) -> None:
    client = Client()
    try:
        me = client.get("/auth/me")
    except ApiError as exc:
        raise SystemExit(str(exc)) from exc
    print(f"{me['name']} <{me['email']}> (operator id {me['id']})")


def cmd_logout(args: argparse.Namespace) -> None:
    client = Client()
    try:
        client.post("/auth/logout")
    except ApiError as exc:
        print(f"warning: server-side revoke failed ({exc}); clearing local token anyway")
    config.clear_token()
    print("Signed out. All active tokens for the operator were revoked.")


def register(subparsers: argparse._SubParsersAction) -> None:
    auth = subparsers.add_parser("auth", help="Authenticate against your Toolskalika API")
    auth_sub = auth.add_subparsers(dest="auth_command", required=True)

    p = auth_sub.add_parser("url", help="Get/set the API base URL")
    p.add_argument("value", nargs="?", help="New API URL, e.g. http://localhost:8000")
    p.set_defaults(func=cmd_url)

    p = auth_sub.add_parser("login", help="Show the passkey login link")
    p.set_defaults(func=cmd_login)

    p = auth_sub.add_parser("token", help="Store a token obtained from the browser login")
    p.add_argument("value", help="The token shown after completing the passkey ceremony")
    p.set_defaults(func=cmd_token)

    p = auth_sub.add_parser("whoami", help="Show the currently authenticated operator")
    p.set_defaults(func=cmd_whoami)

    p = auth_sub.add_parser("logout", help="Revoke all tokens and clear local credentials")
    p.set_defaults(func=cmd_logout)
