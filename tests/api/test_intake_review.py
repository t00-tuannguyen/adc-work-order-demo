"""ADC-001 T-020 — cổng tiếp nhận sau trích xuất + PATCH / submit / cảnh báo tiếp nhận."""

import pytest
from sqlalchemy import select

from src.modules.identity import Role
from src.modules.intake import ClarificationRequest, FieldExtraction, IntakeWarning, Ticket, WorkOrder
from src.modules.orchestration import AuditLog
from tests.agents.test_order_agent import field, full_ticket
from tests.api.test_intake_pipeline import run, use_extractor  # noqa: F401 (fixture)
from tests.api.test_intake_tickets import agent, paste  # noqa: F401 (fixture)
from tests.pdf_samples import SCAN_PDF, TEXT_PDF

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("no_auto_schedule")]


async def intake(client, use_extractor, ticket, content=TEXT_PDF):  # noqa: F811
    use_extractor({"tickets": [ticket]})
    job = await run(client, content)
    assert job["status"] == "SUCCEEDED"
    return job["work_orders"][0]


def actions(db):
    return [a.action for a in db.scalars(select(AuditLog).order_by(AuditLog.id))]


async def test_tc12_warn_proceeds_and_warning_can_be_acknowledged(client, sign_in, db, use_extractor):  # noqa: F811
    user = sign_in(Role.SALES)
    wo = await intake(client, use_extractor, full_ticket(priority=field("URGENT", kind="INFERRED")))
    assert (wo["state"], wo["review_status"]) == ("FEASIBILITY_CHECK", "ACCEPTED_WITH_WARNINGS")

    warnings = (await client.get("/api/intake-warnings", params={"status": "open"})).json()
    assert [(w["work_order_id"], w["field"], w["code"]) for w in warnings] == [(wo["id"], "priority", "INFERRED_VALUE")]

    res = await client.post(f"/api/intake-warnings/{warnings[0]['id']}/ack", json={"note": "đã gọi khách"})
    assert res.status_code == 200
    assert (await client.get("/api/intake-warnings")).json() == []
    assert len((await client.get("/api/intake-warnings", params={"status": "acknowledged"})).json()) == 1
    assert (await client.post(f"/api/intake-warnings/{warnings[0]['id']}/ack", json={})).status_code == 409
    log = db.scalars(select(AuditLog).where(AuditLog.action == "INTAKE_WARNING_ACKNOWLEDGED")).one()
    assert (log.actor_id, log.payload["note"]) == (user.id, "đã gọi khách")


async def test_duplicate_upload_warns_but_does_not_block(client, sign_in, use_extractor):  # noqa: F811
    sign_in(Role.SALES)
    first = await intake(client, use_extractor, full_ticket())
    second = await intake(client, use_extractor, full_ticket())
    assert first["review_status"] == "AUTO_ACCEPTED"
    assert (second["state"], second["review_status"]) == ("FEASIBILITY_CHECK", "ACCEPTED_WITH_WARNINGS")
    codes = [w["code"] for w in (await client.get("/api/intake-warnings")).json()]
    assert codes == ["POSSIBLE_DUPLICATE"]


async def test_tc2_tc13_low_confidence_held_until_confirmed(client, sign_in, db, use_extractor):  # noqa: F811
    sign_in(Role.SALES)
    wo = await intake(client, use_extractor, full_ticket(quantity=field(120, conf=0.6)), SCAN_PDF)
    assert (wo["state"], wo["review_status"]) == ("DRAFT", "NEEDS_REVIEW")

    res = await client.post(f"/api/work-orders/{wo['id']}/submit")
    assert res.status_code == 422
    assert res.json()["detail"] == {"errors": [], "unconfirmed_fields": ["quantity"]}

    # Xác nhận đúng giá trị cũ → MANUAL
    body = (await client.patch(f"/api/work-orders/{wo['id']}", json={"fields": {"quantity": 120}})).json()
    q = next(e for e in body["extractions"] if e["field"] == "quantity")
    assert (q["source_kind"], q["confidence"], q["page"]) == ("MANUAL", None, 1)
    assert (body["unconfirmed_fields"], body["can_submit"], body["state"]) == ([], True, "DRAFT")

    body = (await client.post(f"/api/work-orders/{wo['id']}/submit")).json()
    assert body["state"] == "FEASIBILITY_CHECK"
    assert actions(db)[-2:] == ["WORK_ORDER_FIELDS_EDITED", "WORK_ORDER_STATE_CHANGED"]


async def test_tc3_missing_fields_then_filled(client, sign_in, db, use_extractor):  # noqa: F811
    sign_in(Role.SALES)
    ticket = full_ticket(required_dose_kgy=field(None), requested_return=field(None))
    wo = await intake(client, use_extractor, ticket)
    assert (wo["state"], wo["review_status"]) == ("DRAFT", "NEEDS_CLARIFICATION")
    questions = db.scalars(select(ClarificationRequest).where(ClarificationRequest.work_order_id == wo["id"])).all()
    assert {q.field for q in questions} == {"required_dose_kgy", "requested_return"}

    res = await client.post(f"/api/work-orders/{wo['id']}/submit")
    assert res.status_code == 422
    assert {e["field"] for e in res.json()["detail"]["errors"]} == {"required_dose_kgy", "requested_return"}

    body = (
        await client.patch(
            f"/api/work-orders/{wo['id']}",
            json={"fields": {"required_dose_kgy": 10, "requested_return": "2026-10-02T16:00:00+07:00"}},
        )
    ).json()
    assert (body["errors"], body["review_status"], body["can_submit"]) == ([], "NEEDS_REVIEW", True)
    assert all(c["status"] == "ANSWERED" for c in body["clarifications"])
    assert (await client.post(f"/api/work-orders/{wo['id']}/submit")).json()["state"] == "FEASIBILITY_CHECK"


async def test_tc8_return_before_arrival_reported_on_field(client, sign_in, use_extractor):  # noqa: F811
    sign_in(Role.SALES)
    wo = await intake(client, use_extractor, full_ticket())
    # đơn AUTO đã qua DRAFT → không sửa qua API tiếp nhận
    assert (await client.patch(f"/api/work-orders/{wo['id']}", json={"fields": {"quantity": 1}})).status_code == 409

    draft = await intake(client, use_extractor, full_ticket(quantity=field(None)))
    body = (
        await client.patch(
            f"/api/work-orders/{draft['id']}",
            json={"fields": {"quantity": 50, "requested_return": "2026-10-02T08:00:00+07:00"}},
        )
    ).json()
    assert body["errors"] == [{"field": "requested_return", "code": "RETURN_NOT_AFTER_ARRIVAL"}]
    assert body["can_submit"] is False


async def test_tc14_uncertain_boundary_submit_confirms(client, sign_in, use_extractor):  # noqa: F811
    sign_in(Role.SALES)
    ticket = full_ticket()
    ticket["boundary_uncertain"] = True
    wo = await intake(client, use_extractor, ticket)
    assert (wo["state"], wo["review_status"]) == ("DRAFT", "NEEDS_REVIEW")
    assert (await client.post(f"/api/work-orders/{wo['id']}/submit")).json()["state"] == "FEASIBILITY_CHECK"


async def test_dimension_edit_updates_single_source(client, sign_in, db, use_extractor):  # noqa: F811
    sign_in(Role.SALES)
    wo = await intake(client, use_extractor, full_ticket(package_dimensions_cm=field(None)))
    body = (
        await client.patch(
            f"/api/work-orders/{wo['id']}",
            json={"fields": {"pkg_length_cm": 40, "pkg_width_cm": 30, "pkg_height_cm": 25}},
        )
    ).json()
    dims = [e for e in body["extractions"] if e["field"] == "package_dimensions_cm"]
    assert [(d["value"], d["source_kind"]) for d in dims] == [({"length": 40, "width": 30, "height": 25}, "MANUAL")]


async def test_patch_validation(client, sign_in, use_extractor):  # noqa: F811
    sign_in(Role.SALES)
    wo = await intake(client, use_extractor, full_ticket(quantity=field(None)))
    url = f"/api/work-orders/{wo['id']}"
    assert (await client.patch(url, json={"fields": {}})).status_code == 422
    assert (await client.patch(url, json={"fields": {"state": "SCHEDULED"}})).status_code == 422
    assert (await client.patch(url, json={"fields": {"requested_return": "2026-10-02T16:00"}})).status_code == 422
    assert (await client.patch("/api/work-orders/khong-co", json={"fields": {"quantity": 1}})).status_code == 404
    assert (await client.post("/api/work-orders/khong-co/submit")).status_code == 404


async def test_review_endpoints_require_sales_or_planner(client, sign_in):
    for role in (Role.OPS_MANAGER, Role.ADMIN):
        sign_in(role)
        assert (await client.get("/api/intake-warnings")).status_code == 403
        assert (await client.patch("/api/work-orders/x", json={"fields": {"quantity": 1}})).status_code == 403
        assert (await client.post("/api/work-orders/x/submit")).status_code == 403
        assert (await client.delete("/api/work-orders/x")).status_code == 403
        assert (await client.post("/api/intake-warnings/1/ack", json={})).status_code == 403


async def test_submit_only_draft(client, sign_in, db, use_extractor):  # noqa: F811
    sign_in(Role.SALES)
    wo = await intake(client, use_extractor, full_ticket())
    assert db.get(WorkOrder, wo["id"]).state == "FEASIBILITY_CHECK"
    assert (await client.post(f"/api/work-orders/{wo['id']}/submit")).status_code == 409


async def test_delete_draft_removes_order_ticket_and_intake_rows(client, sign_in, db, use_extractor):  # noqa: F811
    user = sign_in(Role.SALES)
    wo = await intake(client, use_extractor, full_ticket(quantity=field(None)))
    assert wo["state"] == "DRAFT"
    db.add(IntakeWarning(work_order_id=wo["id"], field=None, code="POSSIBLE_DUPLICATE"))
    db.commit()
    review = (await client.get(f"/api/work-orders/{wo['id']}/intake")).json()
    ticket_id, file_id = db.get(WorkOrder, wo["id"]).ticket_id, review["source"]["file_id"]
    assert review["clarifications"] and review["warnings"]

    res = await client.delete(f"/api/work-orders/{wo['id']}")
    assert res.status_code == 204
    db.expire_all()
    assert db.get(WorkOrder, wo["id"]) is None and db.get(Ticket, ticket_id) is None
    for model in (FieldExtraction, ClarificationRequest, IntakeWarning):
        assert db.scalars(select(model).where(model.work_order_id == wo["id"])).all() == []
    assert (await client.get(f"/api/work-orders/{wo['id']}/intake")).status_code == 404
    assert (await client.get(f"/api/files/{file_id}")).status_code == 200  # giữ file gốc

    log = db.scalars(select(AuditLog).where(AuditLog.action == "WORK_ORDER_DELETED")).one()
    assert log.actor_id == user.id
    assert (log.payload["work_order_id"], log.payload["ticket_id"], log.payload["source"]) == (
        wo["id"],
        ticket_id,
        "PDF",
    )
    assert log.payload["fields"]["quantity"] is None and log.payload["fields"]["product_name"]


async def test_delete_manual_draft(client, sign_in, db, agent):  # noqa: F811
    sign_in(Role.SALES)
    agent(None)
    [wo] = (await paste(client, None, source="MANUAL")).json()["work_orders"]
    assert (await client.delete(f"/api/work-orders/{wo['id']}")).status_code == 204
    db.expire_all()
    assert db.get(WorkOrder, wo["id"]) is None


async def test_delete_only_draft(client, sign_in, db, use_extractor):  # noqa: F811
    sign_in(Role.SALES)
    wo = await intake(client, use_extractor, full_ticket())
    assert wo["state"] == "FEASIBILITY_CHECK"
    assert (await client.delete(f"/api/work-orders/{wo['id']}")).status_code == 409
    assert db.get(WorkOrder, wo["id"]) is not None
    assert (await client.delete("/api/work-orders/khong-co")).status_code == 404
    assert "WORK_ORDER_DELETED" not in actions(db)
