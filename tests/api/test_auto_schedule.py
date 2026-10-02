"""ADC-003 — tạo ticket xong hệ thống tự xếp lịch; Kinh doanh không được sửa lịch."""

import pytest

from src.modules.identity import Role
from tests.agents.test_order_agent import field, full_ticket
from tests.api.test_intake_tickets import agent, paste  # noqa: F401 (fixture)

pytestmark = pytest.mark.asyncio

FIELDS = {
    "product_name": "Bột ớt",
    "quantity": 120,
    "pkg_length_cm": 40,
    "pkg_width_cm": 30,
    "pkg_height_cm": 25,
    "pkg_weight_kg": 8,
    "required_dose_kgy": 10,
    "priority": "NORMAL",
    "expected_arrival": "2030-01-01T09:00:00+07:00",  # tương lai — API dùng giờ thật làm `now`
    "requested_return": "2030-01-01T16:00:00+07:00",
}


async def manual_submit(client, fields):
    [wo] = (await paste(client, None, source="MANUAL")).json()["work_orders"]
    url = f"/api/work-orders/{wo['id']}"
    assert (await client.patch(url, json={"fields": fields})).json()["can_submit"] is True
    return wo["id"], (await client.post(f"{url}/submit")).json()


async def card(client, wo_id):
    return next(c for c in (await client.get("/api/work-orders")).json() if c["id"] == wo_id)


async def test_sales_submit_auto_schedules(client, sign_in, agent):  # noqa: F811
    sign_in(Role.SALES)
    agent(None)
    wo_id, body = await manual_submit(client, FIELDS)
    assert body["state"] == "SCHEDULED"
    slot = (await card(client, wo_id))["slot"]
    assert slot["line"] == "A" and slot["plan_status"] == "ACTIVE" and slot["sla_ok"] is True


async def test_pasted_ticket_auto_accepted_is_scheduled(client, sign_in, agent):  # noqa: F811
    sign_in(Role.SALES)
    agent(
        {
            "tickets": [
                full_ticket(expected_arrival=field("2030-01-01T09:00"), requested_return=field("2030-01-01T16:00"))
            ]
        }
    )
    [wo] = (await paste(client)).json()["work_orders"]
    assert (wo["state"], wo["review_status"]) == ("SCHEDULED", "AUTO_ACCEPTED")
    assert (await card(client, wo["id"]))["slot"] is not None


async def test_past_return_time_is_blocked(client, sign_in, agent):  # noqa: F811
    sign_in(Role.SALES)
    agent(None)
    fields = {
        **FIELDS,
        "expected_arrival": "2020-01-01T09:00:00+07:00",
        "requested_return": "2020-01-01T16:00:00+07:00",
    }
    wo_id, body = await manual_submit(client, fields)
    assert body["state"] == "BLOCK_NEW_ORDER"
    assert (await card(client, wo_id))["slot"] is None


async def test_unschedulable_order_stays_for_planner(client, sign_in, agent):  # noqa: F811
    """Đơn Thường dài hơn ca ngày → không có khe → giữ FEASIBILITY_CHECK cho Điều phối xử lý."""
    sign_in(Role.SALES)
    agent(None)
    fields = {**FIELDS, "quantity": 3000, "requested_return": "2030-01-05T16:00:00+07:00"}
    _, body = await manual_submit(client, fields)
    assert body["state"] == "FEASIBILITY_CHECK"


async def test_sales_cannot_change_schedule(client, sign_in, agent):  # noqa: F811
    sign_in(Role.SALES)
    agent(None)
    wo_id, _ = await manual_submit(client, {**FIELDS, "expected_arrival": "2020-01-01T09:00:00+07:00"})
    assert (await client.post(f"/api/work-orders/{wo_id}/schedule")).status_code == 403
