"""Kiểu dùng chung giữa các context (Ubiquitous Language — specs/domains.md §2)."""

from enum import StrEnum


class Line(StrEnum):
    A = "A"
    B = "B"


class Priority(StrEnum):
    NORMAL = "NORMAL"  # Thường
    URGENT = "URGENT"  # Khẩn
    VIP = "VIP"


# BR-05: VIP → Khẩn → Thường
PRIORITY_RANK: dict[Priority, int] = {Priority.VIP: 0, Priority.URGENT: 1, Priority.NORMAL: 2}

PRIORITY_LABEL: dict[Priority, str] = {Priority.VIP: "VIP", Priority.URGENT: "Khẩn", Priority.NORMAL: "Thường"}
