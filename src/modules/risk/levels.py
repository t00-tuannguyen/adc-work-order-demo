"""Enum của Risk context — tách riêng để Orchestration import được mà không vòng (ADR-0003)."""

from enum import StrEnum


class RiskLevel(StrEnum):
    OK = "OK"
    WARN = "WARN"  # kịp giờ trả nhưng đẩy đơn khác — nhận được nhưng cần duyệt (BR-07)
    BLOCK = "BLOCK"  # không kịp giờ trả dù xếp sớm nhất — Quản lý override kèm lý do


class EscalationStatus(StrEnum):
    """`OPEN → DRAFTED → APPROVED → CLOSED` (specs/domains.md §5); bảng chuyển ở orchestration.state_machine."""

    OPEN = "OPEN"
    DRAFTED = "DRAFTED"
    APPROVED = "APPROVED"
    CLOSED = "CLOSED"
