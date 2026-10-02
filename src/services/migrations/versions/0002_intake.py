"""Intake: ticket file, ingest job, ticket, work order, trường trích xuất, yêu cầu bổ sung, cảnh báo (T-017)

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ticket_files",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("storage_path", sa.Text(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("has_text_layer", sa.Boolean(), nullable=True),
        sa.Column("ocr_used", sa.Boolean(), nullable=False),
        sa.Column("channel", sa.String(length=32), nullable=True),
        sa.Column("received_at", sa.DateTime(), nullable=True),
        sa.Column("uploaded_by", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(
            ["uploaded_by"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_ticket_files_sha256"), "ticket_files", ["sha256"], unique=False)

    op.create_table(
        "ingest_jobs",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("file_id", sa.String(length=32), nullable=False),
        sa.Column(
            "status",
            sa.Enum("QUEUED", "RUNNING", "SUCCEEDED", "FAILED", name="ingestjobstatus", native_enum=False),
            nullable=False,
        ),
        sa.Column(
            "step",
            sa.Enum(
                "UPLOADED", "READING", "DETECTING", "EXTRACTING", "DONE", "FAILED", name="ingeststep", native_enum=False
            ),
            nullable=False,
        ),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["file_id"],
            ["ticket_files.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_ingest_jobs_status"), "ingest_jobs", ["status"], unique=False)

    op.create_table(
        "tickets",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("file_id", sa.String(length=32), nullable=True),
        sa.Column(
            "source_type", sa.Enum("PDF", "TEXT", "MANUAL", name="ticketsourcetype", native_enum=False), nullable=False
        ),
        sa.Column("raw_text", sa.Text(), nullable=True),
        sa.Column("page_from", sa.Integer(), nullable=True),
        sa.Column("page_to", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["file_id"],
            ["ticket_files.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "work_orders",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("ticket_id", sa.String(length=32), nullable=False),
        sa.Column(
            "review_status",
            sa.Enum(
                "AUTO_ACCEPTED",
                "ACCEPTED_WITH_WARNINGS",
                "NEEDS_REVIEW",
                "NEEDS_CLARIFICATION",
                name="reviewstatus",
                native_enum=False,
            ),
            nullable=True,
        ),
        sa.Column("product_name", sa.Text(), nullable=True),
        sa.Column("product_group", sa.String(length=64), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=True),
        sa.Column("pkg_length_cm", sa.Float(), nullable=True),
        sa.Column("pkg_width_cm", sa.Float(), nullable=True),
        sa.Column("pkg_height_cm", sa.Float(), nullable=True),
        sa.Column("pkg_weight_kg", sa.Float(), nullable=True),
        sa.Column("required_dose_kgy", sa.Float(), nullable=True),
        sa.Column("priority", sa.Enum("NORMAL", "URGENT", "VIP", name="priority", native_enum=False), nullable=True),
        sa.Column("expected_arrival", sa.DateTime(), nullable=True),
        sa.Column("requested_return", sa.DateTime(), nullable=True),
        sa.Column(
            "state",
            sa.Enum(
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
                name="workorderstate",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["ticket_id"],
            ["tickets.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ticket_id"),
    )
    op.create_index(op.f("ix_work_orders_requested_return"), "work_orders", ["requested_return"], unique=False)
    op.create_index(op.f("ix_work_orders_review_status"), "work_orders", ["review_status"], unique=False)
    op.create_index(op.f("ix_work_orders_state"), "work_orders", ["state"], unique=False)

    op.create_table(
        "clarification_requests",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("work_order_id", sa.String(length=32), nullable=False),
        sa.Column("field", sa.String(length=64), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("status", sa.Enum("OPEN", "ANSWERED", name="clarificationstatus", native_enum=False), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("answered_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["work_order_id"],
            ["work_orders.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_clarification_requests_work_order_id"), "clarification_requests", ["work_order_id"], unique=False
    )

    op.create_table(
        "field_extractions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("work_order_id", sa.String(length=32), nullable=False),
        sa.Column("field", sa.String(length=64), nullable=False),
        sa.Column("value", sa.JSON(), nullable=True),
        sa.Column(
            "source_kind",
            sa.Enum(
                "VERBATIM",
                "INFERRED",
                "CONVERTED",
                "OCR_LOW",
                "MANUAL",
                "DEFAULT",
                name="sourcekind",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("page", sa.Integer(), nullable=True),
        sa.Column("bbox", sa.JSON(), nullable=True),
        sa.Column("snippet", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(
            ["work_order_id"],
            ["work_orders.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_field_extractions_work_order_id_field", "field_extractions", ["work_order_id", "field"], unique=False
    )

    op.create_table(
        "intake_warnings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("work_order_id", sa.String(length=32), nullable=False),
        sa.Column("field", sa.String(length=64), nullable=True),
        sa.Column(
            "code",
            sa.Enum(
                "LOW_CONFIDENCE",
                "BOUNDARY_UNCERTAIN",
                "AMBIGUOUS_OCR",
                "INFERRED_VALUE",
                "DEFAULT_VALUE",
                "POSSIBLE_DUPLICATE",
                name="flagcode",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("status", sa.Enum("OPEN", "ACKNOWLEDGED", name="warningstatus", native_enum=False), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("acknowledged_by", sa.String(length=32), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["acknowledged_by"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["work_order_id"],
            ["work_orders.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_intake_warnings_status"), "intake_warnings", ["status"], unique=False)
    op.create_index(op.f("ix_intake_warnings_work_order_id"), "intake_warnings", ["work_order_id"], unique=False)


def downgrade() -> None:
    op.drop_table("intake_warnings")
    op.drop_table("field_extractions")
    op.drop_table("clarification_requests")
    op.drop_table("work_orders")
    op.drop_table("tickets")
    op.drop_table("ingest_jobs")
    op.drop_table("ticket_files")
