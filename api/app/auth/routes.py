import json

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..models import Credential, PersonalAccessToken, User
from . import webauthn as wa
from .tokens import get_current_user, issue_token

router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterVerifyBody(BaseModel):
    flow_id: str
    credential: dict
    nickname: str = "primary passkey"


class LoginVerifyBody(BaseModel):
    flow_id: str
    credential: dict


class TokenResponse(BaseModel):
    token: str
    token_type: str = "bearer"


def _the_operator(db: Session) -> User | None:
    return db.query(User).order_by(User.id.asc()).first()


def _is_registered(db: Session) -> bool:
    return db.query(Credential).count() > 0


@router.get("/status")
def status_check(db: Session = Depends(get_db)):
    return {"registered": _is_registered(db)}


@router.post("/register/options")
def register_options(db: Session = Depends(get_db)):
    if _is_registered(db):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "an operator is already registered")

    settings = get_settings()
    user = _the_operator(db)
    if user is None:
        user = User(
            name=settings.owner_name,
            email=settings.owner_email,
            webauthn_user_handle=wa.new_user_handle(),
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    flow_id, options_json = wa.start_registration(
        user_handle=user.webauthn_user_handle, name=user.name, email=user.email
    )
    return {"flow_id": flow_id, "publicKey": json.loads(options_json)}


@router.post("/register/verify", response_model=TokenResponse)
def register_verify(body: RegisterVerifyBody, db: Session = Depends(get_db)):
    if _is_registered(db):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "an operator is already registered")

    user = _the_operator(db)
    if user is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "call /auth/register/options first")

    try:
        verified = wa.finish_registration(body.flow_id, json.dumps(body.credential))
    except Exception as exc:  # noqa: BLE001 - surface ceremony failure to the caller
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    db.add(
        Credential(
            id=wa.b64url_encode(verified.credential_id),
            user_id=user.id,
            public_key=verified.credential_public_key,
            sign_count=verified.sign_count,
            nickname=body.nickname,
        )
    )
    db.commit()

    token = issue_token(db, user, name="initial-registration")
    return TokenResponse(token=token)


@router.post("/login/options")
def login_options(db: Session = Depends(get_db)):
    user = _the_operator(db)
    if user is None or not user.credentials:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "no operator registered yet")

    flow_id, options_json = wa.start_authentication([c.id for c in user.credentials])
    return {"flow_id": flow_id, "publicKey": json.loads(options_json)}


@router.post("/login/verify", response_model=TokenResponse)
def login_verify(body: LoginVerifyBody, db: Session = Depends(get_db)):
    cred_id = body.credential.get("id")
    cred = db.get(Credential, cred_id) if cred_id else None
    if cred is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "unknown credential")

    try:
        verified = wa.finish_authentication(
            body.flow_id,
            json.dumps(body.credential),
            credential_public_key=cred.public_key,
            credential_current_sign_count=cred.sign_count,
        )
    except Exception as exc:  # noqa: BLE001 - surface ceremony failure to the caller
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    cred.sign_count = verified.new_sign_count
    cred.last_used_at = wa.utcnow()
    db.commit()

    token = issue_token(db, cred.user, name="login")
    return TokenResponse(token=token)


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return {"name": user.name, "email": user.email, "id": user.id}


@router.post("/logout")
def logout(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Revokes every active token for the operator (a single-operator kill
    switch: any device holding an old token is signed out too)."""
    db.query(PersonalAccessToken).filter(
        PersonalAccessToken.user_id == user.id,
        PersonalAccessToken.revoked_at.is_(None),
    ).update({"revoked_at": wa.utcnow()})
    db.commit()
    return {"revoked": True}
