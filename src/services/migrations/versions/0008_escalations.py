"""Escalation cho đơn trễ giờ trả (ADC-005 T-037)

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "escalations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("work_order_id", sa.String(length=32), nullable=False),
        sa.Column("incident_id", sa.Integer(), nullable=True),
        sa.Column("delay_min", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("OPEN", "DRAFTED", "APPROVED", "CLOSED", name="escalationstatus", native_enum=False),
            nullable=False,
        ),
        sa.Column("draft_message", sa.Text(), nullable=True),
        sa.Column("final_message", sa.Text(), nullable=True),
        sa.Column("approved_by", sa.String(length=32), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["approved_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.id"]),
        sa.ForeignKeyConstraint(["work_order_id"], ["work_orders.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_escalations_status"), "escalations", ["status"], unique=False)
    op.create_index(op.f("ix_escalations_work_order_id"), "escalations", ["work_order_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_escalations_work_order_id"), table_name="escalations")
    op.drop_index(op.f("ix_escalations_status"), table_name="escalations")
    op.drop_table("escalations")
