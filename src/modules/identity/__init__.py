"""Identity context — ADC-008, specs/user-roles.md. Module khác chỉ import từ đây."""

from src.modules.identity.admin import (
    InvalidUserUpdateError,
    LastAdminError,
    UserChange,
    UserNotFoundError,
    list_users,
    update_user,
)
from src.modules.identity.models import OAuthLoginAttempt, User, UserSession
from src.modules.identity.oidc import (
    AuthError,
    AuthErrorCode,
    GoogleIdentity,
    parse_list,
    safe_next_path,
    verify_id_token,
)
from src.modules.identity.permissions import PERMISSIONS, Action, Role, UserStatus, is_allowed
from src.modules.identity.service import (
    REQUESTABLE_ROLES,
    LoginOutcome,
    LoginStart,
    SignupError,
    complete_signup,
    consume_login_attempt,
    get_or_create_demo_user,
    resolve_user,
    start_login,
)
from src.modules.identity.sessions import create_session, get_session_user, revoke_all_sessions, revoke_session

__all__ = [
    "update_user",
    "list_users",
    "UserNotFoundError",
    "UserChange",
    "LastAdminError",
    "InvalidUserUpdateError",
    "PERMISSIONS",
    "REQUESTABLE_ROLES",
    "Action",
    "AuthError",
    "AuthErrorCode",
    "GoogleIdentity",
    "LoginOutcome",
    "LoginStart",
    "OAuthLoginAttempt",
    "Role",
    "SignupError",
    "User",
    "UserSession",
    "UserStatus",
    "complete_signup",
    "consume_login_attempt",
    "create_session",
    "get_or_create_demo_user",
    "get_session_user",
    "is_allowed",
    "parse_list",
    "resolve_user",
    "revoke_all_sessions",
    "revoke_session",
    "safe_next_path",
    "start_login",
    "verify_id_token",
]
