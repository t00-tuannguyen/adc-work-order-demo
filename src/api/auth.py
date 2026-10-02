"""Auth API — ADC-008, specs/api-contracts.md §8. Router `/auth/*` gắn ở gốc (không qua `/api`)."""

from datetime import timedelta
from functools import lru_cache
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.api.deps import SESSION_COOKIE, current_user
from src.modules.identity import (
    AuthError,
    AuthErrorCode,
    LoginOutcome,
    Role,
    SignupError,
    User,
    UserStatus,
    complete_signup,
    consume_login_attempt,
    create_session,
    get_or_create_demo_user,
    parse_list,
    resolve_user,
    revoke_all_sessions,
    revoke_session,
    start_login,
    verify_id_token,
)
from src.modules.orchestration import AuditAction, record
from src.services.db import get_db, utcnow
from src.services.google_oauth import GoogleOAuthClient, GoogleOAuthError
from src.settings import Settings, get_settings

STATE_COOKIE = "adc_oauth_state"
STATE_COOKIE_PATH = "/auth/google"

auth_router = APIRouter(prefix="/auth", tags=["auth"])
me_router = APIRouter(tags=["auth"])  # gắn dưới /api


@lru_cache
def get_google_client() -> GoogleOAuthClient:
    s = get_settings()
    return GoogleOAuthClient(s.google_client_id, s.google_client_secret, s.oauth_redirect_uri)


def _frontend(settings: Settings, path: str, **query: str) -> RedirectResponse:
    url = settings.frontend_url.rstrip("/") + path
    if query:
        url += "?" + urlencode(query)
    return RedirectResponse(url, status_code=302)


def _login_error(settings: Settings, code: AuthErrorCode) -> RedirectResponse:
    resp = _frontend(settings, "/login", error=code.value)
    resp.delete_cookie(STATE_COOKIE, path=STATE_COOKIE_PATH)
    return resp


@auth_router.get("/google/start")
def google_start(
    next: str | None = None,
    db: Session = Depends(get_db),
    google: GoogleOAuthClient = Depends(get_google_client),
    settings: Settings = Depends(get_settings),
) -> RedirectResponse:
    start = start_login(db, next, utcnow())
    resp = RedirectResponse(
        google.authorization_url(state=start.state, nonce=start.nonce, code_challenge=start.code_challenge),
        status_code=302,
    )
    # Gắn state với trình duyệt này; mở tab khác sẽ ghi đè → tab cũ nhận STATE_MISMATCH và thử lại
    resp.set_cookie(
        STATE_COOKIE,
        start.state,
        max_age=settings.oauth_state_ttl_min * 60,
        path=STATE_COOKIE_PATH,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
    )
    return resp


def _verify(google: GoogleOAuthClient, id_token: str, nonce: str):
    try:
        return verify_id_token(id_token, google.jwks(), client_id=google.client_id, nonce=nonce)
    except AuthError:
        # Google có thể vừa xoay khóa → tải lại JWKS một lần
        return verify_id_token(id_token, google.jwks(force_refresh=True), client_id=google.client_id, nonce=nonce)


@auth_router.get("/google/callback")
def google_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
    google: GoogleOAuthClient = Depends(get_google_client),
    settings: Settings = Depends(get_settings),
) -> RedirectResponse:
    if error:  # vd access_denied khi người dùng bấm Hủy trên trang Google
        return _login_error(settings, AuthErrorCode.CANCELLED)
    now = utcnow()
    try:
        attempt = consume_login_attempt(
            db, state, request.cookies.get(STATE_COOKIE), now, timedelta(minutes=settings.oauth_state_ttl_min)
        )
        if not code:
            raise AuthError(AuthErrorCode.AUTH_FAILED, "thiếu code")
        try:
            id_token = google.exchange_code(code, attempt.code_verifier)
            identity = _verify(google, id_token, attempt.nonce)
        except GoogleOAuthError as e:
            raise AuthError(AuthErrorCode.AUTH_FAILED, str(e)) from e
        user, outcome = resolve_user(
            db,
            identity,
            allowed_domains=parse_list(settings.allowed_email_domains),
            bootstrap_admins=parse_list(settings.bootstrap_admin_emails),
            now=now,
        )
    except AuthError as e:
        return _login_error(settings, e.code)

    if outcome == LoginOutcome.SIGNUP:
        resp = _frontend(settings, "/signup/complete")
    elif outcome == LoginOutcome.PENDING:
        resp = _frontend(settings, "/pending")
    else:
        resp = _frontend(settings, attempt.next_path or "/")
    resp.delete_cookie(STATE_COOKIE, path=STATE_COOKIE_PATH)
    # PENDING cũng có phiên: cần để gửi yêu cầu vai trò và xem /api/me; API dữ liệu vẫn 403
    _start_session(resp, request, db, user, settings)
    record(db, user.id, AuditAction.LOGIN, {"outcome": outcome.value}, now=now)
    return resp


def _start_session(resp: Response, request: Request, db: Session, user: User, settings: Settings) -> None:
    token = create_session(
        db,
        user,
        now=utcnow(),
        ttl=timedelta(hours=settings.session_ttl_hours),
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    # Không đặt max_age: hạn thật do server giữ (trượt theo SESSION_TTL_HOURS)
    resp.set_cookie(SESSION_COOKIE, token, httponly=True, secure=settings.session_cookie_secure, samesite="lax")


def _clear_session_cookie(resp: Response, settings: Settings) -> None:
    resp.delete_cookie(SESSION_COOKIE, httponly=True, secure=settings.session_cookie_secure, samesite="lax")


@auth_router.post("/logout", status_code=204)
def logout(request: Request, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> Response:
    """Chỉ kết thúc phiên trên thiết bị này; không đăng xuất tài khoản Google. Luôn 204 (idempotent)."""
    now = utcnow()
    user_id = revoke_session(db, request.cookies.get(SESSION_COOKIE), now=now)
    if user_id:
        record(db, user_id, AuditAction.LOGOUT, now=now)
    resp = Response(status_code=204)
    _clear_session_cookie(resp, settings)
    return resp


@auth_router.post("/logout-all", status_code=204)
def logout_all(
    user: User = Depends(current_user), db: Session = Depends(get_db), settings: Settings = Depends(get_settings)
) -> Response:
    now = utcnow()
    revoke_all_sessions(db, user.id, now=now)
    record(db, user.id, AuditAction.LOGOUT_ALL, now=now)
    resp = Response(status_code=204)
    _clear_session_cookie(resp, settings)
    return resp


class DemoLoginRequest(BaseModel):
    role: Role


@auth_router.post("/demo-login", status_code=204)
def demo_login(
    req: DemoLoginRequest,
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Response:
    """Dự phòng khi pitch (ADR-0006). Tắt → 404 như thể không tồn tại."""
    if not settings.feature_demo_login:
        raise HTTPException(status_code=404)
    resp = Response(status_code=204)
    now = utcnow()
    user = get_or_create_demo_user(db, req.role, now)
    _start_session(resp, request, db, user, settings)
    record(db, user.id, AuditAction.DEMO_LOGIN, {"role": req.role.value}, now=now)
    return resp


class MeResponse(BaseModel):
    id: str
    name: str
    email: str
    avatar_url: str | None
    role: Role | None
    status: UserStatus
    requested_role: Role | None


def to_me(user: User) -> MeResponse:
    return MeResponse(
        id=user.id,
        name=user.name,
        email=user.email,
        avatar_url=user.avatar_url,
        role=user.role,
        status=user.status,
        requested_role=user.requested_role,
    )


@me_router.get("/me", response_model=MeResponse)
def me(user: User = Depends(current_user)) -> MeResponse:
    return to_me(user)


class SignupRequest(BaseModel):
    requested_role: Role
    note: str | None = None


@me_router.post("/signup/complete", response_model=MeResponse)
def signup_complete(
    req: SignupRequest, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> MeResponse:
    try:
        complete_signup(db, user, req.requested_role, req.note)
    except SignupError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    record(
        db,
        user.id,
        AuditAction.SIGNUP_REQUESTED,
        {"requested_role": user.requested_role.value, "note": user.request_note},
        now=utcnow(),
    )
    return to_me(user)
