"""Plan version, danh sách thay đổi, slot lịch 2 line (ADC-003 T-028, ADC-006)

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "plan_versions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("parent_version_id", sa.Integer(), nullable=True),
        sa.Column(
            "trigger", sa.Enum("NEW_ORDER", "INCIDENT", "MANUAL", name="plantrigger", native_enum=False), nullable=False
        ),
        sa.Column(
            "status",
            sa.Enum(
                "PROPOSED",
                "PENDING_APPROVAL",
                "ACTIVE",
                "SUPERSEDED",
                "REJECTED",
                name="planversionstatus",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("requires_approval", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("approved_by", sa.String(length=32), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["approved_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["parent_version_id"], ["plan_versions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_plan_versions_status"), "plan_versions", ["status"], unique=False)

    op.create_table(
        "plan_changes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("plan_version_id", sa.Integer(), nullable=False),
        sa.Column("work_order_id", sa.String(length=32), nullable=False),
        sa.Column(
            "change_type",
            sa.Enum(
                "LINE_ASSIGNMENT",
                "RETURN_TIME_CHANGE",
                "INCIDENT_DELAY",
                "PRIORITY_OVERRIDE",
                "ACCEPT_DURING_WARNING",
                name="changetype",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("old_value", sa.JSON(), nullable=True),
        sa.Column("new_value", sa.JSON(), nullable=False),
        sa.Column("needs_approval", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["plan_version_id"], ["plan_versions.id"]),
        sa.ForeignKeyConstraint(["work_order_id"], ["work_orders.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_plan_changes_plan_version_id"), "plan_changes", ["plan_version_id"], unique=False)
    op.create_index(op.f("ix_plan_changes_work_order_id"), "plan_changes", ["work_order_id"], unique=False)

    op.create_table(
        "schedule_slots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("plan_version_id", sa.Integer(), nullable=False),
        sa.Column("work_order_id", sa.String(length=32), nullable=False),
        sa.Column("line", sa.Enum("A", "B", name="line", native_enum=False), nullable=False),
        sa.Column("start_at", sa.DateTime(), nullable=False),
        sa.Column("end_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["plan_version_id"], ["plan_versions.id"]),
        sa.ForeignKeyConstraint(["work_order_id"], ["work_orders.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_schedule_slots_plan_version_id_line_start_at",
        "schedule_slots",
        ["plan_version_id", "line", "start_at"],
        unique=False,
    )
    op.create_index(op.f("ix_schedule_slots_work_order_id"), "schedule_slots", ["work_order_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_schedule_slots_work_order_id"), table_name="schedule_slots")
    op.drop_index("ix_schedule_slots_plan_version_id_line_start_at", table_name="schedule_slots")
    op.drop_table("schedule_slots")
    op.drop_index(op.f("ix_plan_changes_work_order_id"), table_name="plan_changes")
    op.drop_index(op.f("ix_plan_changes_plan_version_id"), table_name="plan_changes")
    op.drop_table("plan_changes")
    op.drop_index(op.f("ix_plan_versions_status"), table_name="plan_versions")
    op.drop_table("plan_versions")
