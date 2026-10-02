"""Xác thực & RBAC cho mọi router — specs/api-contracts.md §Quy ước chung: chưa đăng nhập 401, chưa được cấp quyền 403."""

from collections.abc import Callable
from datetime import timedelta

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from src.modules.identity import Action, User, UserStatus, get_session_user, is_allowed
from src.services.db import get_db, utcnow
from src.settings import Settings, get_settings

SESSION_COOKIE = "adc_session"


def current_user(request: Request, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> User:
    """Mọi user đã đăng nhập, kể cả PENDING (cần cho /api/me và hoàn tất đăng ký)."""
    user = get_session_user(
        db, request.cookies.get(SESSION_COOKIE), now=utcnow(), ttl=timedelta(hours=settings.session_ttl_hours)
    )
    if user is None:
        raise HTTPException(status_code=401, detail="Chưa đăng nhập hoặc phiên đã hết hạn")
    if user.status == UserStatus.DISABLED:
        raise HTTPException(status_code=403, detail="Tài khoản đã bị vô hiệu hóa")
    return user


def require(action: Action) -> Callable[..., User]:
    """Dependency cho API dữ liệu: user ACTIVE có vai trò được phép `action` (specs/user-roles.md §2)."""

    def dependency(user: User = Depends(current_user)) -> User:
        if not is_allowed(user.role, user.status, action):
            raise HTTPException(status_code=403, detail=f"Không có quyền {action.value}")
        return user

    return dependency
