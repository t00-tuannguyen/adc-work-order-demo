"""Quản lý người dùng (ADMIN) — ADC-008, specs/api-contracts.md §8."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.api.deps import require
from src.modules.identity import (
    Action,
    InvalidUserUpdateError,
    LastAdminError,
    Role,
    User,
    UserNotFoundError,
    UserStatus,
    list_users,
    update_user,
)
from src.modules.orchestration import AuditAction, record
from src.services.db import get_db, utcnow

router = APIRouter(prefix="/users", tags=["users"])


class UserOut(BaseModel):
    id: str
    name: str
    email: str
    avatar_url: str | None
    role: Role | None
    status: UserStatus
    requested_role: Role | None
    request_note: str | None
    created_at: datetime
    approved_by: str | None
    approved_at: datetime | None
    last_login_at: datetime | None

    model_config = {"from_attributes": True}


class UserPatch(BaseModel):
    role: Role | None = None
    status: UserStatus | None = None


@router.get("", response_model=list[UserOut])
def get_users(
    status: UserStatus | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require(Action.MANAGE_USERS)),
) -> list[User]:
    return list_users(db, status)


@router.patch("/{user_id}", response_model=UserOut)
def patch_user(
    user_id: str,
    patch: UserPatch,
    db: Session = Depends(get_db),
    admin: User = Depends(require(Action.MANAGE_USERS)),
) -> User:
    fields = patch.model_dump(include=patch.model_fields_set)
    if fields.get("status", ...) is None:
        raise HTTPException(status_code=422, detail="status không được null")
    try:
        now = utcnow()
        user, changes = update_user(db, admin, user_id, now=now, **fields)
    except UserNotFoundError as e:
        raise HTTPException(status_code=404, detail="Không tìm thấy người dùng") from e
    except InvalidUserUpdateError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except LastAdminError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    if changes:
        payload = {"user_id": user.id, "email": user.email, "changes": [vars(c) for c in changes]}
        record(db, admin.id, AuditAction.USER_UPDATED, payload, now=now)
    return user
