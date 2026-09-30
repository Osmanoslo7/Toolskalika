import datetime as dt

from sqlalchemy import ForeignKey, LargeBinary, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def _utcnow() -> dt.datetime:
    # Naive UTC on purpose: SQLite drops tzinfo on round-trip, so mixing
    # aware "now" values with values read back from the DB raises
    # TypeError on comparison. Every datetime in this app is UTC, naive.
    return dt.datetime.utcnow()


class User(Base):
    """The single operator. Exactly one row may ever exist."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(320), unique=True)
    webauthn_user_handle: Mapped[bytes] = mapped_column(LargeBinary)
    created_at: Mapped[dt.datetime] = mapped_column(default=_utcnow)

    credentials: Mapped[list["Credential"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    tokens: Mapped[list["PersonalAccessToken"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Credential(Base):
    """A registered passkey (Face ID / Touch ID / Windows Hello / security key)."""

    __tablename__ = "credentials"

    id: Mapped[str] = mapped_column(String(512), primary_key=True)  # base64url credential id
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    public_key: Mapped[bytes] = mapped_column(LargeBinary)
    sign_count: Mapped[int] = mapped_column(default=0)
    transports: Mapped[str] = mapped_column(String(200), default="")
    nickname: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[dt.datetime] = mapped_column(default=_utcnow)
    last_used_at: Mapped[dt.datetime | None] = mapped_column(default=None)

    user: Mapped[User] = relationship(back_populates="credentials")


class PersonalAccessToken(Base):
    """Long-lived bearer token the CLI holds after a passkey login."""

    __tablename__ = "personal_access_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200), default="cli")
    created_at: Mapped[dt.datetime] = mapped_column(default=_utcnow)
    expires_at: Mapped[dt.datetime | None] = mapped_column(default=None)
    last_used_at: Mapped[dt.datetime | None] = mapped_column(default=None)
    revoked_at: Mapped[dt.datetime | None] = mapped_column(default=None)

    user: Mapped[User] = relationship(back_populates="tokens")


class ToolRun(Base):
    """History log of tool invocations, for recall/context in later runs."""

    __tablename__ = "tool_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    tool_name: Mapped[str] = mapped_column(String(100))
    input_prompt: Mapped[str] = mapped_column(Text)
    output_text: Mapped[str] = mapped_column(Text)
    used_llm: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[dt.datetime] = mapped_column(default=_utcnow)
