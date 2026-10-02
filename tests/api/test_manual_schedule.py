"""BR-15 — Điều phối xếp / sửa lịch thủ công (PUT /api/work-orders/{id}/schedule, specs/api-contracts.md §3)."""

from datetime import datetime

import pytest
from sqlalchemy import select

from src.modules.identity import Role
from src.modules.intake import WorkOrder
from src.modules.orchestration import AuditLog, PlanChange, WorkOrderState
from src.modules.types import Priority
from tests.api.test_scheduling import make_wo, t  # noqa: F401 (fixture)

pytestmark = pytest.mark.asyncio


def put(client, wid, line, start: datetime):
    return client.put(f"/api/work-orders/{wid}/schedule", json={"line": line, "start": start.isoformat()})


async def test_place_new_order_manually(client, sign_in, db, make_wo):  # noqa: F811
    sign_in(Role.PLANNER)
    wid = make_wo()  # 180 phút, đến 09:00, trả 16:00 giờ +07
    r = await put(client, wid, "B", t(3))
    assert r.status_code == 200, r.text
    body = r.json()
    assert (body["line"], body["plan_status"], body["sla_ok"], body["plan_version"]) == ("B", "ACTIVE", True, 1)
    assert datetime.fromisoformat(body["end"]) == t(6)
    assert body["reason"] == "Line B 10:00–13:00. Điều phối xếp tay. Kịp giờ trả 16:00."
    assert db.get(WorkOrder, wid).state == WorkOrderState.SCHEDULED
    view = (await client.get("/api/schedule")).json()
    assert view["plan_version"]["trigger"] == "MANUAL" and view["lines"]["B"][0]["work_order_id"] == wid


async def test_move_scheduled_order_keeps_state_and_records_old_slot(client, sign_in, db, make_wo):  # noqa: F811
    user = sign_in(Role.PLANNER)
    wid = make_wo()
    assert (await client.post(f"/api/work-orders/{wid}/schedule")).json()["line"] == "A"
    r = await put(client, wid, "B", t(4))
    assert r.status_code == 200 and r.json()["plan_version"] == 2
    db.expire_all()
    assert db.get(WorkOrder, wid).state == WorkOrderState.SCHEDULED
    change = db.scalars(select(PlanChange).where(PlanChange.plan_version_id == 2)).one()
    assert change.change_type == "LINE_ASSIGNMENT" and change.old_value["line"] == "A"
    view = (await client.get("/api/schedule")).json()
    assert view["lines"]["A"] == [] and view["lines"]["B"][0]["work_order_id"] == wid
    old = (await client.get("/api/schedule?version=1")).json()
    assert old["plan_version"]["status"] == "SUPERSEDED"
    log = db.scalars(select(AuditLog).where(AuditLog.action == "PLAN_VERSION_CREATED")).all()[-1]
    assert (log.actor_id, log.payload["trigger"], log.payload["old"]["line"]) == (user.id, "MANUAL", "A")


async def test_overlap_rejected_with_occupying_order(client, sign_in, db, make_wo):  # noqa: F811
    sign_in(Role.PLANNER)
    a = make_wo(name="Hạt tiêu")
    b = make_wo(name="Quế")
    await client.post(f"/api/work-orders/{a}/schedule")  # Line A 09:00–12:00
    r = await put(client, b, "A", t(4))
    assert r.status_code == 409
    assert r.json()["detail"] == "Line A 11:00–14:00 trùng Hạt tiêu (09:00–12:00)"
    assert db.get(WorkOrder, b).state == WorkOrderState.FEASIBILITY_CHECK
    # Ngay sau đơn kia → được (biên không tính chồng)
    assert (await put(client, b, "A", t(5))).status_code == 200


async def test_late_placement_needs_approval(client, sign_in, db, make_wo):  # noqa: F811
    sign_in(Role.PLANNER)
    wid = make_wo(ret=t(9))  # trả 16:00
    r = await put(client, wid, "A", t(7))  # 14:00–17:00 → trễ 60 phút
    body = r.json()
    assert (body["plan_status"], body["sla_ok"]) == ("PENDING_APPROVAL", False)
    assert "Trễ giờ trả 16:00 60 phút" in body["reason"]
    assert db.get(WorkOrder, wid).state == WorkOrderState.PENDING_APPROVAL
    assert (await client.get("/api/schedule")).json()["plan_version"] is None  # chưa có ACTIVE
    change = db.scalars(select(PlanChange)).one()
    assert change.change_type == "RETURN_TIME_CHANGE" and change.needs_approval is True
    # Đang có phương án chờ duyệt → không sửa tiếp
    assert (await put(client, wid, "A", t(2))).status_code == 409


async def test_late_move_of_scheduled_order_keeps_active_plan(client, sign_in, db, make_wo):  # noqa: F811
    sign_in(Role.PLANNER)
    wid = make_wo(ret=t(9))
    await client.post(f"/api/work-orders/{wid}/schedule")
    r = await put(client, wid, "B", t(8))
    assert r.json()["plan_status"] == "PENDING_APPROVAL"
    db.expire_all()
    assert db.get(WorkOrder, wid).state == WorkOrderState.SCHEDULED
    active = (await client.get("/api/schedule")).json()
    assert active["plan_version"]["id"] == 1 and active["lines"]["A"][0]["work_order_id"] == wid


@pytest.mark.parametrize(
    ("start", "priority", "message"),
    [
        (t(1), Priority.VIP, "trước giờ hàng đến 09:00"),
        (datetime(2020, 1, 1, 2, tzinfo=t(0).tzinfo), Priority.VIP, "giờ bắt đầu đã qua"),
        (t(14), Priority.NORMAL, "đơn Thường chỉ chạy trọn trong ca ngày 06:00–22:00"),  # 21:00–00:00
    ],
)
async def test_invalid_start_is_422(client, sign_in, make_wo, start, priority, message):  # noqa: F811
    sign_in(Role.PLANNER)
    wid = make_wo(ret=t(4, day=2), priority=priority)
    r = await put(client, wid, "A", start)
    assert r.status_code == 422 and message in r.json()["detail"]


async def test_vip_may_run_night_shift(client, sign_in, make_wo):  # noqa: F811
    sign_in(Role.PLANNER)
    wid = make_wo(ret=t(4, day=2), priority=Priority.VIP)
    assert (await put(client, wid, "A", t(14))).status_code == 200


async def test_only_planner_and_only_not_started_orders(client, sign_in, make_wo):  # noqa: F811
    sign_in(Role.SALES)
    wid = make_wo()
    assert (await put(client, wid, "A", t(2))).status_code == 403
    sign_in(Role.PLANNER)
    running = make_wo(state=WorkOrderState.IN_IRRADIATION)
    assert (await put(client, running, "A", t(2))).status_code == 409
    r = await client.put(f"/api/work-orders/{wid}/schedule", json={"line": "A", "start": "2030-01-01T09:00:00"})
    assert r.status_code == 422  # thiếu múi giờ


async def test_order_longer_than_day_shift_has_readable_message(client, sign_in, make_wo):  # noqa: F811
    sign_in(Role.PLANNER)
    wid = make_wo(duration=17 * 60, ret=t(23, day=2), priority=Priority.NORMAL)
    r = await put(client, wid, "A", t(2))
    assert r.status_code == 422 and "đơn Thường dài 17h00, hơn cả ca ngày 06:00–22:00" in r.json()["detail"]


@pytest.mark.parametrize(
    ("ret_h", "status", "state"), [(9, "ACTIVE", "SCHEDULED"), (2, "PENDING_APPROVAL", "PENDING_APPROVAL")]
)
async def test_reschedule_required_order_placed_again(client, sign_in, db, make_wo, ret_h, status, state):  # noqa: F811
    """T-040: đơn bị từ chối phương án (RESCHEDULE_REQUIRED) được Điều phối xếp tay lại."""
    sign_in(Role.PLANNER)
    wid = make_wo(ret=t(ret_h))
    wo = db.get(WorkOrder, wid)
    wo.state = WorkOrderState.RESCHEDULE_REQUIRED
    db.commit()
    r = await put(client, wid, "A", t(3))
    assert r.status_code == 200, r.text
    assert r.json()["plan_status"] == status
    db.expire_all()
    assert db.get(WorkOrder, wid).state == state
