"""ADC-002 T-026 — lệnh vào FEASIBILITY_CHECK được gắn ước tính; WorkOrderReview trả breakdown."""

import pytest

from src.modules.identity import Role
from src.modules.intake import WorkOrder
from tests.agents.test_order_agent import field, full_ticket
from tests.api.test_intake_pipeline import use_extractor  # noqa: F401 (fixture)
from tests.api.test_intake_review import intake

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("no_auto_schedule")]

SPEC_BREAKDOWN = {"setup": 30, "weight_load": 48, "volume_load": 36, "dose_load": 42, "buffer": 15.6}


async def review(client, wo_id):
    return (await client.get(f"/api/work-orders/{wo_id}/intake")).json()


async def test_auto_accepted_order_gets_estimate(client, sign_in, db, use_extractor):  # noqa: F811
    sign_in(Role.SALES)
    wo = await intake(client, use_extractor, full_ticket())
    body = await review(client, wo["id"])
    assert body["state"] == "FEASIBILITY_CHECK"
    assert body["estimate"] == {"duration_min": 180, "breakdown": SPEC_BREAKDOWN, "config_version": "0.1.0"}
    assert body["estimate_error"] is None
    assert db.get(WorkOrder, wo["id"]).product_group == "spice"


async def test_draft_has_no_estimate_until_submitted(client, sign_in, use_extractor):  # noqa: F811
    sign_in(Role.SALES)
    ticket = full_ticket()
    ticket["boundary_uncertain"] = True
    wo = await intake(client, use_extractor, ticket)
    draft = await review(client, wo["id"])
    assert (draft["state"], draft["estimate"], draft["estimate_error"]) == ("DRAFT", None, None)

    submitted = (await client.post(f"/api/work-orders/{wo['id']}/submit")).json()
    assert submitted["estimate"]["duration_min"] == 180


async def test_unknown_product_explains_missing_estimate(client, sign_in, use_extractor):  # noqa: F811
    sign_in(Role.SALES)
    wo = await intake(client, use_extractor, full_ticket(product_name=field("Hạt điều rang muối")))
    body = await review(client, wo["id"])
    assert body["state"] == "FEASIBILITY_CHECK"
    assert body["estimate"] is None
    assert "nhóm sản phẩm" in body["estimate_error"]


async def test_unconfigured_group_factor_is_reported(client, sign_in, use_extractor):  # noqa: F811
    sign_in(Role.SALES)
    wo = await intake(client, use_extractor, full_ticket(product_name=field("Tôm sú đông lạnh")))
    body = await review(client, wo["id"])
    assert body["estimate"] is None and "seafood" in body["estimate_error"]
