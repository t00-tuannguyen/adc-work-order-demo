"""ADC-002 T-025 — seed dataset & POST /api/demo/reset."""

from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from sqlalchemy import select

from src.api.demo import seed_day, seed_incidents, seed_work_orders
from src.modules.estimation import EstimateInput, estimate_duration
from src.modules.identity import Role
from src.modules.intake import Ticket, TicketSourceType, WorkOrder
from src.modules.orchestration import AuditLog, PlanVersion
from src.modules.scheduling import (
    Incident,
    LineIncident,
    ScheduleSlot,
    Slot,
    find_affected_slots,
    has_overlap,
    schedule_order,
)
from src.modules.types import Line, Priority

SEED = Path("src/seed")
DAY = date(2026, 10, 5)


@pytest.fixture
def enabled(test_settings):
    test_settings.demo_reset_enabled = True
    return test_settings


# ---- Dữ liệu seed ----


def _estimated(config):
    out = []
    for ref, f in seed_work_orders(SEED, DAY):
        group = config.classify_product(f.product_name)
        fields = {k: getattr(f, k) for k in EstimateInput.__dataclass_fields__ if k != "product_group"}
        out.append((ref, f, estimate_duration(EstimateInput(product_group=group, **fields), config).duration_min))
    return out


def _plan(config, lines=(Line.A, Line.B)):
    slots, sla = [], {}
    for ref, f, duration in _estimated(config):
        p = schedule_order(
            duration_min=duration,
            expected_arrival=f.expected_arrival,
            requested_return=f.requested_return,
            now=f.expected_arrival.replace(hour=0, minute=0),
            slots=slots,
            lines=lines,
        )
        slots.append(Slot(ref, p.line, p.start, p.end))
        sla[ref] = p.sla_ok
    return slots, sla


def test_seed_has_at_least_5_orders_with_every_priority():
    orders = seed_work_orders(SEED, DAY)
    assert len(orders) >= 5
    assert {f.priority for _, f in orders} == set(Priority)
    assert all(f.expected_arrival.date() == DAY for _, f in orders)


def test_seed_spec_example_order_is_180_minutes(config):
    assert dict((ref, d) for ref, _, d in _estimated(config))["SEED-01"] == 180


def test_seed_fits_one_day_on_two_lines_without_sla_risk(config):
    slots, sla = _plan(config)
    assert not has_overlap(slots)
    assert all(sla.values())
    assert all(s.end.date() == DAY for s in slots)


def test_seed_line_a_incident_hits_orders(config):
    slots, _ = _plan(config)
    [inc] = seed_incidents(SEED, DAY)
    incident = Incident(Line(inc["line"]), inc["start_at"], inc["est_downtime_min"])
    affected = find_affected_slots(slots, incident, now=inc["start_at"].replace(hour=0))
    assert inc["line"] == "A" and affected


def test_seed_one_line_mode_has_late_orders(config):
    _, sla = _plan(config, lines=(Line.A,))
    assert not all(sla.values())


def test_seed_day_uses_seed_timezone():
    # 20:00 UTC 04/10 = 03:00 ngày 05/10 giờ +07:00
    assert seed_day(SEED, datetime(2026, 10, 4, 20, 0, tzinfo=UTC)) == DAY


# ---- API ----


@pytest.mark.asyncio
async def test_reset_requires_login(client, enabled):
    assert (await client.post("/api/demo/reset")).status_code == 401


@pytest.mark.asyncio
async def test_reset_disabled_is_404(client, sign_in):
    sign_in(Role.PLANNER)
    assert (await client.post("/api/demo/reset")).status_code == 404


@pytest.mark.asyncio
async def test_reset_never_runs_in_production(client, sign_in, enabled):
    enabled.app_env = "production"
    sign_in(Role.PLANNER)
    assert (await client.post("/api/demo/reset")).status_code == 404


@pytest.mark.asyncio
async def test_reset_replaces_intake_data_with_seed(client, sign_in, db, enabled):
    user = sign_in(Role.PLANNER)
    old = Ticket(source_type=TicketSourceType.MANUAL)
    db.add(old)
    db.flush()
    db.add(WorkOrder(ticket_id=old.id, product_name="cũ"))
    db.commit()

    res = await client.post("/api/demo/reset")

    assert res.status_code == 200
    body = res.json()
    refs = [w["ref"] for w in body["work_orders"]]
    assert refs == [ref for ref, _ in seed_work_orders(SEED, DAY)]
    assert {w["state"] for w in body["work_orders"]} == {"FEASIBILITY_CHECK"}
    assert body["work_orders"][0]["estimated_duration_min"] == 180
    assert [i["ref"] for i in body["incidents"]] == ["INC-A-01"]

    db.expire_all()
    orders = db.scalars(select(WorkOrder)).all()
    assert len(orders) == len(refs) and "cũ" not in {o.product_name for o in orders}
    first = db.get(WorkOrder, body["work_orders"][0]["id"])
    assert (first.product_group, first.config_version) == ("spice", "0.1.0")
    assert first.estimate_breakdown == {
        "setup": 30.0,
        "weight_load": 48.0,
        "volume_load": 36.0,
        "dose_load": 42.0,
        "buffer": 15.6,
    }
    log = db.scalars(select(AuditLog).where(AuditLog.action == "DEMO_RESET")).one()
    assert log.actor_id == user.id and log.payload["work_orders"] == len(refs)


@pytest.mark.asyncio
async def test_reset_twice_gives_identical_data(client, sign_in, db, enabled):
    sign_in(Role.SALES)

    def snapshot(body):
        return [(w["ref"], w["state"], w["estimated_duration_min"]) for w in body["work_orders"]]

    first = (await client.post("/api/demo/reset")).json()
    second = (await client.post("/api/demo/reset")).json()
    assert snapshot(first) == snapshot(second)
    assert first["incidents"] == second["incidents"]
    db.expire_all()
    assert len(db.scalars(select(WorkOrder)).all()) == len(second["work_orders"])


@pytest.mark.asyncio
async def test_reset_clears_schedule(client, sign_in, db, enabled, monkeypatch):
    """ADC-003 T-028: plan version và slot gắn với work order cũ cũng bị xóa. ADC-004 T-031: cả sự cố.

    Giờ cố định 07:30 (+07): theo giờ thật đơn seed có thể đã trễ → BLOCK (T-036).
    """
    morning = datetime(2026, 10, 1, 0, 30, tzinfo=UTC)
    for module in ("src.api.demo", "src.api.scheduling", "src.api.incidents"):
        monkeypatch.setattr(f"{module}.utcnow", lambda: morning)
    sign_in(Role.PLANNER)
    first = (await client.post("/api/demo/reset")).json()
    for w in first["work_orders"][:2]:
        assert (await client.post(f"/api/work-orders/{w['id']}/schedule")).status_code == 200
    inc = first["incidents"][0]
    body = {k: inc[k] for k in ("line", "start_at", "est_downtime_min", "note")}
    assert (await client.post("/api/incidents", json=body)).status_code == 201
    assert (await client.post("/api/demo/reset")).status_code == 200
    db.expire_all()
    assert db.scalars(select(PlanVersion)).all() == []
    assert db.scalars(select(ScheduleSlot)).all() == []
    assert db.scalars(select(LineIncident)).all() == []
    assert (await client.get("/api/schedule")).json()["plan_version"] is None
