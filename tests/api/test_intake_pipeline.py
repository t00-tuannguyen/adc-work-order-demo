"""T-019 — job upload chạy Order Agent: 4 bước, tạo ticket + work order DRAFT + nguồn từng trường."""

import pytest
from sqlalchemy import select

from src.agents.intake_pipeline import OrderAgentPipeline
from src.agents.order_agent import ExtractionFailedError
from src.agents.schemas import DocumentExtraction
from src.api.intake import get_ingest_stages
from src.main import app
from src.modules.identity import Role
from src.modules.intake import FieldExtraction, ReviewThresholds, Ticket, WorkOrder
from src.modules.orchestration import AuditLog
from tests.agents.test_order_agent import field, full_ticket
from tests.pdf_samples import SCAN_PDF, TEXT_PDF, TICKET_TEXT, make_pdf

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("no_auto_schedule")]


class FakeExtractor:
    def __init__(self, result):
        self.result, self.calls = result, []

    def extract_pdf(self, pdf, *, page_count, received_at):
        self.calls.append(page_count)
        return self._result()

    def extract_text(self, text, *, received_at):
        self.calls.append(text)
        return self._result()

    def _result(self):
        if isinstance(self.result, Exception):
            raise self.result
        return DocumentExtraction.model_validate(self.result)


@pytest.fixture
def use_extractor():
    def _use(result, ocr_enabled=True):
        extractor = FakeExtractor(result)
        app.dependency_overrides[get_ingest_stages] = lambda: OrderAgentPipeline(
            extractor, ReviewThresholds(), ocr_enabled=ocr_enabled
        ).stages()
        return extractor

    yield _use
    app.dependency_overrides.pop(get_ingest_stages, None)


async def run(client, content=TEXT_PDF):
    res = await client.post("/api/tickets/upload", files={"file": ("f.pdf", content, "application/pdf")})
    return (await client.get(f"/api/ingest-jobs/{res.json()['job_id']}")).json()


async def test_tc1_tc4_tc11_two_clear_tickets_are_auto_accepted_with_sources(client, sign_in, db, use_extractor):
    user = sign_in(Role.SALES)
    second = full_ticket(product_name=field("Tôm đông lạnh", page=2))
    second.update(page_from=2, page_to=2)
    extractor = use_extractor({"tickets": [full_ticket(), second]})
    job = await run(client, make_pdf([TICKET_TEXT, TICKET_TEXT]))

    assert (job["status"], job["step"], job["progress"]) == ("SUCCEEDED", "DONE", 100)
    assert extractor.calls == [2]
    assert [(w["state"], w["review_status"]) for w in job["work_orders"]] == [
        ("FEASIBILITY_CHECK", "AUTO_ACCEPTED")
    ] * 2

    tickets = db.scalars(select(Ticket).order_by(Ticket.page_from)).all()
    assert [(t.page_from, t.page_to, t.source_type) for t in tickets] == [(1, 1, "PDF"), (2, 2, "PDF")]
    orders = {wo.ticket_id: wo for wo in db.scalars(select(WorkOrder))}
    assert orders[tickets[1].id].product_name == "Tôm đông lạnh"
    assert orders[tickets[0].id].pkg_height_cm == 25
    sources = db.scalars(select(FieldExtraction).where(FieldExtraction.work_order_id == orders[tickets[0].id].id)).all()
    assert len(sources) == 8 and all(s.page == 1 and s.bbox and s.confidence == 0.97 for s in sources)

    audit = db.scalars(select(AuditLog).where(AuditLog.action == "TICKET_EXTRACTED")).one()
    assert (audit.actor_id, audit.payload["tickets"]) == (user.id, 2)


async def test_tc9_extraction_failure_means_manual_entry(client, sign_in, db, use_extractor):
    sign_in(Role.SALES)
    use_extractor(ExtractionFailedError("timeout"))
    job = await run(client)
    assert (job["status"], job["error_code"], job["work_orders"]) == ("FAILED", "OCR_FAILED", [])
    assert db.query(Ticket).count() == 0


async def test_tc6_unreadable_scan_fails_with_ocr_failed(client, sign_in, use_extractor):
    sign_in(Role.SALES)
    use_extractor({"tickets": []})
    job = await run(client, SCAN_PDF)
    assert (job["status"], job["error_code"]) == ("FAILED", "OCR_FAILED")


async def test_ocr_disabled_skips_gemini_for_scans_only(client, sign_in, use_extractor):
    sign_in(Role.SALES)
    extractor = use_extractor({"tickets": [full_ticket()]}, ocr_enabled=False)
    assert (await run(client, SCAN_PDF))["error_code"] == "OCR_FAILED"
    assert extractor.calls == []
    assert (await run(client, TEXT_PDF))["status"] == "SUCCEEDED"
