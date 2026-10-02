"""Luồng đăng nhập Google — ADC-008 §Kiến trúc hệ thống."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.modules.identity.models import OAuthLoginAttempt, User
from src.modules.identity.oidc import (
    AuthError,
    AuthErrorCode,
    GoogleIdentity,
    email_domain,
    is_domain_allowed,
    pkce_challenge,
    random_token,
    safe_next_path,
)
from src.modules.identity.permissions import Role, UserStatus


class LoginOutcome(StrEnum):
    SIGNUP = "SIGNUP"  # → /signup/complete
    PENDING = "PENDING"  # → /pending
    ACTIVE = "ACTIVE"  # → trang trước đó (next) hoặc trang chính


@dataclass(frozen=True)
class LoginStart:
    state: str
    nonce: str
    code_challenge: str


def start_login(db: Session, next_path: str | None, now: datetime) -> LoginStart:
    attempt = OAuthLoginAttempt(
        state=random_token(),
        nonce=random_token(),
        code_verifier=random_token(48),  # 64 ký tự, trong khoảng 43–128 của RFC 7636
        next_path=safe_next_path(next_path),
        created_at=now,
    )
    db.add(attempt)
    db.commit()
    return LoginStart(attempt.state, attempt.nonce, pkce_challenge(attempt.code_verifier))


def consume_login_attempt(
    db: Session, state: str | None, cookie_state: str | None, now: datetime, ttl: timedelta
) -> OAuthLoginAttempt:
    """state phải khớp cookie của chính trình duyệt này (chống CSRF), còn hạn, và chỉ dùng 1 lần."""
    if not state or not cookie_state or state != cookie_state:
        raise AuthError(AuthErrorCode.STATE_MISMATCH, "state không khớp cookie")
    attempt = db.get(OAuthLoginAttempt, state)
    if attempt is None:
        raise AuthError(AuthErrorCode.STATE_MISMATCH, "state không tồn tại hoặc đã dùng")
    db.delete(attempt)
    db.commit()
    if now - attempt.created_at > ttl:
        raise AuthError(AuthErrorCode.STATE_MISMATCH, "state hết hạn")
    return attempt


def resolve_user(
    db: Session,
    identity: GoogleIdentity,
    *,
    allowed_domains: frozenset[str],
    bootstrap_admins: frozenset[str],
    now: datetime,
) -> tuple[User, LoginOutcome]:
    """Tìm user theo google_sub (không theo email — người dùng có thể đổi email Google)."""
    if not is_domain_allowed(identity.email, allowed_domains):
        raise AuthError(AuthErrorCode.DOMAIN_NOT_ALLOWED)
    if not identity.email_verified:
        raise AuthError(AuthErrorCode.EMAIL_NOT_VERIFIED)

    user = db.scalar(select(User).where(User.google_sub == identity.sub))
    owner = db.scalar(select(User).where(User.email == identity.email))
    if owner is not None and owner is not user:
        # Email đã thuộc google_sub khác (vd email Workspace cấp lại cho người mới) → không tự gộp tài khoản
        raise AuthError(AuthErrorCode.AUTH_FAILED, "email đã gắn với tài khoản Google khác")
    is_new = user is None
    if user is None:
        user = User(google_sub=identity.sub, status=UserStatus.PENDING, created_at=now)
        if identity.email in bootstrap_admins:
            user.status, user.role, user.approved_at = UserStatus.ACTIVE, Role.ADMIN, now
        db.add(user)
    elif user.status == UserStatus.DISABLED:
        raise AuthError(AuthErrorCode.ACCOUNT_DISABLED)

    user.email = identity.email
    user.email_domain = email_domain(identity.email)
    user.name = identity.name
    user.avatar_url = identity.picture
    user.last_login_at = now
    db.commit()

    if user.status == UserStatus.ACTIVE:
        return user, LoginOutcome.ACTIVE
    # PENDING chưa gửi yêu cầu vai trò (bỏ dở form) → cho hoàn tất đăng ký lại
    if is_new or user.requested_role is None:
        return user, LoginOutcome.SIGNUP
    return user, LoginOutcome.PENDING


class SignupError(Exception):
    pass


# ADMIN chỉ được cấp bởi admin khác hoặc BOOTSTRAP_ADMIN_EMAILS, không tự yêu cầu
REQUESTABLE_ROLES = frozenset({Role.SALES, Role.PLANNER, Role.OPS_MANAGER})


def complete_signup(db: Session, user: User, requested_role: Role, note: str | None) -> User:
    if user.status != UserStatus.PENDING:
        raise SignupError("chỉ tài khoản PENDING mới gửi yêu cầu vai trò")
    if requested_role not in REQUESTABLE_ROLES:
        raise SignupError(f"không thể yêu cầu vai trò {requested_role}")
    user.requested_role, user.request_note = requested_role, (note or "").strip() or None
    db.commit()
    return user


def get_or_create_demo_user(db: Session, role: Role, now: datetime) -> User:
    """Tài khoản demo — chỉ gọi khi FEATURE_DEMO_LOGIN bật (ADR-0006: dự phòng khi pitch)."""
    sub = f"demo:{role.value}"
    user = db.scalar(select(User).where(User.google_sub == sub))
    if user is None:
        email = f"demo.{role.value.lower()}@demo.local"
        user = User(google_sub=sub, email=email, email_domain="demo.local", name=f"Demo {role.value}", created_at=now)
        user.status, user.role, user.approved_at = UserStatus.ACTIVE, role, now
        db.add(user)
    user.last_login_at = now
    db.commit()
    return user
