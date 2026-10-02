"""Bảng của Identity context — ADC-008 §Mô hình dữ liệu."""

import uuid
from datetime import datetime

from sqlalchemy import Enum, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.modules.identity.permissions import Role, UserStatus
from src.services.db import Base, UTCDateTime, utcnow


def _new_id() -> str:
    return uuid.uuid4().hex


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_new_id)
    google_sub: Mapped[str] = mapped_column(String(255), unique=True)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    name: Mapped[str] = mapped_column(String(255), default="")
    avatar_url: Mapped[str | None] = mapped_column(Text)
    email_domain: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role | None] = mapped_column(Enum(Role, native_enum=False))
    status: Mapped[UserStatus] = mapped_column(Enum(UserStatus, native_enum=False), index=True)
    requested_role: Mapped[Role | None] = mapped_column(Enum(Role, native_enum=False))
    request_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    approved_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_login_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class OAuthLoginAttempt(Base):
    """Một lượt "Tiếp tục với Google" đang chờ callback — dùng 1 lần, hết hạn sau OAUTH_STATE_TTL_MIN."""

    __tablename__ = "oauth_login_attempts"

    state: Mapped[str] = mapped_column(String(64), primary_key=True)
    nonce: Mapped[str] = mapped_column(String(64))
    code_verifier: Mapped[str] = mapped_column(String(128))
    next_path: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class UserSession(Base):
    """Phiên đăng nhập — cookie chỉ chứa token ngẫu nhiên; DB lưu sha256(token) làm id."""

    __tablename__ = "sessions"
    __table_args__ = (Index("ix_sessions_user_id_revoked_at", "user_id", "revoked_at"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)
    last_seen_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(Text)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
