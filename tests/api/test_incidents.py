"""ADC-004 — API sự cố line (specs/api-contracts.md §4)."""

from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy import select

from src.agents.scheduler_agent import SchedulerAgent
from src.agents.schemas import ScheduleExplanation
from src.api.incidents import get_scheduler_agent
from src.main import app
from src.modules.identity import Role
from src.modules.intake import Ticket, TicketSourceType, WorkOrder
from src.modules.orchestration import AuditLog, WorkOrderState
from src.modules.types import Priority

pytestmark = pytest.mark.asyncio


def t(hour: int, minute: int = 0, day: int = 1) -> datetime:
    """Giờ UTC ở tương lai — API dùng giờ thật làm `now`."""
    return datetime(2030, 1, day, hour, minute, tzinfo=UTC)


def incident(line="A", start=t(2), downtime=180, note="Dừng line A") -> dict:
    return {"line": line, "start_at": start.isoformat(), "est_downtime_min": downtime, "note": note}


async def test_declare_incident(client, sign_in, db):
    planner = sign_in(Role.PLANNER)
    r = await client.post("/api/incidents", json=incident(note="  Hỏng băng tải  "))
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["incident_id"] == 1 and body["line"] == "A" and body["status"] == "OPEN"
    assert datetime.fromisoformat(body["start_at"]) == t(2)
    assert datetime.fromisoformat(body["end_at"]) == t(5)
    assert (body["note"], body["created_by"], body["actual_end_at"]) == ("Hỏng băng tải", planner.id, None)
    # Chưa có lịch → không có đơn bị ảnh hưởng, không tạo phương án
    assert (body["affected_orders"], body["proposed_plan_version"], body["sla_risks"]) == ([], None, [])

    got = await client.get("/api/incidents/1")
    assert got.status_code == 200 and got.json() == body

    [entry] = db.scalars(select(AuditLog).where(AuditLog.action == "INCIDENT_DECLARED")).all()
    assert entry.actor_id == planner.id
    assert entry.payload == {
        "incident_id": 1,
        "line": "A",
        "start_at": t(2).isoformat(),
        "est_downtime_min": 180,
        "note": "Hỏng băng tải",
    }


@pytest.mark.parametrize(
    "patch",
    [
        {"line": "C"},
        {"est_downtime_min": -1},
        {"est_downtime_min": 7 * 24 * 60 + 1},
        {"start_at": "2030-01-01T09:00:00"},  # thiếu múi giờ
        {"note": "x" * 501},
    ],
)
async def test_declare_incident_invalid_input(client, sign_in, patch):
    sign_in(Role.PLANNER)
    assert (await client.post("/api/incidents", json={**incident(), **patch})).status_code == 422


async def test_overlapping_open_incident_same_line_conflicts(client, sign_in):
    sign_in(Role.PLANNER)
    assert (await client.post("/api/incidents", json=incident(start=t(2), downtime=180))).status_code == 201
    r = await client.post("/api/incidents", json=incident(start=t(4), downtime=60))
    assert r.status_code == 409 and "#1" in r.json()["detail"]
    # Line khác, hoặc nối tiếp ngay sau khung dừng → được
    assert (await client.post("/api/incidents", json=incident(line="B", start=t(4)))).status_code == 201
    assert (await client.post("/api/incidents", json=incident(start=t(5), downtime=30))).status_code == 201
    # Thời gian dừng 0 không chiếm khung nào
    assert (await client.post("/api/incidents", json=incident(start=t(3), downtime=0))).status_code == 201


@pytest.mark.parametrize("role", [Role.SALES, Role.OPS_MANAGER, Role.ADMIN])
async def test_only_planner_declares_but_everyone_views(client, sign_in, db, role):
    sign_in(Role.PLANNER, email="planner@adc.test")
    assert (await client.post("/api/incidents", json=incident())).status_code == 201
    sign_in(role)
    assert (await client.post("/api/incidents", json=incident(line="B"))).status_code == 403
    assert (await client.get("/api/incidents/1")).status_code == 200


async def test_incident_not_found_and_auth(client, sign_in):
    assert (await client.get("/api/incidents/1")).status_code == 401
    sign_in(Role.SALES)
    assert (await client.get("/api/incidents/99")).status_code == 404


# --- T-033: phương án phục hồi qua API ---


@pytest.fixture
def make_wo(db):
    def _make(priority, duration, arrival, ret, name) -> str:
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
            state=WorkOrderState.FEASIBILITY_CHECK,
        )
        db.add(wo)
        db.commit()
        return wo.id

    return _make


@pytest_asyncio.fixture
async def planned(client, sign_in, make_wo):
    """Lịch ACTIVE (giờ UTC): A: V 1–4, N1 4–7 · B: U 2–4, N2 4–6."""
    sign_in(Role.PLANNER)
    ids = {
        "V": make_wo(Priority.VIP, 180, t(1), t(5), "Hạt tiêu"),
        "U": make_wo(Priority.URGENT, 120, t(2), t(6), "Nghệ"),
        "N1": make_wo(Priority.NORMAL, 180, t(1), t(8), "Ớt"),
        "N2": make_wo(Priority.NORMAL, 120, t(4), t(7), "Quế"),
    }
    for wid in ids.values():
        assert (await client.post(f"/api/work-orders/{wid}/schedule")).json()["plan_status"] == "ACTIVE"
    view = (await client.get("/api/schedule")).json()
    assert [s["product_name"] for s in view["lines"]["A"]] == ["Hạt tiêu", "Ớt"]
    assert [s["product_name"] for s in view["lines"]["B"]] == ["Nghệ", "Quế"]
    return ids


def h(value: str) -> int:
    return datetime.fromisoformat(value).hour


async def test_line_a_incident_reschedules_by_priority(client, planned, db):
    ids = planned
    name = {v: k for k, v in ids.items()}
    body = (await client.post("/api/incidents", json=incident(start=t(2), downtime=180))).json()

    rows = [
        (
            name[a["work_order_id"]],
            a["old"]["line"],
            h(a["old"]["start"]),
            a["new"]["line"],
            h(a["new"]["start"]),
            h(a["new"]["end"]),
            a["outcome"],
            a["change_type"],
            a["sla_ok"],
            a["state"],
        )
        for a in body["affected_orders"]
    ]
    assert rows == [
        # VIP xử lý trước, sang B và đẩy đơn Khẩn chưa bắt đầu → kịp giờ trả
        ("V", "A", 1, "B", 1, 4, "MOVED_ALT_LINE", "LINE_ASSIGNMENT", True, "LINE_INCIDENT"),
        # Khẩn bị đẩy → trễ nếu sang A sau hồi phục, nên đẩy tiếp đơn Thường trên B → vẫn kịp
        ("U", "B", 2, "B", 4, 6, "DELAYED", "PRIORITY_OVERRIDE", True, "LINE_INCIDENT"),
        ("N2", "B", 4, "A", 5, 7, "MOVED_ALT_LINE", "PRIORITY_OVERRIDE", True, "LINE_INCIDENT"),
        # Thường không đẩy ai → trễ → SLA_RISK → escalation cho kinh doanh (T-037)
        ("N1", "A", 4, "B", 6, 9, "MOVED_ALT_LINE", "INCIDENT_DELAY", False, "ESCALATED_TO_BUSINESS"),
    ]
    assert body["sla_risks"] == [ids["N1"]]
    assert body["affected_orders"][0]["reason"].startswith("Line A dừng → Line B 08:00–11:00")
    assert body["explanation"].splitlines()[0] == (
        "Line A dừng 09:00–12:00 (dự kiến): 4 đơn phải xếp lại, theo thứ tự VIP → Khẩn → Thường rồi giờ trả sớm hơn."
    )

    proposal = body["proposed_plan_version"]
    assert (proposal["id"], proposal["status"], proposal["trigger"]) == (5, "PENDING_APPROVAL", "INCIDENT")
    assert (proposal["parent_version_id"], proposal["requires_approval"], proposal["slot_count"]) == (4, True, 4)

    # Lịch ACTIVE không đổi khi chưa duyệt
    active = (await client.get("/api/schedule")).json()
    assert active["plan_version"]["id"] == 4
    assert [(s["product_name"], h(s["start"])) for s in active["lines"]["A"]] == [("Hạt tiêu", 1), ("Ớt", 4)]
    # Phương án đề xuất không chồng lấn, không có gì trên A trong khung dừng 2–5
    view = (await client.get("/api/schedule?version=5")).json()
    assert [(s["product_name"], h(s["start"]), h(s["end"])) for s in view["lines"]["A"]] == [("Quế", 5, 7)]
    assert [(s["product_name"], h(s["start"]), h(s["end"])) for s in view["lines"]["B"]] == [
        ("Hạt tiêu", 1, 4),
        ("Nghệ", 4, 6),
        ("Ớt", 6, 9),
    ]
    assert view["lines"]["B"][1]["reason"].startswith("Nhường Line B cho đơn ưu tiên cao hơn")

    # GET trả đúng dữ liệu như lúc khai báo; mọi vai trò xem được
    assert (await client.get("/api/incidents/1")).json() == body

    created = db.scalars(select(AuditLog).where(AuditLog.action == "PLAN_VERSION_CREATED")).all()[-1]
    assert created.payload["trigger"] == "INCIDENT" and created.payload["incident_id"] == 1
    assert created.payload["sla_risks"] == [ids["N1"]]


async def test_resolve_on_planned_end_keeps_proposal(client, planned):
    """Hồi phục đúng giờ dự kiến → không tính lại, giữ phương án đang chờ duyệt."""
    first = (await client.post("/api/incidents", json=incident(start=t(2), downtime=180))).json()
    again = await client.post("/api/incidents/1/resolve", json={"actual_end": t(5).isoformat()})
    assert again.status_code == 200 and again.json()["status"] == "RESOLVED"
    assert again.json()["proposed_plan_version"]["id"] == first["proposed_plan_version"]["id"]  # không tính lại


async def test_incident_without_affected_orders_creates_no_plan(client, planned):
    body = (await client.post("/api/incidents", json=incident(start=t(12), downtime=60))).json()
    assert (body["affected_orders"], body["proposed_plan_version"]) == ([], None)
    assert body["explanation"] == "Line A dừng 19:00–20:00 (dự kiến): không có đơn bị ảnh hưởng."


async def test_resolve_earlier_recomputes_and_supersedes_previous_proposal(client, planned):
    await client.post("/api/incidents", json=incident(start=t(2), downtime=180))
    r = await client.post("/api/incidents/1/resolve", json={"actual_end": t(3).isoformat()})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "RESOLVED" and datetime.fromisoformat(body["end_at"]) == t(3)
    assert body["proposed_plan_version"]["id"] == 6
    assert body["explanation"].startswith("Line A dừng 09:00–10:00 (đã hồi phục)")
    versions = {v["id"]: v["status"] for v in (await client.get("/api/plan-versions")).json()}
    assert (versions[5], versions[6]) == ("SUPERSEDED", "PENDING_APPROVAL")
    # Hồi phục 10:00 → N1 (bắt đầu 11:00) không còn bị ảnh hưởng
    assert planned["N1"] not in [a["work_order_id"] for a in body["affected_orders"]]
    old = (await client.get("/api/incidents/1")).json()
    assert old == body


async def test_resolve_errors(client, sign_in, planned):
    await client.post("/api/incidents", json=incident(start=t(2), downtime=180))
    assert (await client.post("/api/incidents/1/resolve", json={"actual_end": t(1).isoformat()})).status_code == 422
    assert (await client.post("/api/incidents/9/resolve", json={"actual_end": t(3).isoformat()})).status_code == 404
    assert (await client.post("/api/incidents/1/resolve", json={"actual_end": t(5).isoformat()})).status_code == 200
    assert (await client.post("/api/incidents/1/resolve", json={"actual_end": t(5).isoformat()})).status_code == 409
    sign_in(Role.SALES)
    assert (await client.post("/api/incidents/1/resolve", json={"actual_end": t(5).isoformat()})).status_code == 403


async def test_new_incident_supersedes_pending_incident_proposal(client, planned):
    first = (await client.post("/api/incidents", json=incident(start=t(2), downtime=180))).json()
    second = (await client.post("/api/incidents", json=incident(line="B", start=t(8), downtime=60))).json()
    assert second["proposed_plan_version"]["id"] == first["proposed_plan_version"]["id"] + 1
    versions = {v["id"]: v["status"] for v in (await client.get("/api/plan-versions")).json()}
    assert versions[first["proposed_plan_version"]["id"]] == "SUPERSEDED"
    # Phương án mới vẫn tránh khung dừng của sự cố Line A còn mở
    view = (await client.get(f"/api/schedule?version={second['proposed_plan_version']['id']}")).json()
    for s in view["lines"]["A"]:
        assert datetime.fromisoformat(s["end"]) <= t(2) or datetime.fromisoformat(s["start"]) >= t(5)
    for s in view["lines"]["B"]:
        assert datetime.fromisoformat(s["end"]) <= t(8) or datetime.fromisoformat(s["start"]) >= t(9)


async def test_pending_new_order_proposal_in_downtime_moves_into_incident_plan(client, sign_in, make_wo):
    """Đề xuất WARN (T-036) đang chờ duyệt giữ chỗ A 2–5 → Line A dừng 3–4 → đơn sang Line B trong phương án sự cố."""
    sign_in(Role.PLANNER)
    normal = make_wo(Priority.NORMAL, 180, t(2), t(9), "Thường")  # A 2–5
    make_wo_b = make_wo(Priority.NORMAL, 360, t(2), t(9), "Chiếm B")  # B 2–8
    for w in (normal, make_wo_b):
        assert (await client.post(f"/api/work-orders/{w}/schedule")).json()["plan_status"] == "ACTIVE"
    vip = make_wo(Priority.VIP, 180, t(2), t(6), "Hồi")  # sớm nhất A 5–8 trễ → đẩy đơn Thường → A 2–5
    assert (await client.post(f"/api/work-orders/{vip}/schedule")).json()["plan_status"] == "PENDING_APPROVAL"
    body = (await client.post("/api/incidents", json=incident(start=t(3), downtime=60))).json()
    by_id = {a["work_order_id"]: a for a in body["affected_orders"]}
    assert (by_id[vip]["state"], by_id[vip]["new"]["line"]) == ("PENDING_APPROVAL", "B")
    versions = {v["id"]: v["status"] for v in (await client.get("/api/plan-versions")).json()}
    assert versions == {1: "SUPERSEDED", 2: "ACTIVE", 3: "SUPERSEDED", 4: "PENDING_APPROVAL"}


async def test_scheduling_during_open_incident_avoids_downtime(client, sign_in, make_wo):
    sign_in(Role.PLANNER)
    await client.post("/api/incidents", json=incident(start=t(2), downtime=180))
    blocker = make_wo(Priority.NORMAL, 60, t(2), t(9), "B chiếm")
    assert (await client.post(f"/api/work-orders/{blocker}/schedule")).json()["line"] == "B"
    wid = make_wo(Priority.VIP, 60, t(2), t(9), "Sau")
    body = (await client.post(f"/api/work-orders/{wid}/schedule")).json()
    # A dừng 2–5 → B 3–4 (sau đơn trước) thay vì A 2–3
    assert (body["line"], h(body["start"])) == ("B", 3)


async def test_seed_line_a_incident_same_result_after_every_reset(client, sign_in, test_settings, monkeypatch):
    """Kịch bản demo: reset → xếp 7 lệnh seed theo thứ tự Kanban → khai báo INC-A-01 (Line A 09:00–12:00)."""
    test_settings.demo_reset_enabled = True
    morning = datetime(2026, 10, 1, 0, 30, tzinfo=UTC)  # 07:30 giờ +07
    for module in ("src.api.demo", "src.api.scheduling", "src.api.incidents"):
        monkeypatch.setattr(f"{module}.utcnow", lambda: morning)
    sign_in(Role.PLANNER)

    async def run() -> list[tuple]:
        seed = (await client.post("/api/demo/reset")).json()
        ref = {w["id"]: w["ref"] for w in seed["work_orders"]}
        levels = {}
        for card in (await client.get("/api/work-orders")).json():
            r = await client.post(f"/api/work-orders/{card['id']}/schedule")
            levels[ref[card["id"]]] = (r.json().get("risk") or r.json()["detail"]["risk"])["level"]
        # T-036: VIP SEED-05 kịp nhờ đẩy SEED-01 (Thường) → WARN; SEED-07 không kịp 19:00 → BLOCK
        assert levels == {f"SEED-0{i}": "OK" for i in (1, 2, 3, 4, 6)} | {"SEED-05": "WARN", "SEED-07": "BLOCK"}
        inc = seed["incidents"][0]
        body = (
            await client.post(
                "/api/incidents", json={k: inc[k] for k in ("line", "start_at", "est_downtime_min", "note")}
            )
        ).json()
        assert body["proposed_plan_version"]["status"] == "PENDING_APPROVAL"
        return [
            (ref[a["work_order_id"]], a["priority"], a["new"]["line"], a["new"]["start"], a["change_type"], a["sla_ok"])
            for a in body["affected_orders"]
        ]

    first = await run()
    assert first and first == await run()
    assert {r[0] for r in first} >= {"SEED-02"}  # VIP đang chạy trên Line A lúc dừng
    # VIP/Khẩn được xử lý trước đơn Thường
    ranks = [{"VIP": 0, "URGENT": 1, "NORMAL": 2}[r[1]] for r in first if r[4] != "PRIORITY_OVERRIDE"]
    assert ranks == sorted(ranks)


# --- T-034: Scheduler Agent giải thích phương án ---


class EchoLLM:
    """LLM giả: trả `reply`; lưu prompt để kiểm tra dữ liệu gửi đi."""

    def __init__(self, reply: str):
        self.reply, self.calls = reply, []

    def with_structured_output(self, schema):
        return self

    def invoke(self, messages):
        self.calls.append(messages)
        return ScheduleExplanation(text=self.reply)


@pytest.fixture
def use_llm(test_settings):
    def _use(reply: str) -> EchoLLM:
        llm = EchoLLM(reply)
        app.dependency_overrides[get_scheduler_agent] = lambda: SchedulerAgent(llm, test_settings.local_tz)
        return llm

    yield _use
    app.dependency_overrides.pop(get_scheduler_agent, None)


async def test_explanation_from_llm_when_it_matches_data(client, planned, sign_in, use_llm):
    body = (await client.post("/api/incidents", json=incident(start=t(2), downtime=180))).json()
    llm = use_llm(body["explanation"])  # bản deterministic luôn qua validator → coi như câu LLM hợp lệ
    sign_in(Role.SALES, email="sales@adc.test")  # người duyệt cũng xem được giải thích
    r = await client.post("/api/incidents/1/explanation")
    assert r.status_code == 200, r.text
    assert r.json() == {
        "explanation": body["explanation"],
        "source": "LLM",
        "plan_version_id": body["proposed_plan_version"]["id"],
    }
    human = llm.calls[0][1][1]
    assert '"line_dung": "Line A"' in human and "Hạt tiêu" in human
    # Chỉ đọc: phương án và lịch ACTIVE giữ nguyên
    assert (await client.get("/api/incidents/1")).json() == body


async def test_explanation_wrong_numbers_falls_back_to_template(client, planned, use_llm):
    body = (await client.post("/api/incidents", json=incident(start=t(2), downtime=180))).json()
    use_llm(body["explanation"].replace("09:00–12:00", "09:00–12:30"))
    r = (await client.post("/api/incidents/1/explanation")).json()
    assert (r["source"], r["explanation"]) == ("TEMPLATE", body["explanation"])


async def test_explanation_disabled_or_no_affected_orders(client, planned, test_settings):
    test_settings.feature_ai_explanation = False
    await client.post("/api/incidents", json=incident(start=t(12), downtime=60))
    r = (await client.post("/api/incidents/1/explanation")).json()
    assert r == {
        "explanation": "Line A dừng 19:00–20:00 (dự kiến): không có đơn bị ảnh hưởng.",
        "source": "TEMPLATE",
        "plan_version_id": None,
    }


async def test_explanation_auth_and_not_found(client, sign_in):
    assert (await client.post("/api/incidents/1/explanation")).status_code == 401
    sign_in(Role.OPS_MANAGER)
    assert (await client.post("/api/incidents/9/explanation")).status_code == 404


# --- T-035: danh sách sự cố cho màn trước / sau ---


async def test_list_incidents_newest_first_for_every_role(client, sign_in, planned):
    first = (await client.post("/api/incidents", json=incident(start=t(2), downtime=180))).json()
    second = (await client.post("/api/incidents", json=incident(line="B", start=t(8), downtime=60))).json()
    sign_in(Role.SALES, email="sales@adc.test")
    r = await client.get("/api/incidents")
    assert r.status_code == 200
    assert [i["incident_id"] for i in r.json()] == [second["incident_id"], first["incident_id"]]
    # Cùng dữ liệu như GET từng sự cố (phương án mới nhất do sự cố đó tạo)
    assert r.json()[1] == (await client.get("/api/incidents/1")).json()


async def test_list_incidents_empty_and_auth(client, sign_in):
    assert (await client.get("/api/incidents")).status_code == 401
    sign_in(Role.ADMIN)
    assert (await client.get("/api/incidents")).json() == []


# --- T-058: dồn trái sau sự cố (ADR-0011) ---


async def test_incident_plan_pulls_forward_unaffected_order_into_gap(client, sign_in, make_wo, db):
    """Kịch bản demo 03/10: E (A 07–13) sang Line B → C (A 13–20, sẵn hàng) kéo sớm về 12:00 thay vì để A nghỉ."""
    sign_in(Role.PLANNER)
    ret = t(20)
    e = make_wo(Priority.NORMAL, 360, t(0), ret, "E")  # A 0–6 (07:00–13:00 giờ VN)
    x = make_wo(Priority.NORMAL, 300, t(0), ret, "X")  # B 0–5
    y = make_wo(Priority.NORMAL, 240, t(0), ret, "Y")  # B 5–9
    c = make_wo(Priority.NORMAL, 420, t(0), ret, "C")  # A 6–13 (B 9–16 quá ca ngày 22:00)
    for wid in (e, x, y, c):
        assert (await client.post(f"/api/work-orders/{wid}/schedule")).json()["plan_status"] == "ACTIVE"

    body = (await client.post("/api/incidents", json=incident(start=t(2), downtime=180))).json()
    rows = {
        a["work_order_id"]: (a["new"]["line"], h(a["new"]["start"]), h(a["new"]["end"]), a["outcome"], a["change_type"])
        for a in body["affected_orders"]
    }
    assert rows == {
        e: ("B", 9, 15, "MOVED_ALT_LINE", "INCIDENT_DELAY"),
        c: ("A", 5, 12, "PULLED_FORWARD", "LINE_ASSIGNMENT"),  # Line A chạy ngay khi hồi phục
    }
    assert "1 đơn khác được kéo sớm để lấp khe trống" in body["explanation"].splitlines()[0]
    assert db.get(WorkOrder, c).state == WorkOrderState.SCHEDULED  # không bị ảnh hưởng → giữ trạng thái
    assert db.get(WorkOrder, e).state == WorkOrderState.LINE_INCIDENT

    view = (await client.get(f"/api/schedule?version={body['proposed_plan_version']['id']}")).json()
    assert [(s["product_name"], h(s["start"]), h(s["end"])) for s in view["lines"]["A"]] == [("C", 5, 12)]
    assert [(s["product_name"], h(s["start"]), h(s["end"])) for s in view["lines"]["B"]] == [
        ("X", 0, 5),
        ("Y", 5, 9),
        ("E", 9, 15),
    ]
