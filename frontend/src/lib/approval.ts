// Phê duyệt plan version & lịch sử trạng thái — ADC-006 (T-041, T-042). Kiểu + hàm thuần, test bằng node --test.
// Contract: specs/api-contracts.md §6.

import { hhmm, type Line, type PlanVersion, todayVN, type WorkOrderState } from "./board.ts";
import type { Priority } from "./intake.ts";

export type ChangeType =
  | "LINE_ASSIGNMENT"
  | "RETURN_TIME_CHANGE"
  | "INCIDENT_DELAY"
  | "PRIORITY_OVERRIDE"
  | "ACCEPT_DURING_WARNING";

export interface Span {
  line: Line;
  start: string;
  end: string;
}

export interface PlanChange {
  work_order_id: string;
  product_name: string | null;
  priority: Priority | null;
  state: WorkOrderState;
  requested_return: string | null;
  change_type: ChangeType;
  needs_approval: boolean;
  old: Span | null;
  new: Span;
  sla_ok: boolean;
  reason: string | null;
}

export interface PlanDiff {
  plan_version: PlanVersion;
  base_version_id: number | null;
  base_changed: boolean;
  incident_id: number | null;
  changes: PlanChange[];
  decided_by: string | null;
  decided_by_name: string | null;
  decided_at: string | null;
  comment: string | null;
}

export type ActorType = "USER" | "AGENT" | "SYSTEM";

export interface HistoryEntry {
  id: number;
  from_state: WorkOrderState | null;
  to_state: WorkOrderState;
  actor_type: ActorType;
  actor_id: string;
  actor_name: string;
  reason: string;
  plan_version_id: number | null;
  at: string;
}

// Nhãn loại thay đổi — 4 loại cần duyệt theo specs/user-roles.md §4
export const CHANGE_LABEL: Record<ChangeType, string> = {
  LINE_ASSIGNMENT: "Gán line",
  RETURN_TIME_CHANGE: "Đổi giờ trả",
  INCIDENT_DELAY: "Hoãn do sự cố",
  PRIORITY_OVERRIDE: "Đổi ưu tiên",
  ACCEPT_DURING_WARNING: "Nhận đơn khi cảnh báo",
};

export const CHANGE_TONE: Record<ChangeType, string> = {
  LINE_ASSIGNMENT: "badge",
  RETURN_TIME_CHANGE: "badge badge-warn",
  INCIDENT_DELAY: "badge badge-danger",
  PRIORITY_OVERRIDE: "badge badge-warn",
  ACCEPT_DURING_WARNING: "badge badge-warn",
};

export const ACTOR_LABEL: Record<ActorType, string> = {
  USER: "Người dùng",
  AGENT: "AI agent",
  SYSTEM: "Hệ thống",
};

/** Nguồn của đề xuất: sự cố / đơn mới / Điều phối sửa tay. */
export function sourceLabel(diff: Pick<PlanDiff, "plan_version" | "incident_id">): string {
  switch (diff.plan_version.trigger) {
    case "INCIDENT":
      return diff.incident_id ? `Sự cố line #${diff.incident_id}` : "Sự cố line";
    case "NEW_ORDER":
      return "Đơn mới";
    case "MANUAL":
      return "Điều phối xếp tay";
  }
}

/** Số đơn bị ảnh hưởng = số đơn có thay đổi. */
export function affectedCount(changes: Pick<PlanChange, "work_order_id">[]): number {
  return new Set(changes.map((c) => c.work_order_id)).size;
}

/** Các loại thay đổi cần duyệt có trong version, theo thứ tự nhãn, không trùng. */
export function approvalLabels(changes: Pick<PlanChange, "change_type" | "needs_approval">[]): string[] {
  const types = new Set(changes.filter((c) => c.needs_approval).map((c) => c.change_type));
  return (Object.keys(CHANGE_LABEL) as ChangeType[]).filter((t) => types.has(t)).map((t) => CHANGE_LABEL[t]);
}

/** "Line A 09:00–12:00"; null → "Chưa có lịch". */
export function spanText(span: Span | null): string {
  return span ? `Line ${span.line} ${hhmm(span.start)}–${hhmm(span.end)}` : "Chưa có lịch";
}

/** Lý do từ chối bắt buộc (backend: rỗng → 422, > 500 ký tự → 422). */
export function rejectReasonError(reason: string): string | null {
  const r = reason.trim();
  if (!r) return "Phải ghi lý do từ chối.";
  if (r.length > 500) return "Lý do tối đa 500 ký tự.";
  return null;
}

// ---------- Màn so sánh 2 version — /approvals/[id] ----------

/** "Trước" = lịch nền của diff (ACTIVE hiện tại khi còn chờ duyệt, version cha khi đã xử lý); "sau" = chính version. */
export function compareVersions(diff: Pick<PlanDiff, "plan_version" | "base_version_id">): {
  before: string;
  after: string;
} {
  return {
    before: diff.base_version_id ? String(diff.base_version_id) : "current",
    after: String(diff.plan_version.id),
  };
}

/** Các ngày (giờ VN) có slot cũ / mới của đơn thay đổi (+ mốc thêm, vd khung dừng sự cố) — để chọn ngày xem. */
export function diffDays(changes: Pick<PlanChange, "old" | "new">[], extra: string[] = []): string[] {
  const stamps = [...extra, ...changes.flatMap((c) => [c.old?.start, c.new.start, c.new.end])].filter(
    (t): t is string => !!t,
  );
  return [...new Set(stamps.map((t) => todayVN(Date.parse(t))))].sort();
}
