"""ADC-005 — API kiểm tra rủi ro đơn mới (specs/api-contracts.md §5)."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from src.modules.identity import Role
from src.modules.intake import Ticket, TicketSourceType, WorkOrder
from src.modules.orchestration import WorkOrderState
from src.modules.risk import RiskCheck
from src.modules.types import Priority

pytestmark = pytest.mark.asyncio


def t(hour: int, minute: int = 0, day: int = 1) -> datetime:
    """Giờ UTC ở tương lai — API dùng giờ thật làm `now`."""
    return datetime(2030, 1, day, hour, minute, tzinfo=UTC)


@pytest.fixture
def make_wo(db):
    def _make(priority=Priority.NORMAL, duration=180, arrival=t(2), ret=t(9), state=WorkOrderState.FEASIBILITY_CHECK):
        ticket = Ticket(source_type=TicketSourceType.MANUAL)
        db.add(ticket)
        db.flush()
        wo = WorkOrder(
            ticket_id=ticket.id,
            product_name="Bột ớt",
            priority=priority,
            expected_arrival=arrival,
            requested_return=ret,
            estimated_duration_min=duration,
            state=state,
        )
        db.add(wo)
        db.commit()
        return wo.id

    return _make


async def test_risk_check_ok_warn_block_without_changing_schedule(client, sign_in, make_wo, db):
    sign_in(Role.PLANNER)
    for _ in range(2):  # A 2–9, B 2–9
        await client.post(f"/api/work-orders/{make_wo(duration=420, ret=t(12))}/schedule")
    ok = (await client.post(f"/api/work-orders/{make_wo(ret=t(13))}/risk-check")).json()
    assert ok["level"] == "OK" and datetime.fromisoformat(ok["earliest_feasible_return"]) == t(12)

    warn = (await client.post(f"/api/work-orders/{make_wo(Priority.VIP, ret=t(6))}/risk-check")).json()
    assert warn["level"] == "WARN" and datetime.fromisoformat(warn["earliest_feasible_return"]) == t(5)
    assert any(r.startswith("Đẩy Bột ớt (Thường)") for r in warn["reasons"])

    blocked = make_wo(ret=t(10))
    block = (await client.post(f"/api/work-orders/{blocked}/risk-check")).json()
    assert block["level"] == "BLOCK" and datetime.fromisoformat(block["earliest_feasible_return"]) == t(12)
    assert block["reasons"][0].startswith("Không kịp giờ trả 17:00")  # giờ địa phương +07

    # Chỉ mô phỏng: lịch và trạng thái không đổi; mỗi lần kiểm tra (kể cả lúc xếp lịch) lưu 1 dòng risk_checks
    assert [v["id"] for v in (await client.get("/api/plan-versions")).json()] == [2, 1]
    assert db.get(WorkOrder, blocked).state == WorkOrderState.FEASIBILITY_CHECK
    assert [c.level for c in db.scalars(select(RiskCheck).order_by(RiskCheck.id))] == [
        "OK",
        "OK",
        "OK",
        "WARN",
        "BLOCK",
    ]


async def test_blocked_order_can_be_rechecked(client, sign_in, make_wo):
    sign_in(Role.PLANNER)
    wid = make_wo(duration=600, ret=t(9))
    assert (await client.post(f"/api/work-orders/{wid}/schedule")).status_code == 409
    r = await client.post(f"/api/work-orders/{wid}/risk-check")
    assert r.status_code == 200 and r.json()["level"] == "BLOCK"


async def test_risk_check_errors(client, sign_in, make_wo):
    sign_in(Role.SALES)  # mọi vai trò xem được rủi ro (banner khi tạo đơn)
    assert (await client.post("/api/work-orders/nope/risk-check")).status_code == 404
    assert (
        await client.post(f"/api/work-orders/{make_wo(state=WorkOrderState.SCHEDULED)}/risk-check")
    ).status_code == 409
    assert (await client.post(f"/api/work-orders/{make_wo(duration=None)}/risk-check")).status_code == 422
    assert (await client.post(f"/api/work-orders/{make_wo()}/risk-check")).status_code == 200


async def test_risk_check_requires_active_account(client, sign_in, make_wo):
    wid = make_wo()
    assert (await client.post(f"/api/work-orders/{wid}/risk-check")).status_code == 401
    sign_in(None)
    assert (await client.post(f"/api/work-orders/{wid}/risk-check")).status_code == 403
