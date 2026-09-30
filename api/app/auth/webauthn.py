"""WebAuthn (passkey) ceremonies.

This is what actually backs "Face ID auth" here: Face ID / Touch ID /
Windows Hello never talk to this server directly. They unlock a passkey
inside the operating system's platform authenticator, and *that*
authenticator talks to us over the standard WebAuthn protocol. The browser
is required to run the ceremony (navigator.credentials.create / .get) —
see static/login.html.

Challenges are short-lived and kept in memory between the "generate
options" and "verify response" calls of a single ceremony. That's fine for
a single-operator tool running as one process; it just means a server
restart mid-login invalidates any in-flight ceremony (harmless — retry).
"""

import base64
import datetime as dt
import time
import uuid
from dataclasses import dataclass

from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from ..config import get_settings

_CHALLENGE_TTL_SECONDS = 300


@dataclass
class _PendingChallenge:
    challenge: bytes
    created_at: float


class _ChallengeStore:
    def __init__(self) -> None:
        self._pending: dict[str, _PendingChallenge] = {}

    def put(self, challenge: bytes) -> str:
        self._sweep()
        flow_id = uuid.uuid4().hex
        self._pending[flow_id] = _PendingChallenge(challenge, time.monotonic())
        return flow_id

    def pop(self, flow_id: str) -> bytes | None:
        self._sweep()
        pending = self._pending.pop(flow_id, None)
        return pending.challenge if pending else None

    def _sweep(self) -> None:
        cutoff = time.monotonic() - _CHALLENGE_TTL_SECONDS
        expired = [fid for fid, p in self._pending.items() if p.created_at < cutoff]
        for fid in expired:
            self._pending.pop(fid, None)


_challenge_store = _ChallengeStore()


def b64url_decode(value: str) -> bytes:
    padded = value + "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(padded)


def b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


def start_registration(user_handle: bytes, name: str, email: str) -> tuple[str, str]:
    settings = get_settings()
    options = generate_registration_options(
        rp_id=settings.rp_id,
        rp_name=settings.rp_name,
        user_id=user_handle,
        user_name=email,
        user_display_name=name,
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.REQUIRED,
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
    )
    flow_id = _challenge_store.put(options.challenge)
    return flow_id, options_to_json(options)


def finish_registration(flow_id: str, credential_json: str):
    challenge = _challenge_store.pop(flow_id)
    if challenge is None:
        raise ValueError("registration ceremony expired or unknown; try again")

    settings = get_settings()
    return verify_registration_response(
        credential=credential_json,
        expected_challenge=challenge,
        expected_origin=settings.origin,
        expected_rp_id=settings.rp_id,
        require_user_verification=True,
    )


def start_authentication(allowed_credential_ids: list[str]) -> tuple[str, str]:
    settings = get_settings()
    options = generate_authentication_options(
        rp_id=settings.rp_id,
        allow_credentials=[
            PublicKeyCredentialDescriptor(id=b64url_decode(cred_id))
            for cred_id in allowed_credential_ids
        ],
        user_verification=UserVerificationRequirement.REQUIRED,
    )
    flow_id = _challenge_store.put(options.challenge)
    return flow_id, options_to_json(options)


def finish_authentication(
    flow_id: str,
    credential_json: str,
    credential_public_key: bytes,
    credential_current_sign_count: int,
):
    challenge = _challenge_store.pop(flow_id)
    if challenge is None:
        raise ValueError("login ceremony expired or unknown; try again")

    settings = get_settings()
    return verify_authentication_response(
        credential=credential_json,
        expected_challenge=challenge,
        expected_origin=settings.origin,
        expected_rp_id=settings.rp_id,
        credential_public_key=credential_public_key,
        credential_current_sign_count=credential_current_sign_count,
        require_user_verification=True,
    )


def new_user_handle() -> bytes:
    return uuid.uuid4().bytes


def utcnow() -> dt.datetime:
    return dt.datetime.utcnow()
