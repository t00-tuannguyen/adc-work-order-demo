"""ADC-005 T-037 — escalation tự động cho đơn trễ giờ trả (BR-06), hàng đợi GET /api/escalations (§5)."""

from datetime import datetime

import pytest
import pytest_asyncio
from sqlalchemy import select

from src.agents.risk_agent import Draft, DraftSource
from src.api.risk import get_risk_agent
from src.main import app
from src.modules.identity import Role
from src.modules.orchestration import AuditLog
from src.modules.types import Priority
from tests.api.test_incidents import incident, make_wo, planned, t  # noqa: F401 — fixture dùng chung

pytestmark = pytest.mark.asyncio


async def test_incident_late_order_gets_escalation(client, planned, db):  # noqa: F811
    body = (await client.post("/api/incidents", json=incident(start=t(2), downtime=180))).json()
    [esc] = (await client.get("/api/escalations?status=open")).json()
    assert body["sla_risks"] == [esc["work_order_id"]] == [planned["N1"]]
    # N1 giờ trả 8:00, phương án mới xong 9:00 → trễ 60 phút
    assert (esc["status"], esc["incident_id"], esc["delay_min"], esc["state"]) == (
        "OPEN",
        1,
        60,
        "ESCALATED_TO_BUSINESS",
    )
    assert datetime.fromisoformat(esc["expected_finish"]) == t(9)
    assert (esc["draft_message"], esc["can_close"]) == (None, False)
    audit = db.scalars(select(AuditLog).where(AuditLog.action == "ESCALATION_CREATED")).one()
    assert audit.payload == {
        "escalation_id": esc["id"],
        "work_order_id": planned["N1"],
        "incident_id": 1,
        "delay_min": 60,
    }


async def test_every_late_order_has_exactly_one_open_escalation(client, sign_in, make_wo):  # noqa: F811
    """TC: mọi đơn SLA_RISK trễ đều có escalation (đếm đủ 100%), tính lại phương án không tạo trùng."""
    sign_in(Role.PLANNER)
    ids = [make_wo(Priority.NORMAL, 120, t(1), t(6), f"Đơn {i}") for i in range(4)]  # A 1–3, B 1–3, A 3–5, B 3–5
    for wid in ids:
        await client.post(f"/api/work-orders/{wid}/schedule")
    body = (await client.post("/api/incidents", json=incident(start=t(1), downtime=240))).json()
    late = {a["work_order_id"] for a in body["affected_orders"] if not a["sla_ok"]}
    assert len(late) == 2  # 2 đơn trên A dồn ra sau B / sau hồi phục
    open_ = (await client.get("/api/escalations?status=open")).json()
    assert {e["work_order_id"] for e in open_} == late and len(open_) == len(late)
    # Hồi phục muộn hơn → tính lại: cập nhật số phút trễ, không thêm mục
    await client.post("/api/incidents/1/resolve", json={"actual_end": t(6).isoformat()})
    again = (await client.get("/api/escalations?status=open")).json()
    assert {e["id"] for e in again} == {e["id"] for e in open_}
    assert sum(e["delay_min"] for e in again) > sum(e["delay_min"] for e in open_)


async def test_recovered_early_marks_escalation_can_close(client, planned):  # noqa: F811
    """Sự cố kết thúc sớm → hết trễ → escalation vẫn mở nhưng `can_close` để người xác nhận."""
    await client.post("/api/incidents", json=incident(start=t(2), downtime=180))
    await client.post("/api/incidents/1/resolve", json={"actual_end": t(3).isoformat()})
    by_order = {e["work_order_id"]: e for e in (await client.get("/api/escalations")).json()}
    assert (by_order[planned["N1"]]["status"], by_order[planned["N1"]]["can_close"]) == ("OPEN", True)
    # Phương án tính lại theo khung dừng thực tế làm N2 trễ 60 phút → mục mới, chưa đóng được
    assert (by_order[planned["N2"]]["delay_min"], by_order[planned["N2"]]["can_close"]) == (60, False)


async def test_warn_bumped_late_order_gets_escalation_without_incident(client, sign_in, make_wo):  # noqa: F811
    sign_in(Role.PLANNER)
    normal = make_wo(Priority.NORMAL, 420, t(1), t(9), "Thường A")
    await client.post(f"/api/work-orders/{normal}/schedule")
    await client.post(f"/api/work-orders/{make_wo(Priority.NORMAL, 420, t(1), t(9), 'Thường B')}/schedule")
    vip = make_wo(Priority.VIP, 180, t(1), t(5), "VIP")
    assert (await client.post(f"/api/work-orders/{vip}/schedule")).json()["risk"]["level"] == "WARN"
    [esc] = (await client.get("/api/escalations?status=open")).json()
    # Thường A bị đẩy A 1–8 → A 4–11, giờ trả 9:00 → trễ 120 phút; giữ SCHEDULED tới khi duyệt
    assert (esc["work_order_id"], esc["incident_id"], esc["delay_min"], esc["state"]) == (
        normal,
        None,
        120,
        "SCHEDULED",
    )


async def test_escalation_queue_filters_and_order(client, sign_in, planned):  # noqa: F811
    await client.post("/api/incidents", json=incident(start=t(2), downtime=180))
    sign_in(Role.SALES)
    assert len((await client.get("/api/escalations")).json()) == 1
    assert len((await client.get("/api/escalations?status=OPEN")).json()) == 1
    assert (await client.get("/api/escalations?status=approved")).json() == []
    assert (await client.get("/api/escalations?status=nope")).status_code == 422


async def test_escalation_queue_requires_active_account(client, sign_in):
    assert (await client.get("/api/escalations")).status_code == 401
    sign_in(None)
    assert (await client.get("/api/escalations")).status_code == 403


# --- T-038: soạn nháp & duyệt thông điệp -------------------------------------------------------------------------


class FakeAgent:
    def __init__(self):
        self.events = []

    def draft(self, event):
        self.events.append(event)
        return Draft(f"Nháp AI cho {event.product_name}", DraftSource.LLM)


@pytest.fixture
def fake_agent():
    agent = FakeAgent()
    app.dependency_overrides[get_risk_agent] = lambda: agent
    yield agent
    app.dependency_overrides.pop(get_risk_agent, None)


@pytest_asyncio.fixture
async def escalated(client, planned):  # noqa: F811
    await client.post("/api/incidents", json=incident(start=t(2), downtime=180))
    [esc] = (await client.get("/api/escalations?status=open")).json()
    return esc


async def test_draft_then_approve_edited_message(client, sign_in, escalated, fake_agent, db):
    sign_in(Role.SALES)
    eid = escalated["id"]
    r = await client.post(f"/api/escalations/{eid}/draft")
    assert r.status_code == 200 and r.json() == {"message_draft": "Nháp AI cho Ớt", "source": "LLM"}
    [event] = fake_agent.events
    assert (event.requested_return, event.expected_finish) == (t(8), t(9))  # giờ lấy từ dữ liệu, không từ LLM
    assert event.cause == "sự cố kỹ thuật trên dây chuyền chiếu xạ"
    [esc] = (await client.get("/api/escalations?status=open")).json()
    assert (esc["status"], esc["draft_message"], esc["final_message"]) == ("DRAFTED", "Nháp AI cho Ớt", None)

    assert (await client.post(f"/api/escalations/{eid}/draft")).status_code == 200  # soạn lại được khi DRAFTED

    sign_in(Role.OPS_MANAGER, email="manager@adc.test")
    r = await client.post(f"/api/escalations/{eid}/approve", json={"final_message": "  Bản đã sửa  "})
    assert r.status_code == 200
    body = r.json()
    assert (body["status"], body["final_message"], body["can_close"]) == ("APPROVED", "Bản đã sửa", False)
    assert body["approved_by"] and body["approved_at"]
    audit = db.scalars(select(AuditLog).where(AuditLog.action == "ESCALATION_APPROVED")).one()
    assert (audit.actor_id, audit.payload["edited"]) == (body["approved_by"], True)
    assert (await client.get("/api/escalations?status=open")).json() == []

    # Đã duyệt → không soạn lại, không duyệt lại
    assert (await client.post(f"/api/escalations/{eid}/draft")).status_code == 409
    assert (await client.post(f"/api/escalations/{eid}/approve", json={"final_message": "x"})).status_code == 409


async def test_no_path_sends_message_without_approval(client, sign_in, escalated, fake_agent):
    """TC: không có đường nào gửi thông điệp mà bỏ qua bước duyệt."""
    eid = escalated["id"]
    sign_in(Role.SALES)
    # Chưa có nháp → không duyệt được
    assert (await client.post(f"/api/escalations/{eid}/approve", json={"final_message": "x"})).status_code == 409
    await client.post(f"/api/escalations/{eid}/draft")
    [esc] = (await client.get("/api/escalations")).json()
    assert esc["final_message"] is None and esc["approved_by"] is None  # nháp không bao giờ tự gửi
    assert (await client.post(f"/api/escalations/{eid}/approve", json={"final_message": "   "})).status_code == 422
    # Điều phối không soạn / duyệt thông điệp (specs/user-roles.md §2)
    sign_in(Role.PLANNER, email="planner2@adc.test")
    assert (await client.post(f"/api/escalations/{eid}/draft")).status_code == 403
    assert (await client.post(f"/api/escalations/{eid}/approve", json={"final_message": "x"})).status_code == 403
    assert (await client.post("/api/escalations/99/draft")).status_code in (403, 404)


async def test_ai_draft_disabled_uses_template(client, sign_in, escalated, test_settings):
    test_settings.feature_ai_message_draft = False
    sign_in(Role.SALES)
    body = (await client.post(f"/api/escalations/{escalated['id']}/draft")).json()
    assert body["source"] == "TEMPLATE"
    assert "15:00 ngày 01/01/2030" in body["message_draft"] and "16:00 ngày 01/01/2030" in body["message_draft"]
    assert (await client.post("/api/escalations/99/draft")).status_code == 404


async def test_newer_version_copying_active_slot_does_not_hide_pending_delay(client, planned, make_wo):  # noqa: F811
    """Version mới chép lịch ACTIVE (xếp đơn khác sau sự cố) không làm escalation tưởng đã hết trễ."""
    await client.post("/api/incidents", json=incident(start=t(2), downtime=180))
    other = make_wo(Priority.NORMAL, 60, t(12), t(20), "Đơn sau")
    assert (await client.post(f"/api/work-orders/{other}/schedule")).json()["plan_status"] == "ACTIVE"
    [esc] = (await client.get("/api/escalations?status=open")).json()
    assert (esc["work_order_id"], esc["can_close"]) == (planned["N1"], False)
