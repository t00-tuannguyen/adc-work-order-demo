// node --test — ADC-003 T-029: nhóm cột Kanban, thứ tự ưu tiên, bước vận hành
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  blockPosition,
  canDeleteDraft,
  canEditManually,
  manualPreview,
  COLUMNS,
  columnOf,
  groupByColumn,
  hhmm,
  markerPosition,
  NEXT_STEP,
  returnLabel,
  scheduleQueue,
  shiftDay,
  scheduleHref,
  slotText,
  STATE_LABEL,
  todayVN,
  type WorkOrderCard,
  type WorkOrderState,
} from "./board.ts";

function card(id: string, over: Partial<WorkOrderCard> = {}): WorkOrderCard {
  return {
    id,
    product_name: "Bột ớt",
    priority: "NORMAL",
    state: "FEASIBILITY_CHECK",
    review_status: "AUTO_ACCEPTED",
    expected_arrival: "2026-10-01T01:00:00Z",
    requested_return: "2026-10-01T09:00:00Z",
    estimated_duration_min: 180,
    slot: null,
    ...over,
  };
}

const SLOT = {
  line: "A" as const,
  start: "2026-10-01T02:00:00Z",
  end: "2026-10-01T05:00:00Z",
  sla_ok: true,
  plan_version: 1,
  plan_status: "ACTIVE" as const,
};

test("mọi trạng thái có nhãn và thuộc đúng 1 cột", () => {
  const keys = new Set(COLUMNS.map((c) => c.key));
  for (const state of Object.keys(STATE_LABEL) as WorkOrderState[]) {
    assert.ok(keys.has(columnOf(card("x", { state }))), state);
  }
});

test("cột theo nhóm trạng thái", () => {
  assert.equal(columnOf(card("a", { state: "DRAFT" })), "draft");
  assert.equal(columnOf(card("a", { state: "FEASIBILITY_CHECK" })), "draft");
  assert.equal(columnOf(card("a", { state: "SCHEDULED", slot: SLOT })), "scheduled");
  assert.equal(columnOf(card("a", { state: "IN_IRRADIATION", slot: SLOT })), "irradiating");
  assert.equal(columnOf(card("a", { state: "CLOSED", slot: SLOT })), "done");
  assert.equal(columnOf(card("a", { state: "ESCALATED_TO_BUSINESS" })), "escalated");
});

test("lịch trễ giờ trả → cột Rủi ro SLA dù đang chờ duyệt", () => {
  const late = { ...SLOT, sla_ok: false, plan_status: "PENDING_APPROVAL" as const };
  assert.equal(columnOf(card("a", { state: "PENDING_APPROVAL", slot: late })), "sla_risk");
  assert.equal(columnOf(card("a", { state: "PENDING_APPROVAL", slot: SLOT })), "approval");
  // Đã trả rồi thì không còn là rủi ro
  assert.equal(columnOf(card("a", { state: "RETURNED", slot: late })), "done");
});

test("trong cột: VIP → Khẩn → Thường, cùng mức giờ trả sớm trước", () => {
  const cards = [
    card("n1", { priority: "NORMAL", requested_return: "2026-10-01T05:00:00Z" }),
    card("v2", { priority: "VIP", requested_return: "2026-10-01T10:00:00Z" }),
    card("u1", { priority: "URGENT" }),
    card("v1", { priority: "VIP", requested_return: "2026-10-01T06:00:00Z" }),
  ];
  assert.deepEqual(
    groupByColumn(cards).draft.map((c) => c.id),
    ["v1", "v2", "u1", "n1"],
  );
});

test("hàng đợi xếp lịch chỉ gồm đơn FEASIBILITY_CHECK có ước tính", () => {
  const cards = [
    card("a", { priority: "NORMAL" }),
    card("b", { priority: "VIP" }),
    card("c", { estimated_duration_min: null }),
    card("d", { state: "DRAFT" }),
    card("e", { state: "SCHEDULED", slot: SLOT }),
  ];
  assert.deepEqual(
    scheduleQueue(cards).map((c) => c.id),
    ["b", "a"],
  );
});

test("bước vận hành đi đúng chuỗi SCHEDULED → CLOSED", () => {
  const chain: WorkOrderState[] = ["SCHEDULED"];
  for (let s = NEXT_STEP.SCHEDULED; s; s = NEXT_STEP[s.to]) chain.push(s.to);
  assert.deepEqual(chain, [
    "SCHEDULED",
    "WAITING_ARRIVAL",
    "READY_FOR_IRRADIATION",
    "IN_IRRADIATION",
    "COMPLETED_IRRADIATION",
    "READY_FOR_RETURN",
    "RETURNED",
    "CLOSED",
  ]);
  assert.equal(NEXT_STEP.FEASIBILITY_CHECK, undefined);
});

test("giờ hiển thị theo giờ Việt Nam", () => {
  assert.equal(hhmm("2026-10-01T02:00:00Z"), "09:00");
  assert.equal(slotText(SLOT), "Line A · 09:00–12:00");
});

test("T-030: khối trên trục 24h theo giờ Việt Nam", () => {
  // 09:00–12:00 giờ VN ngày 01/10 = 02:00–05:00Z
  assert.deepEqual(blockPosition("2026-10-01T02:00:00Z", "2026-10-01T05:00:00Z", "2026-10-01"), {
    left: 37.5,
    width: 12.5,
    clippedStart: false,
    clippedEnd: false,
  });
  assert.equal(blockPosition("2026-10-01T02:00:00Z", "2026-10-01T05:00:00Z", "2026-10-02"), null);
});

test("T-030: khối qua nửa đêm bị cắt ở 2 ngày", () => {
  // 22:00 → 02:00 giờ VN
  const start = "2026-10-01T15:00:00Z";
  const end = "2026-10-01T19:00:00Z";
  assert.deepEqual(blockPosition(start, end, "2026-10-01"), {
    left: 91.67,
    width: 8.33,
    clippedStart: false,
    clippedEnd: true,
  });
  assert.deepEqual(blockPosition(start, end, "2026-10-02"), { left: 0, width: 8.33, clippedStart: true, clippedEnd: false });
});

test("T-030: vạch giờ trả và ngày", () => {
  assert.equal(markerPosition("2026-10-01T09:00:00Z", "2026-10-01"), 66.67); // 16:00 VN
  assert.equal(markerPosition("2026-10-03T09:00:00Z", "2026-10-01"), null);
  assert.equal(markerPosition(null, "2026-10-01"), null);
  assert.equal(todayVN(Date.parse("2026-09-30T18:30:00Z")), "2026-10-01"); // 01:30 VN
  assert.equal(shiftDay("2026-10-31", 1), "2026-11-01");
  assert.equal(shiftDay("2026-10-01", -1), "2026-09-30");
});

test("BR-15: chỉ đơn chưa chạy, có thời lượng, không có đề xuất chờ duyệt mới sửa tay được", () => {
  const slot = { line: "A" as const, start: "", end: "", sla_ok: true, plan_version: 1, plan_status: "ACTIVE" as const };
  assert.equal(canEditManually({ state: "FEASIBILITY_CHECK", estimated_duration_min: 180, slot: null }), true);
  assert.equal(canEditManually({ state: "SCHEDULED", estimated_duration_min: 180, slot }), true);
  assert.equal(canEditManually({ state: "RESCHEDULE_REQUIRED", estimated_duration_min: 180, slot: null }), true);
  assert.equal(canEditManually({ state: "FEASIBILITY_CHECK", estimated_duration_min: null, slot: null }), false);
  assert.equal(canEditManually({ state: "IN_IRRADIATION", estimated_duration_min: 180, slot }), false);
  assert.equal(
    canEditManually({ state: "SCHEDULED", estimated_duration_min: 180, slot: { ...slot, plan_status: "PENDING_APPROVAL" } }),
    false,
  );
});

test("T-055: chỉ lệnh nháp hiện nút xóa", () => {
  assert.equal(canDeleteDraft({ state: "DRAFT" }), true);
  assert.equal(canDeleteDraft({ state: "FEASIBILITY_CHECK" }), false);
  assert.equal(canDeleteDraft({ state: "SCHEDULED" }), false);
});

test("BR-15: xem trước giờ xong và số phút trễ", () => {
  const ok = manualPreview("2030-01-01T09:00:00+07:00", 180, "2030-01-01T16:00:00+07:00");
  assert.deepEqual(ok, { end: "2030-01-01T05:00:00.000Z", slaOk: true, lateMin: 0 });
  const late = manualPreview("2030-01-01T14:00:00+07:00", 180, "2030-01-01T16:00:00+07:00");
  assert.equal(late?.slaOk, false);
  assert.equal(late?.lateMin, 60);
  assert.equal(manualPreview(null, 180, null), null);
});

test("thẻ Kanban → lịch: đúng ngày giờ VN, kèm version khi là đề xuất", () => {
  const slot = { start: "2026-10-03T23:00:00Z", plan_version: 4, plan_status: "ACTIVE" as const };
  assert.equal(scheduleHref("w1", slot), "/schedule?date=2026-10-04&wo=w1"); // 06:00 04/10 VN
  assert.equal(
    scheduleHref("w1", { ...slot, plan_status: "PENDING_APPROVAL" as const }),
    "/schedule?date=2026-10-04&wo=w1&version=4",
  );
});

test("khối lịch ghi giờ trả, khác ngày đang xem thì kèm ngày", () => {
  assert.equal(returnLabel("2026-10-04T09:00:00Z", "2026-10-04"), "trả 16:00");
  assert.equal(returnLabel("2026-10-05T10:00:00Z", "2026-10-04"), "trả 17:00 05/10");
  assert.equal(returnLabel(null, "2026-10-04"), null);
});
