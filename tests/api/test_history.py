"""ADC-006 T-041 — lịch sử trạng thái work order (GET /api/work-orders/{id}/history, specs/api-contracts.md §6)."""

import pytest
from sqlalchemy import select

from src.modules.identity import Role
from src.modules.intake import WorkOrder
from src.modules.orchestration import StateHistory
from tests.api.test_demo_reset import enabled  # noqa: F401 (fixture)
from tests.api.test_incidents import incident, make_wo, planned, t  # noqa: F401 (fixture)

pytestmark = pytest.mark.asyncio


def steps(body: list[dict]) -> list[tuple[str | None, str, str]]:
    return [(e["from_state"], e["to_state"], e["actor_type"]) for e in body]


async def test_every_seed_order_has_history_from_draft(client, sign_in, db, enabled):  # noqa: F811
    user = sign_in(Role.PLANNER)
    orders = (await client.post("/api/demo/reset")).json()["work_orders"]
    assert orders
    for o in orders:
        body = (await client.get(f"/api/work-orders/{o['id']}/history")).json()
        assert steps(body) == [(None, "DRAFT", "SYSTEM"), ("DRAFT", "FEASIBILITY_CHECK", "SYSTEM")]
        assert {e["actor_id"] for e in body} == {user.id}
        assert body[0]["reason"] == f"nạp seed demo {o['ref']}"
    # reset lần 2 xóa lịch sử cũ cùng lệnh cũ
    await client.post("/api/demo/reset")
    assert db.scalar(select(StateHistory).where(StateHistory.work_order_id == orders[0]["id"])) is None


async def test_manual_ticket_history_names_the_user(client, sign_in):
    user = sign_in(Role.SALES)
    wid = (await client.post("/api/tickets", json={"source": "MANUAL"})).json()["work_orders"][0]["id"]
    body = (await client.get(f"/api/work-orders/{wid}/history")).json()
    assert steps(body) == [(None, "DRAFT", "USER")]
    assert (body[0]["actor_id"], body[0]["actor_name"], body[0]["reason"]) == (user.id, user.email, "nhập tay")


async def test_schedule_and_incident_entries_link_plan_version(client, planned, db):  # noqa: F811
    v = planned["V"]
    body = (await client.get(f"/api/work-orders/{v}/history")).json()
    assert steps(body) == [("FEASIBILITY_CHECK", "SCHEDULED", "USER")]
    assert body[0]["plan_version_id"] == 1 and body[0]["reason"].startswith("Line A")

    proposal = (await client.post("/api/incidents", json=incident(start=t(2), downtime=180))).json()
    body = (await client.get(f"/api/work-orders/{v}/history")).json()
    last = body[-1]
    assert (last["from_state"], last["to_state"], last["actor_type"]) == ("SCHEDULED", "LINE_INCIDENT", "SYSTEM")
    assert last["plan_version_id"] == proposal["proposed_plan_version"]["id"]
    # thứ tự cũ → mới, đúng trạng thái hiện tại của lệnh
    assert body[-1]["to_state"] == db.get(WorkOrder, v).state


async def test_history_requires_login_and_existing_order(client, sign_in):
    assert (await client.get("/api/work-orders/x/history")).status_code == 401
    sign_in(Role.ADMIN)
    assert (await client.get("/api/work-orders/x/history")).status_code == 404
