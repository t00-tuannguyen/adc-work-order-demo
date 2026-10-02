"""Môi trường Alembic — dùng chung engine/metadata với src/services/db.py."""

from alembic import context

from src.services.db import Base, get_engine, load_models

load_models()
target_metadata = Base.metadata


def run_migrations_online() -> None:
    # migrate_db() truyền sẵn connection; chạy CLI `alembic ...` thì lấy engine từ DATABASE_URL
    connection = context.config.attributes.get("connection")
    if connection is not None:
        _run(connection)
        return
    with get_engine().connect() as connection:
        _run(connection)


def _run(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=connection.dialect.name == "sqlite",  # SQLite không ALTER được cột
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    raise RuntimeError("Chỉ hỗ trợ chạy online (có kết nối DB)")
run_migrations_online()
