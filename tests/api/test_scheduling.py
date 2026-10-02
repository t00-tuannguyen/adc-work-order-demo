"""ADC-003 T-028 — API lịch, Kanban, chuyển trạng thái vận hành, plan version (specs/api-contracts.md §3)."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from src.modules.identity import Role
from src.modules.intake import Ticket, TicketSourceType, WorkOrder
from src.modules.orchestration import AuditLog, WorkOrderState
from src.modules.types import Priority

pytestmark = pytest.mark.asyncio


def t(hour: int, minute: int = 0, day: int = 1) -> datetime:
    """Giờ UTC ở tương lai — API dùng giờ thật làm `now`."""
    return datetime(2030, 1, day, hour, minute, tzinfo=UTC)


@pytest.fixture
def make_wo(db):
    def _make(
        duration=180,
        arrival=t(2),
        ret=t(9),
        state=WorkOrderState.FEASIBILITY_CHECK,
        name="Bột ớt",
        priority=Priority.VIP,
    ) -> str:
        ticket = Ticket(source_type=TicketSourceType.MANUAL)
        db.add(ticket)
        db.flush()
        wo = WorkOrder(
            ticket_id=ticket.id,
            product_name=name,
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


async def test_schedule_normal_order(client, sign_in, make_wo):
    sign_in(Role.PLANNER)
    wid = make_wo()
    r = await client.post(f"/api/work-orders/{wid}/schedule")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["line"] == "A" and body["sla_ok"] is True and body["plan_version"] == 1
    assert body["plan_status"] == "ACTIVE"
    assert datetime.fromisoformat(body["start"]) == t(2)
    # Lý do theo giờ địa phương +07:00
    assert body["reason"] == "Line A 09:00–12:00. Các line xong cùng lúc → chọn Line A. Kịp giờ trả 16:00."


async def test_normal_order_after_day_shift_moves_to_next_morning(client, sign_in, make_wo):
    """T-054: 20:00 giờ +07 (13:00 UTC), 3 giờ → vượt 22:00 → 06:00 hôm sau; đơn VIP cùng giờ chạy ca đêm."""
    sign_in(Role.PLANNER)
    normal = make_wo(arrival=t(13), ret=t(4, day=2), priority=Priority.NORMAL)
    body = (await client.post(f"/api/work-orders/{normal}/schedule")).json()
    assert datetime.fromisoformat(body["start"]) == t(23)  # 06:00 ngày 02/01 giờ +07
    assert "đơn Thường chỉ chạy ca ngày 06:00–22:00 → bắt đầu 06:00 02/01" in body["reason"]

    vip = make_wo(arrival=t(13), ret=t(4, day=2), priority=Priority.VIP)
    body = (await client.post(f"/api/work-orders/{vip}/schedule")).json()
    assert (body["line"], datetime.fromisoformat(body["start"])) == ("A", t(13))


async def test_normal_order_longer_than_day_shift_is_422(client, sign_in, make_wo):
    sign_in(Role.PLANNER)
    wid = make_wo(duration=17 * 60, ret=t(23, day=2), priority=Priority.NORMAL)
    r = await client.post(f"/api/work-orders/{wid}/schedule")
    assert r.status_code == 422 and "ca ngày" in r.json()["detail"]


async def test_schedule_capacity_conflict_then_view(client, sign_in, make_wo):
    sign_in(Role.PLANNER)
    a = make_wo(duration=420, arrival=t(1), name="Hạt tiêu")
    b = make_wo(duration=90, arrival=t(2), name="Quế")
    assert (await client.post(f"/api/work-orders/{a}/schedule")).json()["line"] == "A"
    assert (await client.post(f"/api/work-orders/{b}/schedule")).json()["line"] == "B"

    view = (await client.get("/api/schedule?version=current")).json()
    assert view["plan_version"]["id"] == 2 and view["plan_version"]["status"] == "ACTIVE"
    assert view["plan_version"]["parent_version_id"] == 1 and view["plan_version"]["slot_count"] == 2
    assert [s["product_name"] for s in view["lines"]["A"]] == ["Hạt tiêu"]
    slot_b = view["lines"]["B"][0]
    assert (slot_b["work_order_id"], slot_b["state"], slot_b["sla_ok"]) == (b, "SCHEDULED", True)
    assert slot_b["reason"].startswith("Line B 09:00–10:30. Line A chỉ trống từ 15:00 → chọn Line B.")

    old = (await client.get("/api/schedule?version=1")).json()
    assert old["plan_version"]["status"] == "SUPERSEDED"
    assert old["lines"]["B"] == [] and len(old["lines"]["A"]) == 1


async def test_schedule_date_filter_uses_local_day(client, sign_in, make_wo):
    sign_in(Role.PLANNER)
    wid = make_wo(duration=60, arrival=t(2), ret=t(9))  # 09:00 ngày 01/01 giờ +07
    await client.post(f"/api/work-orders/{wid}/schedule")
    assert len((await client.get("/api/schedule?date=2030-01-01")).json()["lines"]["A"]) == 1
    assert (await client.get("/api/schedule?date=2030-01-02")).json()["lines"]["A"] == []


async def test_schedule_empty_and_unknown_version(client, sign_in):
    sign_in(Role.SALES)
    assert (await client.get("/api/schedule")).json() == {
        "plan_version": None,
        "date": None,
        "lines": {"A": [], "B": []},
    }
    assert (await client.get("/api/schedule?version=99")).status_code == 404
    assert (await client.get("/api/schedule?version=abc")).status_code == 422


async def test_schedule_block_returns_409_with_risk(client, sign_in, make_wo):
    """T-036: không kịp giờ trả dù xếp sớm nhất → BLOCK_NEW_ORDER, không tạo plan version."""
    sign_in(Role.PLANNER)
    wid = make_wo(duration=600, arrival=t(2), ret=t(9))
    r = await client.post(f"/api/work-orders/{wid}/schedule")
    assert r.status_code == 409
    detail = r.json()["detail"]
    assert detail["error_code"] == "NEW_ORDER_BLOCKED"
    assert detail["risk"]["level"] == "BLOCK"
    assert datetime.fromisoformat(detail["risk"]["earliest_feasible_return"]) == t(12)
    assert (await client.get("/api/plan-versions")).json() == []
    card = (await client.get("/api/work-orders")).json()[0]
    assert (card["state"], card["slot"]) == ("BLOCK_NEW_ORDER", None)


async def test_schedule_warn_pending_approval(client, sign_in, make_wo):
    """T-036: VIP kịp nhờ đẩy đơn Thường → WARN, version chờ duyệt, lịch ACTIVE giữ nguyên."""
    sign_in(Role.PLANNER)
    for _ in range(2):
        nid = make_wo(duration=420, arrival=t(2), ret=t(10), priority=Priority.NORMAL)
        assert (await client.post(f"/api/work-orders/{nid}/schedule")).json()["risk"]["level"] == "OK"
    vip = make_wo(duration=180, arrival=t(2), ret=t(6))
    body = (await client.post(f"/api/work-orders/{vip}/schedule")).json()
    assert (body["risk"]["level"], body["plan_status"], body["sla_ok"]) == ("WARN", "PENDING_APPROVAL", True)
    assert (body["line"], datetime.fromisoformat(body["start"])) == ("A", t(2))
    assert (await client.get("/api/schedule")).json()["plan_version"]["id"] == 2  # ACTIVE chưa đổi
    pending = (await client.get("/api/plan-versions?status=pending")).json()
    assert [(v["id"], v["requires_approval"]) for v in pending] == [(3, True)]
    card = next(c for c in (await client.get("/api/work-orders")).json() if c["id"] == vip)
    assert card["state"] == "PENDING_APPROVAL" and card["slot"]["plan_status"] == "PENDING_APPROVAL"


async def test_schedule_errors(client, sign_in, make_wo):
    sign_in(Role.PLANNER)
    assert (await client.post("/api/work-orders/nope/schedule")).status_code == 404
    assert (await client.post(f"/api/work-orders/{make_wo(state=WorkOrderState.DRAFT)}/schedule")).status_code == 409
    assert (await client.post(f"/api/work-orders/{make_wo(duration=None)}/schedule")).status_code == 422
    wid = make_wo()
    await client.post(f"/api/work-orders/{wid}/schedule")
    assert (await client.post(f"/api/work-orders/{wid}/schedule")).status_code == 409


@pytest.mark.parametrize("role", [Role.SALES, Role.OPS_MANAGER, Role.ADMIN])
async def test_only_planner_schedules_but_everyone_views(client, sign_in, make_wo, role):
    sign_in(role)
    wid = make_wo()
    assert (await client.post(f"/api/work-orders/{wid}/schedule")).status_code == 403
    r = await client.patch(f"/api/work-orders/{wid}/state", json={"to_state": "WAITING_ARRIVAL"})
    assert r.status_code == 403
    assert (await client.get("/api/schedule")).status_code == 200
    assert (await client.get("/api/work-orders")).status_code == 200
    assert (await client.get("/api/plan-versions")).status_code == 200


async def test_requires_login(client):
    assert (await client.get("/api/work-orders")).status_code == 401


async def test_kanban_list_and_state_filter(client, sign_in, make_wo):
    sign_in(Role.PLANNER)
    draft = make_wo(state=WorkOrderState.DRAFT, ret=t(5))
    wid = make_wo()
    await client.post(f"/api/work-orders/{wid}/schedule")
    cards = (await client.get("/api/work-orders")).json()
    assert [c["id"] for c in cards] == [draft, wid]  # theo giờ trả
    assert cards[0]["slot"] is None
    assert cards[1]["slot"] == {
        "line": "A",
        "start": "2030-01-01T02:00:00Z",
        "end": "2030-01-01T05:00:00Z",
        "sla_ok": True,
        "plan_version": 1,
        "plan_status": "ACTIVE",
    }
    only = (await client.get("/api/work-orders?state=SCHEDULED&state=CLOSED")).json()
    assert [c["id"] for c in only] == [wid]
    assert (await client.get("/api/work-orders?state=BOGUS")).status_code == 422


async def test_operational_state_flow(client, sign_in, make_wo, db):
    user = sign_in(Role.PLANNER)
    wid = make_wo()
    await client.post(f"/api/work-orders/{wid}/schedule")
    for to in ["WAITING_ARRIVAL", "READY_FOR_IRRADIATION", "IN_IRRADIATION", "COMPLETED_IRRADIATION"]:
        r = await client.patch(f"/api/work-orders/{wid}/state", json={"to_state": to, "reason": "hàng đã đến"})
        assert r.status_code == 200, r.text
        assert r.json()["state"] == to and r.json()["slot"]["line"] == "A"
    last = db.scalars(select(AuditLog).order_by(AuditLog.id.desc())).first()
    assert (last.actor_id, last.payload["to"], last.payload["reason"]) == (
        user.id,
        "COMPLETED_IRRADIATION",
        "hàng đã đến",
    )


async def test_operational_state_rejections(client, sign_in, make_wo):
    sign_in(Role.PLANNER)
    wid = make_wo()
    # Bỏ bước (chưa xếp lịch) → sai bảng chuyển
    r = await client.patch(f"/api/work-orders/{wid}/state", json={"to_state": "WAITING_ARRIVAL"})
    assert r.status_code == 409
    # Không phải trạng thái vận hành → không cho chuyển tay
    r = await client.patch(f"/api/work-orders/{wid}/state", json={"to_state": "SCHEDULED"})
    assert r.status_code == 422
    assert (await client.patch("/api/work-orders/nope/state", json={"to_state": "CLOSED"})).status_code == 404


async def test_plan_versions_list_newest_first(client, sign_in, make_wo):
    sign_in(Role.PLANNER)
    for _ in range(2):
        await client.post(f"/api/work-orders/{make_wo(duration=60)}/schedule")
    versions = (await client.get("/api/plan-versions")).json()
    assert [(v["id"], v["status"], v["slot_count"]) for v in versions] == [(2, "ACTIVE", 2), (1, "SUPERSEDED", 1)]
    assert (await client.get("/api/plan-versions?status=ACTIVE")).json()[0]["id"] == 2
    assert (await client.get("/api/plan-versions?status=nope")).status_code == 422
