// node --test — ADC-005 T-039: banner rủi ro, 409 BLOCK, hàng đợi escalation
import assert from "node:assert/strict";
import { test } from "node:test";

import { blockedRisk, canCheckRisk, delayText, isOpen, RISK_NOTICE } from "./risk.ts";

test("delayText đổi phút trễ sang giờ/phút", () => {
  assert.equal(delayText(45), "45 phút");
  assert.equal(delayText(120), "2 giờ");
  assert.equal(delayText(135), "2 giờ 15 phút");
});

test("blockedRisk chỉ nhận detail 409 NEW_ORDER_BLOCKED", () => {
  const risk = { level: "BLOCK", reasons: ["Không kịp"], earliest_feasible_return: "2030-01-01T12:00:00Z" };
  assert.deepEqual(blockedRisk({ error_code: "NEW_ORDER_BLOCKED", message: "x", risk }), risk);
  assert.equal(blockedRisk("Lịch đã được người khác cập nhật"), null);
  assert.equal(blockedRisk({ error_code: "OTHER", risk }), null);
  assert.equal(blockedRisk(null), null);
});

test("banner: vàng cho WARN, đỏ cho BLOCK", () => {
  assert.equal(RISK_NOTICE.WARN, "notice notice-warn");
  assert.equal(RISK_NOTICE.BLOCK, "notice notice-error");
});

test("chỉ kiểm tra rủi ro đơn chưa xếp hoặc bị chặn; escalation mở = OPEN + DRAFTED", () => {
  assert.ok(canCheckRisk("FEASIBILITY_CHECK") && canCheckRisk("BLOCK_NEW_ORDER"));
  assert.ok(!canCheckRisk("SCHEDULED"));
  assert.ok(isOpen({ status: "OPEN" }) && isOpen({ status: "DRAFTED" }) && !isOpen({ status: "APPROVED" }));
});
