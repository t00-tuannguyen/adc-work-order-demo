"""Phiên đăng nhập phía server — ADC-008 §Bảo mật. Hết hạn sau `ttl` không hoạt động (trượt)."""

import hashlib
from datetime import datetime, timedelta

from sqlalchemy import update
from sqlalchemy.orm import Session

from src.modules.identity.models import User, UserSession
from src.modules.identity.oidc import random_token


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(
    db: Session, user: User, *, now: datetime, ttl: timedelta, ip: str | None = None, user_agent: str | None = None
) -> str:
    """Trả token cho cookie; DB chỉ giữ hash nên lộ DB không lộ phiên."""
    token = random_token()
    db.add(
        UserSession(
            id=_hash(token),
            user_id=user.id,
            created_at=now,
            last_seen_at=now,
            expires_at=now + ttl,
            ip=ip,
            user_agent=user_agent,
        )
    )
    db.commit()
    return token


def get_session_user(db: Session, token: str | None, *, now: datetime, ttl: timedelta) -> User | None:
    """None nếu không có / đã thu hồi / hết hạn. Còn hạn → gia hạn thêm `ttl` kể từ bây giờ."""
    if not token:
        return None
    session = db.get(UserSession, _hash(token))
    if session is None or session.revoked_at is not None or session.expires_at <= now:
        return None
    session.last_seen_at, session.expires_at = now, now + ttl
    db.commit()
    return db.get(User, session.user_id)


def revoke_session(db: Session, token: str | None, *, now: datetime) -> str | None:
    """Trả user_id của phiên vừa thu hồi (để ghi audit), None nếu không có phiên còn hiệu lực."""
    if not token:
        return None
    session = db.get(UserSession, _hash(token))
    if session is None or session.revoked_at is not None:
        return None
    session.revoked_at = now
    db.commit()
    return session.user_id


def revoke_all_sessions(db: Session, user_id: str, *, now: datetime) -> None:
    db.execute(
        update(UserSession)
        .where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    db.commit()
