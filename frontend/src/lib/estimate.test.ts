// node --test — ADC-002 T-026: hiển thị thời lượng & breakdown
import assert from "node:assert/strict";
import { test } from "node:test";

import { breakdownRows, type EstimateResult, formatDuration, formatMinutes } from "./estimate.ts";

const SPEC: EstimateResult = {
  duration_min: 180,
  breakdown: { setup: 30, weight_load: 48, volume_load: 36, dose_load: 42, buffer: 15.6 },
  config_version: "0.1.0",
};

test("thời lượng dạng giờ-phút như đặc tả (3h00)", () => {
  assert.equal(formatDuration(180), "3h00");
  assert.equal(formatDuration(45), "0h45");
  assert.equal(formatDuration(615), "10h15");
});

test("breakdown theo thứ tự công thức + phần làm tròn để tổng khớp thời lượng", () => {
  const rows = breakdownRows(SPEC);
  assert.deepEqual(
    rows.map((r) => r.key),
    ["setup", "weight_load", "volume_load", "dose_load", "buffer", "rounding"],
  );
  assert.equal(rows.at(-1)?.minutes, 8.4);
  assert.equal(Math.round(rows.reduce((s, r) => s + r.minutes, 0) * 100) / 100, 180);
});

test("không có dòng làm tròn khi tổng đã đúng bội số", () => {
  const exact = { ...SPEC, duration_min: 171.6 };
  assert.ok(!breakdownRows(exact).some((r) => r.key === "rounding"));
});

test("phút giữ 1 chữ số thập phân", () => {
  assert.equal(formatMinutes(48), "48′");
  assert.equal(formatMinutes(15.6), "15.6′");
  assert.equal(formatMinutes(8.399999), "8.4′");
});
