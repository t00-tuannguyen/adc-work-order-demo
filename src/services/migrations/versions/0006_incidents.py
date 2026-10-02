"""Sự cố line, đơn bị ảnh hưởng, plan_versions.incident_id (ADC-004 T-031)

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "incidents",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("line", sa.Enum("A", "B", name="line", native_enum=False), nullable=False),
        sa.Column("start_at", sa.DateTime(), nullable=False),
        sa.Column("est_downtime_min", sa.Integer(), nullable=False),
        sa.Column("actual_end_at", sa.DateTime(), nullable=True),
        sa.Column("status", sa.Enum("OPEN", "RESOLVED", name="incidentstatus", native_enum=False), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("created_by", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_incidents_status"), "incidents", ["status"], unique=False)

    op.create_table(
        "incident_affected_orders",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("incident_id", sa.Integer(), nullable=False),
        sa.Column("work_order_id", sa.String(length=32), nullable=False),
        sa.Column("old_slot_id", sa.Integer(), nullable=False),
        sa.Column("new_slot_id", sa.Integer(), nullable=True),
        sa.Column(
            "outcome",
            sa.Enum("MOVED_ALT_LINE", "DELAYED", "UNCHANGED", name="affectedoutcome", native_enum=False),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.id"]),
        sa.ForeignKeyConstraint(["new_slot_id"], ["schedule_slots.id"]),
        sa.ForeignKeyConstraint(["old_slot_id"], ["schedule_slots.id"]),
        sa.ForeignKeyConstraint(["work_order_id"], ["work_orders.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_incident_affected_orders_incident_id"), "incident_affected_orders", ["incident_id"], unique=False
    )
    op.create_index(
        op.f("ix_incident_affected_orders_work_order_id"), "incident_affected_orders", ["work_order_id"], unique=False
    )

    with op.batch_alter_table("plan_versions") as batch_op:
        batch_op.add_column(sa.Column("incident_id", sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f("ix_plan_versions_incident_id"), ["incident_id"], unique=False)
        batch_op.create_foreign_key("fk_plan_versions_incident_id_incidents", "incidents", ["incident_id"], ["id"])


def downgrade() -> None:
    with op.batch_alter_table("plan_versions") as batch_op:
        batch_op.drop_constraint("fk_plan_versions_incident_id_incidents", type_="foreignkey")
        batch_op.drop_index(batch_op.f("ix_plan_versions_incident_id"))
        batch_op.drop_column("incident_id")
    op.drop_index(op.f("ix_incident_affected_orders_work_order_id"), table_name="incident_affected_orders")
    op.drop_index(op.f("ix_incident_affected_orders_incident_id"), table_name="incident_affected_orders")
    op.drop_table("incident_affected_orders")
    op.drop_index(op.f("ix_incidents_status"), table_name="incidents")
    op.drop_table("incidents")
