import sys

import requests

from . import config


class ApiError(RuntimeError):
    pass


class Client:
    def __init__(self) -> None:
        self.api_url = config.get_api_url()
        self.token = config.get_token()

    def _headers(self, auth: bool) -> dict:
        headers = {}
        if auth:
            if not self.token:
                print(
                    "Not signed in. Run `toolskalika auth login` and complete the "
                    "passkey ceremony in your browser, then `toolskalika auth token <value>`.",
                    file=sys.stderr,
                )
                raise SystemExit(1)
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _request(self, method: str, path: str, auth: bool = True, **kwargs) -> dict:
        url = f"{self.api_url}{path}"
        try:
            resp = requests.request(method, url, headers=self._headers(auth), timeout=60, **kwargs)
        except requests.ConnectionError as exc:
            raise ApiError(f"could not reach {self.api_url} — is the server running?") from exc

        if not resp.ok:
            detail = resp.text
            try:
                detail = resp.json().get("detail", detail)
            except ValueError:
                pass
            raise ApiError(f"{resp.status_code}: {detail}")

        return resp.json() if resp.content else {}

    def get(self, path: str, auth: bool = True) -> dict:
        return self._request("GET", path, auth=auth)

    def post(self, path: str, json_body: dict | None = None, auth: bool = True) -> dict:
        return self._request("POST", path, auth=auth, json=json_body or {})
