"""T-017 — Alembic: migration khớp model, DB cũ tạo bằng create_all được nâng cấp an toàn.

T-013 — chạy lại trên PostgreSQL (Neon khi deploy, ADR-0012) khi có `TEST_POSTGRES_URL` (job CI `migrations-postgres`).
"""

import os

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text

from src.services.db import Base, load_models, make_engine, migrate_db, normalize_db_url


def _engine(tmp_path):
    return create_engine(f"sqlite:///{tmp_path / 'app.db'}")


def _head(engine) -> str:
    with engine.connect() as c:
        return c.execute(text("SELECT version_num FROM alembic_version")).scalar_one()


def test_migrations_match_models(tmp_path):
    engine = _engine(tmp_path)
    migrate_db(engine)
    load_models()
    with engine.connect() as c:
        diff = compare_metadata(MigrationContext.configure(c, opts={"compare_type": True}), Base.metadata)
    assert diff == []
    assert _head(engine) == "0009"


def test_migrate_is_idempotent(tmp_path):
    engine = _engine(tmp_path)
    migrate_db(engine)
    migrate_db(engine)
    assert _head(engine) == "0009"


def test_legacy_create_all_db_is_stamped_then_upgraded(tmp_path):
    """DB dev tạo bằng create_all ở T-049…T-053 (chỉ có bảng identity + audit) không bị tạo lại bảng."""
    engine = _engine(tmp_path)
    load_models()
    legacy = [Base.metadata.tables[t] for t in ("users", "oauth_login_attempts", "sessions", "audit_log")]
    Base.metadata.create_all(engine, tables=legacy)
    with engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO users (id, google_sub, email, name, email_domain, status, created_at) "
                "VALUES ('u1', 's', 'a@adc.test', '', 'adc.test', 'ACTIVE', '2026-10-01 08:00:00')"
            )
        )
    migrate_db(engine)
    assert "work_orders" in inspect(engine).get_table_names()
    assert _head(engine) == "0009"
    with engine.connect() as c:
        assert c.execute(text("SELECT count(*) FROM users")).scalar_one() == 1


@pytest.fixture
def pg_engine():
    url = os.environ.get("TEST_POSTGRES_URL")
    if not url:
        pytest.skip("cần TEST_POSTGRES_URL (PostgreSQL trống)")
    engine = make_engine(url)
    with engine.begin() as c:
        c.execute(text("DROP SCHEMA public CASCADE"))
        c.execute(text("CREATE SCHEMA public"))
    yield engine
    engine.dispose()


def test_migrations_match_models_on_postgres(pg_engine):
    migrate_db(pg_engine)
    migrate_db(pg_engine)  # khởi động lại app không lỗi
    load_models()
    with pg_engine.connect() as c:
        diff = compare_metadata(MigrationContext.configure(c, opts={"compare_type": True}), Base.metadata)
    assert diff == []
    assert _head(pg_engine) == "0009"


def test_postgres_url_uses_psycopg3_driver():
    assert normalize_db_url("postgres://u:p@h/db?sslmode=require") == "postgresql+psycopg://u:p@h/db?sslmode=require"
    assert normalize_db_url("postgresql://u:p@h/db") == "postgresql+psycopg://u:p@h/db"
    assert normalize_db_url("postgresql+psycopg://u:p@h/db") == "postgresql+psycopg://u:p@h/db"
    assert normalize_db_url("sqlite:///./data/app.db") == "sqlite:///./data/app.db"
