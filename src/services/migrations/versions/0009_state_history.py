"""Lịch sử trạng thái work order (ADC-006 T-041)

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_STATES = (
    "DRAFT",
    "FEASIBILITY_CHECK",
    "PENDING_APPROVAL",
    "SCHEDULED",
    "WAITING_ARRIVAL",
    "READY_FOR_IRRADIATION",
    "IN_IRRADIATION",
    "COMPLETED_IRRADIATION",
    "READY_FOR_RETURN",
    "RETURNED",
    "CLOSED",
    "LINE_INCIDENT",
    "SLA_RISK",
    "RESCHEDULE_REQUIRED",
    "ESCALATED_TO_BUSINESS",
    "BLOCK_NEW_ORDER",
)


def upgrade() -> None:
    op.create_table(
        "state_history",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("work_order_id", sa.String(length=32), nullable=False),
        sa.Column("from_state", sa.Enum(*_STATES, name="workorderstate", native_enum=False), nullable=True),
        sa.Column("to_state", sa.Enum(*_STATES, name="workorderstate", native_enum=False), nullable=False),
        sa.Column(
            "actor_type", sa.Enum("USER", "AGENT", "SYSTEM", name="actortype", native_enum=False), nullable=False
        ),
        sa.Column("actor_id", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("plan_version_id", sa.Integer(), nullable=True),
        sa.Column("at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["plan_version_id"], ["plan_versions.id"]),
        sa.ForeignKeyConstraint(["work_order_id"], ["work_orders.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_state_history_work_order_id_at", "state_history", ["work_order_id", "at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_state_history_work_order_id_at", table_name="state_history")
    op.drop_table("state_history")
