import datetime as dt

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..models import PersonalAccessToken, User
from ..security import generate_personal_access_token, hash_token

_bearer = HTTPBearer(auto_error=False)


def issue_token(db: Session, user: User, name: str = "cli", ttl_days: int | None = None) -> str:
    settings = get_settings()
    ttl_days = settings.pat_default_ttl_days if ttl_days is None else ttl_days
    token, token_hash = generate_personal_access_token()
    expires_at = None
    if ttl_days:
        expires_at = dt.datetime.utcnow() + dt.timedelta(days=ttl_days)
    db.add(
        PersonalAccessToken(
            user_id=user.id,
            token_hash=token_hash,
            name=name,
            expires_at=expires_at,
        )
    )
    db.commit()
    return token


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")

    token_hash = hash_token(creds.credentials)
    pat = (
        db.query(PersonalAccessToken)
        .filter(PersonalAccessToken.token_hash == token_hash)
        .one_or_none()
    )
    if pat is None or pat.revoked_at is not None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or revoked token")

    now = dt.datetime.utcnow()
    if pat.expires_at is not None and pat.expires_at < now:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "token expired")

    pat.last_used_at = now
    db.commit()

    user = db.get(User, pat.user_id)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "operator account not found")
    return user
