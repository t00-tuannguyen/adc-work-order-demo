"""Kiểm tra rủi ro đơn mới (ADC-005 T-036)

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "risk_checks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("work_order_id", sa.String(length=32), nullable=False),
        sa.Column("plan_version_id", sa.Integer(), nullable=True),
        sa.Column("level", sa.Enum("OK", "WARN", "BLOCK", name="risklevel", native_enum=False), nullable=False),
        sa.Column("reasons", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["plan_version_id"], ["plan_versions.id"]),
        sa.ForeignKeyConstraint(["work_order_id"], ["work_orders.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_risk_checks_work_order_id"), "risk_checks", ["work_order_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_risk_checks_work_order_id"), table_name="risk_checks")
    op.drop_table("risk_checks")
