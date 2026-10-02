// node --test — ADC-008 TC1, TC2, TC3, TC4, TC5, TC6, TC8 (phần điều hướng ở frontend)
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  can,
  googleStartUrl,
  initials,
  landingFor,
  loginErrorMessage,
  loginUrl,
  type Me,
  safeNext,
} from "./roles.ts";

const me = (over: Partial<Me>): Me => ({
  id: "u1",
  name: "Nguyễn An",
  email: "an@adc.test",
  avatar_url: null,
  role: null,
  status: "PENDING",
  requested_role: null,
  ...over,
});

test("TC1: PENDING chưa có yêu cầu vai trò → hoàn tất đăng ký", () => {
  assert.equal(landingFor(me({})), "/signup/complete");
});

test("TC2: PENDING (đã gửi yêu cầu) → chờ cấp quyền", () => {
  assert.equal(landingFor(me({ requested_role: "SALES" })), "/pending");
});

test("TC3: ACTIVE → trang theo vai trò", () => {
  assert.equal(landingFor(me({ status: "ACTIVE", role: "SALES" })), "/sales");
  assert.equal(landingFor(me({ status: "ACTIVE", role: "PLANNER" })), "/planner");
  assert.equal(landingFor(me({ status: "ACTIVE", role: "OPS_MANAGER" })), "/ops");
  assert.equal(landingFor(me({ status: "ACTIVE", role: "ADMIN" })), "/admin/users");
});

test("DISABLED → màn đăng nhập kèm lỗi", () => {
  assert.equal(landingFor(me({ status: "DISABLED", role: "SALES" })), "/login?error=ACCOUNT_DISABLED");
});

test("TC4/TC5/TC6: thông báo lỗi đăng nhập", () => {
  assert.equal(loginErrorMessage(null), null);
  assert.equal(loginErrorMessage("CANCELLED")?.tone, "info");
  assert.match(loginErrorMessage("DOMAIN_NOT_ALLOWED")!.title, /tên miền/);
  assert.match(loginErrorMessage("STATE_MISMATCH")!.detail, /thử lại/);
  assert.equal(loginErrorMessage("SOMETHING_NEW")?.tone, "error");
});

test("TC8: next chỉ nhận đường dẫn nội bộ", () => {
  assert.equal(safeNext("/planner?draft=1"), "/planner?draft=1");
  for (const bad of ["//evil.com", "https://evil.com", "/\\evil", "planner", "", null, undefined]) {
    assert.equal(safeNext(bad), null);
  }
  assert.equal(loginUrl("/ops"), "/login?next=%2Fops");
  assert.equal(loginUrl("//evil.com"), "/login");
  assert.equal(googleStartUrl("/ops"), "/auth/google/start?next=%2Fops");
});

test("TC9: PLANNER không duyệt plan version; SALES và OPS_MANAGER được", () => {
  assert.equal(can("PLANNER", "APPROVE_PLAN_VERSION"), false);
  assert.equal(can("SALES", "APPROVE_PLAN_VERSION"), true);
  assert.equal(can("OPS_MANAGER", "APPROVE_PLAN_VERSION"), true);
  assert.equal(can(null, "VIEW_BOARD"), false);
});

test("initials", () => {
  assert.equal(initials("Nguyễn Thu Hà", "x@y"), "NH");
  assert.equal(initials("", "admin@adc.test"), "AD");
});
