"""ADC-001 T-021 — dán nội dung / nhập tay (POST /api/tickets), file gốc, dữ liệu màn xác nhận."""

import pytest
from sqlalchemy import select

from src.agents.order_agent import ExtractionFailedError
from src.api.intake import get_order_agent
from src.main import app
from src.modules.identity import Role
from src.modules.intake import Ticket
from src.modules.orchestration import AuditLog
from tests.agents.test_order_agent import field, full_ticket
from tests.api.test_intake_pipeline import FakeExtractor, run, use_extractor  # noqa: F401 (fixture)
from tests.pdf_samples import TEXT_PDF

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("no_auto_schedule")]

EMAIL = "Gửi 120 thùng bột ớt, 40x30x25 cm, 8 kg/thùng, 10 kGy, đến 9h 2/10, trả 16h 2/10."


@pytest.fixture
def agent():
    def _use(result):
        fake = FakeExtractor(result) if result is not None else None
        app.dependency_overrides[get_order_agent] = lambda: fake
        return fake

    yield _use
    app.dependency_overrides.pop(get_order_agent, None)


def paste(client, text=EMAIL, source="TEXT"):
    return client.post(
        "/api/tickets", json={"raw_text": text, "source": source, "received_at": "2026-10-01T08:00:00+07:00"}
    )


async def test_pasted_text_goes_through_same_gate(client, sign_in, db, agent):
    user = sign_in(Role.SALES)
    fake = agent({"tickets": [full_ticket()]})
    res = await paste(client)
    assert res.status_code == 201
    [wo] = res.json()["work_orders"]
    assert (wo["state"], wo["review_status"]) == ("FEASIBILITY_CHECK", "AUTO_ACCEPTED")
    assert fake.calls == [EMAIL]
    ticket = db.scalars(select(Ticket)).one()
    assert (ticket.source_type, ticket.raw_text, ticket.file_id) == ("TEXT", EMAIL, None)
    log = db.scalars(select(AuditLog).where(AuditLog.action == "TICKET_CREATED")).one()
    assert (log.actor_id, log.payload) == (user.id, {"source": "TEXT", "work_orders": [wo["id"]]})

    detail = (await client.get(f"/api/work-orders/{wo['id']}/intake")).json()
    assert detail["source"]["type"] == "TEXT" and detail["source"]["raw_text"] == EMAIL


@pytest.mark.parametrize(
    ("result", "text", "status"),
    [
        ({"tickets": [full_ticket()]}, "   ", 422),  # nội dung trống
        (None, EMAIL, 503),  # chưa cấu hình Gemini
        (ExtractionFailedError("timeout"), EMAIL, 502),  # TC9 → nhập tay
        ({"tickets": []}, EMAIL, 422),  # không nhận ra ticket
    ],
)
async def test_paste_errors(client, sign_in, db, agent, result, text, status):
    sign_in(Role.SALES)
    agent(result)
    assert (await paste(client, text)).status_code == status
    assert db.query(Ticket).count() == 0


async def test_tc6_manual_entry_then_submit(client, sign_in, agent):
    sign_in(Role.SALES)
    agent(None)  # nhập tay không cần Gemini
    res = await paste(client, None, source="MANUAL")
    [wo] = res.json()["work_orders"]
    assert (wo["state"], wo["review_status"]) == ("DRAFT", "NEEDS_CLARIFICATION")

    url = f"/api/work-orders/{wo['id']}"
    detail = (await client.get(f"{url}/intake")).json()
    assert detail["source"]["type"] == "MANUAL" and detail["can_submit"] is False
    assert {c["field"] for c in detail["clarifications"]} == {
        "product_name",
        "quantity",
        "package_dimensions_cm",
        "pkg_weight_kg",
        "required_dose_kgy",
        "requested_return",
    }
    fields = {
        "product_name": "Bột ớt",
        "quantity": 120,
        "pkg_length_cm": 40,
        "pkg_width_cm": 30,
        "pkg_height_cm": 25,
        "pkg_weight_kg": 8,
        "required_dose_kgy": 10,
        "priority": "NORMAL",
        "expected_arrival": "2026-10-02T09:00:00+07:00",
        "requested_return": "2026-10-02T16:00:00+07:00",
    }
    body = (await client.patch(url, json={"fields": fields})).json()
    assert body["can_submit"] is True and all(e["source_kind"] == "MANUAL" for e in body["extractions"])
    assert (await client.post(f"{url}/submit")).json()["state"] == "FEASIBILITY_CHECK"


async def test_intake_detail_shows_file_source_and_warnings(client, sign_in, use_extractor):  # noqa: F811
    sign_in(Role.SALES)
    use_extractor({"tickets": [full_ticket(priority=field("URGENT", kind="INFERRED"))]})
    job = await run(client, TEXT_PDF)
    wo_id = job["work_orders"][0]["id"]
    detail = (await client.get(f"/api/work-orders/{wo_id}/intake")).json()
    src = detail["source"]
    assert (src["type"], src["file_name"], src["page_count"], src["page_from"], src["ocr_used"]) == (
        "PDF",
        "f.pdf",
        1,
        1,
        False,
    )
    assert [(w["field"], w["code"], w["status"]) for w in detail["warnings"]] == [
        ("priority", "INFERRED_VALUE", "OPEN")
    ]

    pdf = await client.get(f"/api/files/{src['file_id']}")
    assert pdf.status_code == 200 and pdf.content == TEXT_PDF
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.headers["content-disposition"].startswith("inline")
    assert pdf.headers["x-content-type-options"] == "nosniff"


async def test_file_and_intake_detail_access(client, sign_in):
    sign_in(Role.SALES)
    assert (await client.get("/api/files/khong-co")).status_code == 404
    assert (await client.get("/api/work-orders/khong-co/intake")).status_code == 404
    sign_in(Role.OPS_MANAGER)
    assert (await client.get("/api/files/x")).status_code == 403
    assert (await client.get("/api/work-orders/x/intake")).status_code == 403
    assert (await paste(client, source="MANUAL")).status_code == 403
