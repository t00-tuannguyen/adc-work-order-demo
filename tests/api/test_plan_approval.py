"""ADC-006 T-042 — duyệt / từ chối plan version, diff trước/sau (specs/api-contracts.md §6). FR 12, BR-08/09."""

import pytest
from sqlalchemy import select

from src.modules.identity import Role
from src.modules.intake import WorkOrder
from src.modules.orchestration import AuditLog, WorkOrderState
from src.modules.types import Priority
from tests.api.test_incidents import incident, make_wo, planned, t  # noqa: F401 (fixture)
from tests.api.test_manual_schedule import put

pytestmark = pytest.mark.asyncio

S = WorkOrderState


async def _late_proposal(client, sign_in, make_wo) -> tuple[str, int]:  # noqa: F811
    """Điều phối xếp tay trễ giờ trả → RETURN_TIME_CHANGE chờ duyệt."""
    sign_in(Role.PLANNER, email="planner@adc.test")
    wid = make_wo(Priority.NORMAL, 180, t(1), t(4), "Bột ớt")  # đến 08:00, trả 11:00 (giờ +07)
    body = (await put(client, wid, "A", t(2))).json()  # 09:00–12:00 → trễ
    assert body["plan_status"] == "PENDING_APPROVAL"
    return wid, body["plan_version"]


async def test_only_approvers_decide_and_reason_is_required(client, sign_in, db, make_wo):  # noqa: F811
    wid, v = await _late_proposal(client, sign_in, make_wo)
    assert (await client.post(f"/api/plan-versions/{v}/approve", json={})).status_code == 403  # PLANNER
    sign_in(Role.ADMIN)
    assert (await client.post(f"/api/plan-versions/{v}/reject", json={"reason": "x"})).status_code == 403
    sign_in(Role.SALES)
    assert (await client.post(f"/api/plan-versions/{v}/reject", json={})).status_code == 422
    assert (await client.post(f"/api/plan-versions/{v}/reject", json={"reason": "   "})).status_code == 422
    assert (await client.post("/api/plan-versions/999/approve", json={})).status_code == 404
    assert db.get(WorkOrder, wid).state == S.PENDING_APPROVAL


async def test_diff_then_approve_activates_schedule(client, sign_in, db, make_wo):  # noqa: F811
    wid, v = await _late_proposal(client, sign_in, make_wo)
    assert (await client.get("/api/schedule")).json()["plan_version"] is None  # BR-08: chưa ACTIVE

    sign_in(Role.SALES)
    pending = (await client.get("/api/plan-versions?status=pending")).json()
    assert [p["id"] for p in pending] == [v]
    diff = (await client.get(f"/api/plan-versions/{v}/diff")).json()
    assert (diff["base_version_id"], diff["base_changed"], diff["incident_id"]) == (None, False, None)
    [change] = diff["changes"]
    assert (change["work_order_id"], change["change_type"], change["needs_approval"]) == (
        wid,
        "RETURN_TIME_CHANGE",
        True,
    )
    assert change["old"] is None and change["new"]["line"] == "A" and change["sla_ok"] is False
    assert "Trễ giờ trả" in change["reason"]

    ops = sign_in(Role.OPS_MANAGER)
    r = await client.post(f"/api/plan-versions/{v}/approve", json={"comment": "  khách đồng ý trả 12:00 "})
    assert r.status_code == 200 and r.json()["status"] == "ACTIVE"
    assert (await client.get("/api/schedule")).json()["plan_version"]["id"] == v
    db.expire_all()
    assert db.get(WorkOrder, wid).state == S.SCHEDULED
    decided = (await client.get(f"/api/plan-versions/{v}/diff")).json()
    assert (decided["decided_by"], decided["decided_by_name"], decided["comment"]) == (
        ops.id,
        ops.email,
        "khách đồng ý trả 12:00",
    )
    history = (await client.get(f"/api/work-orders/{wid}/history")).json()
    assert (history[-1]["to_state"], history[-1]["actor_id"], history[-1]["plan_version_id"]) == (
        "SCHEDULED",
        ops.id,
        v,
    )
    # đã duyệt → không duyệt / từ chối lại được
    assert (await client.post(f"/api/plan-versions/{v}/approve", json={})).status_code == 409
    assert (await client.post(f"/api/plan-versions/{v}/reject", json={"reason": "x"})).status_code == 409


async def test_rejected_order_is_placed_again_by_planner(client, sign_in, db, make_wo):  # noqa: F811
    wid, v = await _late_proposal(client, sign_in, make_wo)
    sales = sign_in(Role.SALES)
    r = await client.post(f"/api/plan-versions/{v}/reject", json={"reason": "Khách cần đúng 10:00"})
    assert r.status_code == 200 and r.json()["status"] == "REJECTED"
    assert db.get(WorkOrder, wid).state == S.RESCHEDULE_REQUIRED
    log = db.scalars(select(AuditLog).where(AuditLog.action == "PLAN_VERSION_REJECTED")).one()
    assert (log.actor_id, log.payload["reason"]) == (sales.id, "Khách cần đúng 10:00")
    # slot giữ chỗ được nhả → Điều phối xếp lại sớm hơn, kịp giờ trả
    sign_in(Role.PLANNER, email="planner2@adc.test")
    again = await put(client, wid, "A", t(1))
    assert again.status_code == 200 and again.json()["plan_status"] == "ACTIVE"
    db.expire_all()
    assert db.get(WorkOrder, wid).state == S.SCHEDULED


async def test_approve_incident_plan_schedules_affected_orders(client, sign_in, planned, db):  # noqa: F811
    proposal = (await client.post("/api/incidents", json=incident(start=t(2), downtime=180))).json()
    v = proposal["proposed_plan_version"]["id"]
    assert db.get(WorkOrder, planned["N1"]).state == S.ESCALATED_TO_BUSINESS
    diff = (await client.get(f"/api/plan-versions/{v}/diff")).json()
    assert diff["incident_id"] == 1 and len(diff["changes"]) == 4
    assert {c["change_type"] for c in diff["changes"]} == {"LINE_ASSIGNMENT", "PRIORITY_OVERRIDE", "INCIDENT_DELAY"}
    assert all(c["old"] is not None for c in diff["changes"])

    sign_in(Role.OPS_MANAGER)
    assert (await client.post(f"/api/plan-versions/{v}/approve", json={})).status_code == 200
    assert (await client.get("/api/schedule")).json()["plan_version"]["id"] == v
    db.expire_all()
    assert {db.get(WorkOrder, w).state for w in planned.values()} == {S.SCHEDULED}


async def test_reject_incident_plan_requires_rescheduling(client, sign_in, planned, db):  # noqa: F811
    proposal = (await client.post("/api/incidents", json=incident(start=t(2), downtime=180))).json()
    v = proposal["proposed_plan_version"]["id"]
    sign_in(Role.SALES)
    assert (await client.post(f"/api/plan-versions/{v}/reject", json={"reason": "chờ line A"})).status_code == 200
    assert (await client.get("/api/schedule")).json()["plan_version"]["id"] == 4  # lịch ACTIVE giữ nguyên
    db.expire_all()
    assert {db.get(WorkOrder, w).state for w in planned.values()} == {S.RESCHEDULE_REQUIRED}


async def test_approving_superseded_version_is_conflict(client, sign_in, planned):  # noqa: F811
    """TC: duyệt version cũ (đã có version mới hơn) → 409."""
    first = (await client.post("/api/incidents", json=incident(start=t(2), downtime=180))).json()
    old = first["proposed_plan_version"]["id"]
    resolved = (await client.post("/api/incidents/1/resolve", json={"actual_end": t(4).isoformat()})).json()
    assert resolved["proposed_plan_version"]["id"] > old
    sign_in(Role.SALES)
    r = await client.post(f"/api/plan-versions/{old}/approve", json={})
    assert r.status_code == 409 and "version mới hơn" in r.json()["detail"]
