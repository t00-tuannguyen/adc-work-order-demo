"""work_orders: estimated_duration_min, estimate_breakdown, config_version (ADC-002, T-025)

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("work_orders") as batch_op:
        batch_op.add_column(sa.Column("estimated_duration_min", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("estimate_breakdown", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("config_version", sa.String(length=32), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("work_orders") as batch_op:
        batch_op.drop_column("config_version")
        batch_op.drop_column("estimate_breakdown")
        batch_op.drop_column("estimated_duration_min")
