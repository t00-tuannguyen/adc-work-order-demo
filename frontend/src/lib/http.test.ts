// node --test — BUG-001: lỗi không có `detail` (500 text thuần qua HTTP/2) vẫn phải có câu báo lỗi
import assert from "node:assert/strict";
import { test } from "node:test";

import { fallbackMessage } from "./http.ts";

test("statusText rỗng (HTTP/2) → câu báo lỗi không rỗng, có mã HTTP", () => {
  assert.equal(fallbackMessage(500, ""), "Máy chủ lỗi (HTTP 500). Thử lại sau.");
  assert.equal(fallbackMessage(400, ""), "Yêu cầu không hợp lệ (HTTP 400).");
});

test("statusText có sẵn (HTTP/1.1) → giữ nguyên", () => {
  assert.equal(fallbackMessage(500, "Internal Server Error"), "Internal Server Error");
});
