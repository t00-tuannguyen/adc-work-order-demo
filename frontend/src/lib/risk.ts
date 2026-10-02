// Rủi ro đơn mới & escalation — ADC-005 (T-036 → T-039). Kiểu + hàm thuần, test bằng node --test.
// Contract: specs/api-contracts.md §5.

import type { WorkOrderState } from "./board.ts";
import type { Priority } from "./intake.ts";

export type RiskLevel = "OK" | "WARN" | "BLOCK";

export interface RiskCheck {
  level: RiskLevel;
  reasons: string[];
  earliest_feasible_return: string;
}

export type EscalationStatus = "OPEN" | "DRAFTED" | "APPROVED" | "CLOSED";

export interface Escalation {
  id: number;
  work_order_id: string;
  product_name: string | null;
  priority: Priority | null;
  state: WorkOrderState;
  incident_id: number | null;
  delay_min: number;
  requested_return: string | null;
  expected_finish: string | null;
  status: EscalationStatus;
  draft_message: string | null;
  final_message: string | null;
  approved_by: string | null;
  approved_at: string | null;
  can_close: boolean;
}

export interface DraftResult {
  message_draft: string;
  source: "LLM" | "TEMPLATE";
}

export const RISK_NOTICE: Record<RiskLevel, string> = {
  OK: "notice notice-success",
  WARN: "notice notice-warn",
  BLOCK: "notice notice-error",
};

export const RISK_TITLE: Record<RiskLevel, string> = {
  OK: "Nhận được — kịp giờ trả, không ảnh hưởng đơn khác",
  WARN: "Cảnh báo — chỉ kịp giờ trả khi đẩy lùi đơn khác, cần duyệt nhận đơn",
  BLOCK: "Chặn — không kịp giờ trả dù xếp sớm nhất",
};

export const ESCALATION_STATUS_LABEL: Record<EscalationStatus, string> = {
  OPEN: "Mới",
  DRAFTED: "Đã có nháp",
  APPROVED: "Đã duyệt · đã gửi",
  CLOSED: "Đã đóng",
};

export const ESCALATION_STATUS_TONE: Record<EscalationStatus, string> = {
  OPEN: "badge badge-danger",
  DRAFTED: "badge badge-warn",
  APPROVED: "badge badge-success",
  CLOSED: "badge",
};

/** 45 → "45 phút", 120 → "2 giờ", 135 → "2 giờ 15 phút". */
export function delayText(min: number): string {
  const h = Math.floor(min / 60);
  const m = min % 60;
  if (!h) return `${m} phút`;
  return m ? `${h} giờ ${m} phút` : `${h} giờ`;
}

/** `detail` của 409 khi xếp lịch bị chặn (`error_code = NEW_ORDER_BLOCKED`) → RiskCheck, khác → null. */
export function blockedRisk(detail: unknown): RiskCheck | null {
  if (typeof detail !== "object" || detail === null) return null;
  const d = detail as { error_code?: unknown; risk?: unknown };
  if (d.error_code !== "NEW_ORDER_BLOCKED" || typeof d.risk !== "object" || d.risk === null) return null;
  return d.risk as RiskCheck;
}

/** Đơn xem được rủi ro: chưa xếp lịch hoặc đang bị chặn (API trả 409 cho trạng thái khác). */
export function canCheckRisk(state: WorkOrderState | string): boolean {
  return state === "FEASIBILITY_CHECK" || state === "BLOCK_NEW_ORDER";
}

export function isOpen(e: Pick<Escalation, "status">): boolean {
  return e.status === "OPEN" || e.status === "DRAFTED";
}

/** Sự kiện cửa sổ: hàng đợi escalation vừa đổi → badge trên menu đếm lại. */
export const ESCALATIONS_CHANGED = "adc:escalations-changed";
