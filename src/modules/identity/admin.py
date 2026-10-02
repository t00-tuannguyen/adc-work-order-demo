"""Quản lý người dùng & cấp vai trò (ADMIN) — ADC-008, specs/user-roles.md §2."""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.modules.identity.models import User
from src.modules.identity.permissions import Role, UserStatus
from src.modules.identity.sessions import revoke_all_sessions


class UserNotFoundError(Exception):
    pass


class InvalidUserUpdateError(Exception):
    pass


class LastAdminError(Exception):
    """Admin cuối cùng không được hạ quyền hoặc vô hiệu hóa (specs/user-roles.md §2)."""


_UNSET = object()


@dataclass(frozen=True)
class UserChange:
    field: str
    old: str | None
    new: str | None


def list_users(db: Session, status: UserStatus | None = None) -> list[User]:
    query = select(User).order_by(User.created_at)
    if status is not None:
        query = query.where(User.status == status)
    return list(db.scalars(query))


def _is_active_admin(role: Role | None, status: UserStatus) -> bool:
    return role == Role.ADMIN and status == UserStatus.ACTIVE


def update_user(
    db: Session, actor: User, user_id: str, *, now: datetime, role=_UNSET, status=_UNSET
) -> tuple[User, list[UserChange]]:
    """Chỉ đổi trường được truyền. Trả danh sách thay đổi để ghi audit."""
    user = db.get(User, user_id)
    if user is None:
        raise UserNotFoundError(user_id)
    new_role = user.role if role is _UNSET else role
    new_status = user.status if status is _UNSET else status

    if new_status == UserStatus.PENDING and user.status != UserStatus.PENDING:
        raise InvalidUserUpdateError("không thể đưa tài khoản về PENDING")
    if new_status == UserStatus.ACTIVE and new_role is None:
        raise InvalidUserUpdateError("tài khoản ACTIVE phải có vai trò")
    if _is_active_admin(user.role, user.status) and not _is_active_admin(new_role, new_status):
        active_admins = db.scalar(
            select(func.count()).select_from(User).where(User.role == Role.ADMIN, User.status == UserStatus.ACTIVE)
        )
        if active_admins <= 1:
            raise LastAdminError("phải còn ít nhất 1 ADMIN đang hoạt động")

    changes = [
        UserChange(field, old and str(old), new and str(new))
        for field, old, new in (("role", user.role, new_role), ("status", user.status, new_status))
        if old != new
    ]
    if user.status == UserStatus.PENDING and new_status == UserStatus.ACTIVE:
        user.approved_by, user.approved_at = actor.id, now
    user.role, user.status = new_role, new_status
    db.commit()
    if new_status == UserStatus.DISABLED:
        revoke_all_sessions(db, user.id, now=now)
    return user, changes
