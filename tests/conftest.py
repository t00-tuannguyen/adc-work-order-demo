from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.api.auth import get_google_client
from src.api.deps import SESSION_COOKIE
from src.main import app
from src.modules.estimation import load_config
from src.modules.identity import Role, User, UserStatus, create_session
from src.services.db import get_db, get_session_factory, init_db
from src.settings import Settings, get_settings
from tests.google_fake import FakeGoogle

FRONTEND = "http://app.test"


@pytest.fixture(autouse=True)
def _deterministic_estimate(monkeypatch):
    """Test luôn chạy mô hình thật dù .env bật FEATURE_RANDOM_ESTIMATE (demo)."""
    monkeypatch.setenv("FEATURE_RANDOM_ESTIMATE", "false")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def no_auto_schedule(monkeypatch):
    """Test cổng tiếp nhận (ADC-001) dừng ở FEASIBILITY_CHECK — tự xếp lịch có test riêng (test_auto_schedule)."""
    import src.agents.intake_pipeline as pipeline
    import src.api.intake_review as review

    noop = lambda *a, **kw: None  # noqa: E731
    monkeypatch.setattr(pipeline, "auto_schedule", noop)
    monkeypatch.setattr(review, "auto_schedule", noop)


@pytest.fixture
def db_factory():
    """SQLite in-memory dùng chung 1 kết nối cho cả test.

    Bật kiểm tra khóa ngoại như Postgres production — mặc định SQLite bỏ qua FK (BUG-001).
    """
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    event.listen(engine, "connect", lambda conn, _: conn.execute("PRAGMA foreign_keys=ON"))
    init_db(engine)
    yield sessionmaker(bind=engine, expire_on_commit=False)
    engine.dispose()


@pytest.fixture
def db(db_factory):
    with db_factory() as session:
        yield session


@pytest.fixture
def google():
    return FakeGoogle()


@pytest.fixture
def test_settings(tmp_path):
    return Settings(
        upload_dir=str(tmp_path / "uploads"),
        _env_file=None,
        app_env="test",
        allowed_email_domains="adc.test",
        bootstrap_admin_emails="admin@adc.test",
        session_cookie_secure=False,
        frontend_url=FRONTEND,
    )


@pytest_asyncio.fixture
async def client(db_factory, google, test_settings):
    """Async HTTP client, DB in-memory và Google giả."""

    def _db():
        with db_factory() as session:
            yield session

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_session_factory] = lambda: db_factory
    app.dependency_overrides[get_google_client] = lambda: google
    app.dependency_overrides[get_settings] = lambda: test_settings
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture
def sign_in(client, db):
    """Tạo user trực tiếp trong DB và gắn cookie phiên vào `client` (bỏ qua Google)."""

    def _sign_in(role: Role | None = Role.PLANNER, status: UserStatus = UserStatus.ACTIVE, email: str = "") -> User:
        email = email or f"{(role or 'none').lower()}.{status.lower()}@adc.test"
        user = User(google_sub=f"sub:{email}", email=email, email_domain="adc.test", role=role, status=status)
        db.add(user)
        db.commit()
        client.cookies.set(SESSION_COOKIE, create_session(db, user, now=datetime.now(UTC), ttl=timedelta(hours=12)))
        return user

    return _sign_in


@pytest.fixture
def config():
    """Cấu hình thật trong repo — ví dụ chuẩn của ADC-002 (spice, 10 kGy) phải cho 180 phút."""
    return load_config("src/config/throughput.yaml")


def at(hour: int, minute: int = 0, day: int = 1) -> datetime:
    return datetime(2026, 10, day, hour, minute, tzinfo=UTC)
