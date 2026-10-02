// node --test — ADC-001 T-021: hàm thuần của màn tiếp nhận (TC3, TC8, TC13 phía frontend)
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  afterUploadPath,
  changedFields,
  confirmPayload,
  errorMessage,
  errorsByField,
  FIELD_DEFS,
  fieldKeyOf,
  formatVN,
  fromLocalInput,
  pickPdfFiles,
  pollDelay,
  sourcePdfOutcome,
  stepStates,
  toForm,
  toLocalInput,
  type WorkOrderFields,
} from "./intake.ts";

const FIELDS: WorkOrderFields = {
  product_name: "Bột ớt",
  quantity: 120,
  pkg_length_cm: 40,
  pkg_width_cm: 30,
  pkg_height_cm: 25,
  pkg_weight_kg: 8,
  required_dose_kgy: null,
  priority: "URGENT",
  expected_arrival: "2026-10-02T02:00:00+00:00",
  requested_return: null,
};

test("giờ server (UTC) hiển thị và nhập theo giờ Việt Nam", () => {
  assert.equal(toLocalInput("2026-10-02T02:00:00+00:00"), "2026-10-02T09:00");
  assert.equal(toLocalInput("2026-10-01T20:30:00+00:00"), "2026-10-02T03:30"); // qua ngày
  assert.equal(toLocalInput(null), "");
  assert.equal(toLocalInput("không phải ngày"), "");
  assert.equal(fromLocalInput("2026-10-02T16:00"), "2026-10-02T16:00:00+07:00");
  assert.equal(fromLocalInput(""), null);
  assert.equal(formatVN("2026-10-02T09:00:00+00:00"), "16:00 02/10/2026");
});

test("form không đổi → PATCH rỗng; chỉ gửi cột đã đổi, đúng kiểu", () => {
  const form = toForm(FIELDS);
  assert.deepEqual(changedFields(FIELDS, form), {});
  const edited = { ...form, required_dose_kgy: "10", requested_return: "2026-10-02T16:00", quantity: " 120 " };
  assert.deepEqual(changedFields(FIELDS, edited), {
    required_dose_kgy: 10,
    requested_return: "2026-10-02T16:00:00+07:00",
  });
  assert.deepEqual(changedFields(FIELDS, { ...form, pkg_weight_kg: "8,5" }), { pkg_weight_kg: 8.5 });
  assert.deepEqual(changedFields(FIELDS, { ...form, product_name: "" }), { product_name: null });
});

test("TC13: xác nhận trường gửi lại giá trị hiện tại (quy cách gửi đủ 3 cột)", () => {
  const dims = FIELD_DEFS.find((d) => d.key === "package_dimensions_cm")!;
  assert.deepEqual(confirmPayload(dims, toForm(FIELDS)), { pkg_length_cm: 40, pkg_width_cm: 30, pkg_height_cm: 25 });
});

test("TC3/TC8: lỗi theo cột gộp về trường trích xuất", () => {
  assert.equal(fieldKeyOf("pkg_width_cm"), "package_dimensions_cm");
  assert.deepEqual(
    errorsByField([
      { field: "pkg_length_cm", code: "MISSING" },
      { field: "pkg_height_cm", code: "MISSING" },
      { field: "requested_return", code: "RETURN_NOT_AFTER_ARRIVAL" },
    ]),
    { package_dimensions_cm: "MISSING", requested_return: "RETURN_NOT_AFTER_ARRIVAL" },
  );
});

test("8 trường, mỗi cột work order thuộc đúng 1 trường", () => {
  assert.equal(FIELD_DEFS.length, 8);
  const cols = FIELD_DEFS.flatMap((d) => d.columns);
  assert.deepEqual([...cols].sort(), Object.keys(FIELDS).sort());
});

test("tiến độ 4 bước", () => {
  assert.deepEqual(stepStates({ step: "UPLOADED", status: "QUEUED" }), ["active", "todo", "todo", "todo"]);
  assert.deepEqual(stepStates({ step: "DETECTING", status: "RUNNING" }), ["done", "done", "active", "todo"]);
  assert.deepEqual(stepStates({ step: "DONE", status: "SUCCEEDED" }), ["done", "done", "done", "done"]);
  assert.deepEqual(stepStates({ step: "FAILED", status: "FAILED" }, "READING"), ["done", "failed", "todo", "todo"]);
});

test("lệnh nhập tay: thiếu trường không bảo đi hỏi nguồn", () => {
  assert.equal(errorMessage("MISSING", true), "Bắt buộc — nhập giá trị.");
  assert.match(errorMessage("MISSING", false), /hỏi khách/);
  assert.equal(errorMessage("RETURN_NOT_AFTER_ARRIVAL", true), "Giờ trả phải sau giờ hàng đến.");
});

test("pickPdfFiles: nhận nhiều PDF, loại file không phải PDF / quá dung lượng / trùng", () => {
  const MB = 1024 * 1024;
  const a = { name: "a.pdf", size: MB, type: "application/pdf" };
  const b = { name: "b.PDF", size: 2 * MB, type: "" };
  const big = { name: "big.pdf", size: 11 * MB, type: "application/pdf" };
  const img = { name: "x.png", size: MB, type: "image/png" };
  const { accepted, rejected } = pickPdfFiles([a, b, big, img, { ...a }], [], 10);
  assert.deepEqual(accepted, [a, b]);
  assert.deepEqual(rejected, [
    { name: "big.pdf", reason: "vượt 10 MB" },
    { name: "x.png", reason: "chỉ nhận file PDF" },
  ]);
  assert.deepEqual(pickPdfFiles([a], [a], 10).accepted, []);
});

test("sau upload: lệnh DRAFT mở màn xác nhận, lệnh tự tạo về Kanban", () => {
  assert.equal(afterUploadPath({ id: "w1", state: "DRAFT" }), "/intake/w1");
  assert.equal(afterUploadPath({ id: "w2", state: "SCHEDULED" }), "/board");
  assert.equal(afterUploadPath({ id: "w3", state: "FEASIBILITY_CHECK" }), "/board");
});

test("hỏi trạng thái job giãn dần, tối đa 5s", () => {
  assert.deepEqual([0, 1, 2, 3, 4, 10].map((n) => pollDelay(n)), [1000, 1500, 2250, 3375, 5000, 5000]);
});

test("PDF gốc: 404 → báo file đã mất (filesystem tạm, ADR-0012), lỗi khác → báo lỗi tải", () => {
  assert.equal(sourcePdfOutcome(200), "ok");
  assert.equal(sourcePdfOutcome(404), "missing");
  assert.equal(sourcePdfOutcome(500), "error");
  assert.equal(sourcePdfOutcome(403), "error");
});
