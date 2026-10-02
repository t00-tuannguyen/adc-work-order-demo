// node --test — ADC-004 T-031: form khai báo sự cố
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  type AffectedOrder,
  compareVersions,
  defaultIncidentForm,
  downtimesOf,
  finishShiftMin,
  incidentDays,
  downtimeEnd,
  downtimeMin,
  type IncidentForm,
  incidentPayload,
  proposalHref,
  slotTimeText,
  timeText,
  validateIncident,
} from "./incident.ts";

// Kịch bản seed INC-A-01: Line A dừng 09:00–12:00
const SEED: IncidentForm = { line: "A", start: "2026-10-02T09:00", hours: "3", minutes: "0", note: " Dừng line A " };

test("payload đúng contract: giờ VN +07:00, phút dừng, ghi chú đã trim", () => {
  assert.deepEqual(incidentPayload(SEED), {
    line: "A",
    start_at: "2026-10-02T09:00:00+07:00",
    est_downtime_min: 180,
    note: "Dừng line A",
  });
});

test("xem trước giờ hồi phục 12:00 giờ VN", () => {
  assert.equal(downtimeEnd(SEED), "2026-10-02T05:00:00.000Z");
});

test("thời gian dừng: giờ + phút, ô trống = 0, chấp nhận 0 phút", () => {
  assert.equal(downtimeMin({ hours: "1", minutes: "30" }), 90);
  assert.equal(downtimeMin({ hours: "", minutes: "45" }), 45);
  assert.equal(downtimeMin({ hours: "", minutes: "" }), 0);
  assert.equal(downtimeMin({ hours: "1.5", minutes: "" }), null);
  assert.equal(downtimeMin({ hours: "-1", minutes: "" }), null);
});

test("validate: thiếu giờ bắt đầu, vượt 7 ngày, ghi chú quá dài → không có payload", () => {
  const cases: [Partial<IncidentForm>, string][] = [
    [{ start: "" }, "start"],
    [{ hours: "168", minutes: "1" }, "downtime"],
    [{ hours: "abc" }, "downtime"],
    [{ note: "x".repeat(501) }, "note"],
  ];
  for (const [patch, field] of cases) {
    const form = { ...SEED, ...patch };
    assert.ok(field in validateIncident(form), field);
    assert.equal(incidentPayload(form), null);
  }
  assert.deepEqual(validateIncident({ ...SEED, hours: "168", minutes: "0" }), {});
});

test("mặc định: Line A, dừng 3 giờ, bắt đầu làm tròn xuống 15 phút theo giờ VN", () => {
  const f = defaultIncidentForm(Date.parse("2026-10-02T01:52:10Z"));
  assert.equal(f.line, "A");
  assert.equal(f.start, "2026-10-02T08:45");
  assert.equal(downtimeMin(f), 180);
});

test("link phương án đề xuất mở đúng ngày (giờ VN) + version", () => {
  const pv = {
    id: 7,
    status: "PENDING_APPROVAL" as const,
    parent_version_id: 6,
    trigger: "INCIDENT" as const,
    requires_approval: true,
    created_by: "u",
    created_at: "2026-10-02T00:00:00Z",
    slot_count: 5,
  };
  assert.equal(
    proposalHref({ start_at: "2026-10-01T18:30:00Z", proposed_plan_version: pv }),
    "/schedule?date=2026-10-02&version=7",
  );
  assert.equal(proposalHref({ start_at: "2026-10-01T18:30:00Z", proposed_plan_version: null }), null);
});

test("slot cùng ngày sự cố chỉ hiện giờ; dời sang ngày khác thì kèm ngày", () => {
  const at = "2026-10-03T09:00:00+07:00";
  assert.equal(slotTimeText({ line: "A", start: "2026-10-03T00:00:00Z", end: "2026-10-03T06:30:00Z" }, at), "A · 07:00–13:30");
  assert.equal(
    slotTimeText({ line: "A", start: "2026-10-04T03:45:00Z", end: "2026-10-04T10:15:00Z" }, at),
    "A · 10:45–17:15 04/10",
  );
});

// ---------- T-035: màn so sánh trước / sau ----------

const PV = {
  id: 8,
  status: "PENDING_APPROVAL" as const,
  parent_version_id: 6,
  trigger: "INCIDENT" as const,
  requires_approval: true,
  created_by: "u",
  created_at: "2026-10-02T15:00:00Z",
  slot_count: 6,
};
const MOVED: AffectedOrder = {
  work_order_id: "abc",
  product_name: "Dưa hấu",
  priority: "NORMAL",
  state: "LINE_INCIDENT",
  outcome: "DELAYED",
  change_type: "INCIDENT_DELAY",
  old: { line: "A", start: "2026-10-03T00:00:00Z", end: "2026-10-03T06:30:00Z" },
  new: { line: "A", start: "2026-10-04T03:45:00Z", end: "2026-10-04T10:15:00Z" },
  requested_return: "2026-10-06T00:00:00Z",
  sla_ok: true,
  reason: "",
};

test("so sánh: trước = version cha, sau = phương án; chưa có phương án → chỉ lịch ACTIVE", () => {
  assert.deepEqual(compareVersions({ proposed_plan_version: PV }), { before: "6", after: "8" });
  assert.deepEqual(compareVersions({ proposed_plan_version: { ...PV, parent_version_id: null } }), {
    before: "current",
    after: "8",
  });
  assert.deepEqual(compareVersions({ proposed_plan_version: null }), { before: "current", after: null });
});

test("ngày cần xem: ngày dừng + ngày đơn được dời tới (giờ VN), không trùng", () => {
  const inc = { start_at: "2026-10-03T02:00:00Z", end_at: "2026-10-03T05:00:00Z", affected_orders: [MOVED] };
  assert.deepEqual(incidentDays(inc), ["2026-10-03", "2026-10-04"]);
});

test("khung dừng tô trên timeline: bỏ sự cố 0 phút, nhãn có số sự cố", () => {
  const incs = [
    { incident_id: 1, line: "A" as const, start_at: "2026-10-03T02:00:00Z", end_at: "2026-10-03T05:00:00Z" },
    { incident_id: 2, line: "B" as const, start_at: "2026-10-03T06:00:00Z", end_at: "2026-10-03T06:00:00Z" },
  ];
  assert.deepEqual(downtimesOf(incs), [
    { line: "A", start: incs[0].start_at, end: incs[0].end_at, label: "Sự cố #1: Line A dừng 09:00–12:00" },
  ]);
});

test("giờ xong lệch so với lịch cũ (phút)", () => {
  assert.equal(finishShiftMin(MOVED), 27 * 60 + 45);
  assert.equal(finishShiftMin({ old: MOVED.old, new: { ...MOVED.old, line: "B" } }), 0);
});

test("giờ xong kèm ngày khi khác ngày sự cố", () => {
  assert.equal(timeText("2026-10-03T06:30:00Z", "2026-10-03T02:00:00Z"), "13:30");
  assert.equal(timeText("2026-10-04T10:15:00Z", "2026-10-03T02:00:00Z"), "17:15 04/10");
});
