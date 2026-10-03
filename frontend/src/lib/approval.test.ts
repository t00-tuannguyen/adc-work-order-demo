// node --test — ADC-006 T-042: nhãn loại thay đổi, nguồn đề xuất, lý do từ chối bắt buộc
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  affectedCount,
  approvalLabels,
  compareVersions,
  diffDays,
  type PlanDiff,
  rejectReasonError,
  sourceLabel,
  spanText,
} from "./approval.ts";

const version = (trigger: PlanDiff["plan_version"]["trigger"]) => ({
  id: 5,
  status: "PENDING_APPROVAL" as const,
  parent_version_id: 4,
  trigger,
  requires_approval: true,
  created_by: "u",
  created_at: "2030-01-01T00:00:00Z",
  slot_count: 4,
});

test("nguồn đề xuất theo trigger", () => {
  assert.equal(sourceLabel({ plan_version: version("INCIDENT"), incident_id: 3 }), "Sự cố line #3");
  assert.equal(sourceLabel({ plan_version: version("NEW_ORDER"), incident_id: null }), "Đơn mới");
  assert.equal(sourceLabel({ plan_version: version("MANUAL"), incident_id: null }), "Điều phối xếp tay");
});

test("chỉ liệt kê loại cần duyệt, không trùng, theo thứ tự cố định", () => {
  const labels = approvalLabels([
    { change_type: "PRIORITY_OVERRIDE", needs_approval: true },
    { change_type: "LINE_ASSIGNMENT", needs_approval: false },
    { change_type: "INCIDENT_DELAY", needs_approval: true },
    { change_type: "PRIORITY_OVERRIDE", needs_approval: true },
  ]);
  assert.deepEqual(labels, ["Hoãn do sự cố", "Đổi ưu tiên"]);
  assert.equal(affectedCount([{ work_order_id: "a" }, { work_order_id: "b" }, { work_order_id: "a" }]), 2);
});

test("khung giờ theo giờ Việt Nam, đơn chưa có lịch", () => {
  assert.equal(spanText({ line: "B", start: "2030-01-01T02:00:00Z", end: "2030-01-01T05:00:00Z" }), "Line B 09:00–12:00");
  assert.equal(spanText(null), "Chưa có lịch");
});

test("từ chối bắt buộc ghi lý do", () => {
  assert.equal(rejectReasonError("  "), "Phải ghi lý do từ chối.");
  assert.equal(rejectReasonError("x".repeat(501)), "Lý do tối đa 500 ký tự.");
  assert.equal(rejectReasonError("Khách không đồng ý"), null);
});

test("so sánh: trước = lịch nền, sau = version; chưa có nền → current", () => {
  assert.deepEqual(compareVersions({ plan_version: version("INCIDENT"), base_version_id: 4 }), {
    before: "4",
    after: "5",
  });
  assert.deepEqual(compareVersions({ plan_version: version("NEW_ORDER"), base_version_id: null }), {
    before: "current",
    after: "5",
  });
});

test("ngày xem: gộp slot cũ / mới theo giờ VN, không trùng, có mốc thêm", () => {
  const changes = [
    {
      old: { line: "A" as const, start: "2026-10-03T00:00:00Z", end: "2026-10-03T06:30:00Z" },
      new: { line: "A" as const, start: "2026-10-04T03:45:00Z", end: "2026-10-04T10:15:00Z" },
    },
    { old: null, new: { line: "B" as const, start: "2026-10-03T18:00:00Z", end: "2026-10-03T20:00:00Z" } },
  ];
  // 18:00Z 03/10 = 01:00 04/10 giờ VN
  assert.deepEqual(diffDays(changes), ["2026-10-03", "2026-10-04"]);
  assert.deepEqual(diffDays(changes, ["2026-10-01T20:00:00Z"]), ["2026-10-02", "2026-10-03", "2026-10-04"]);
});
