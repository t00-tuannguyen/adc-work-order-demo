"""Hạ tầng DB dùng chung — SQLAlchemy 2 + Alembic (ADR-0002).

Khởi động app chạy `migrate_db()` (alembic upgrade head); test dùng `init_db()` (create_all) cho nhanh.
Migration nằm ở `src/services/migrations/versions/`; tạo mới: `alembic revision --autogenerate -m "..."`.
"""

from collections.abc import Iterator
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path

from sqlalchemy import DateTime, Engine, create_engine, inspect
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.types import TypeDecorator

from src.settings import get_settings


class UTCDateTime(TypeDecorator):
    """Luôn lưu UTC, luôn trả datetime có tz — SQLite bỏ tz nên phải tự gắn lại."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("datetime phải có tzinfo")
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect) -> datetime | None:
        return value.replace(tzinfo=UTC) if value is not None else None


class Base(DeclarativeBase):
    pass


def utcnow() -> datetime:
    return datetime.now(UTC)


def normalize_db_url(url: str) -> str:
    """Neon/Render đưa `postgres://` hoặc `postgresql://` → chỉ rõ driver psycopg 3 (requirements.txt), không phụ thuộc
    driver mặc định của từng bản SQLAlchemy (2.0: psycopg2, 2.1: psycopg)."""
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url.removeprefix(prefix)
    return url


def make_engine(url: str) -> Engine:
    url = normalize_db_url(url)
    if url.startswith("sqlite:///") and not url.startswith("sqlite:///:memory:"):
        Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, connect_args=connect_args)


@lru_cache
def get_engine() -> Engine:
    return make_engine(get_settings().database_url)


@lru_cache
def _session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


def get_session_factory() -> sessionmaker[Session]:
    """FastAPI dependency cho việc chạy nền (BackgroundTasks) — cần session riêng, không dùng session của request."""
    return _session_factory()


def get_db() -> Iterator[Session]:
    """FastAPI dependency — mỗi request một session; test override để dùng DB in-memory."""
    with _session_factory()() as db:
        yield db


MIGRATIONS_DIR = Path(__file__).parent / "migrations"
# Revision tương ứng với các bảng do create_all tạo trước khi có Alembic (T-049 → T-053)
BASELINE_REVISION = "0001"


def load_models() -> None:
    """Import để model đăng ký vào Base.metadata (create_all / autogenerate)."""
    import src.modules.identity.models  # noqa: F401
    import src.modules.intake.models  # noqa: F401
    import src.modules.orchestration.audit  # noqa: F401
    import src.modules.orchestration.history  # noqa: F401
    import src.modules.orchestration.plan_versions  # noqa: F401
    import src.modules.risk.models  # noqa: F401
    import src.modules.scheduling.models  # noqa: F401


def init_db(engine: Engine | None = None) -> None:
    load_models()
    Base.metadata.create_all(engine or get_engine())


def migrate_db(engine: Engine | None = None) -> None:
    """alembic upgrade head. DB cũ tạo bằng create_all (chưa có alembic_version) → stamp baseline trước."""
    from alembic import command
    from alembic.config import Config

    engine = engine or get_engine()
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    with engine.begin() as connection:
        cfg.attributes["connection"] = connection
        tables = set(inspect(connection).get_table_names())
        if "users" in tables and "alembic_version" not in tables:
            command.stamp(cfg, BASELINE_REVISION)
        command.upgrade(cfg, "head")
