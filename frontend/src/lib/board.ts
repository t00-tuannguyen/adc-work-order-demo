// Kanban lệnh & lịch Line A / B — ADC-003 (T-029, T-030). Kiểu + hàm thuần, test bằng node --test.
// Contract: specs/api-contracts.md §3.

import type { Priority, ReviewStatus } from "./intake.ts";
import type { RiskCheck } from "./risk.ts";

export type Line = "A" | "B";
export type PlanStatus = "PROPOSED" | "PENDING_APPROVAL" | "ACTIVE" | "SUPERSEDED" | "REJECTED";
export type WorkOrderState =
  | "DRAFT"
  | "FEASIBILITY_CHECK"
  | "PENDING_APPROVAL"
  | "SCHEDULED"
  | "WAITING_ARRIVAL"
  | "READY_FOR_IRRADIATION"
  | "IN_IRRADIATION"
  | "COMPLETED_IRRADIATION"
  | "READY_FOR_RETURN"
  | "RETURNED"
  | "CLOSED"
  | "LINE_INCIDENT"
  | "SLA_RISK"
  | "RESCHEDULE_REQUIRED"
  | "ESCALATED_TO_BUSINESS"
  | "BLOCK_NEW_ORDER";

export interface CardSlot {
  line: Line;
  start: string;
  end: string;
  sla_ok: boolean;
  plan_version: number;
  plan_status: PlanStatus;
}

export interface WorkOrderCard {
  id: string;
  product_name: string | null;
  priority: Priority | null;
  state: WorkOrderState;
  review_status: ReviewStatus | null;
  expected_arrival: string | null;
  requested_return: string | null;
  estimated_duration_min: number | null;
  slot: CardSlot | null;
}

export interface ScheduleResult {
  line: Line;
  start: string;
  end: string;
  plan_version: number;
  sla_ok: boolean;
  plan_status: PlanStatus;
  reason: string;
  risk: RiskCheck; // T-036: OK → ACTIVE ngay, WARN → chờ duyệt nhận đơn; BLOCK trả 409
}

export const STATE_LABEL: Record<WorkOrderState, string> = {
  DRAFT: "Nháp",
  FEASIBILITY_CHECK: "Chờ xếp lịch",
  PENDING_APPROVAL: "Chờ duyệt",
  SCHEDULED: "Đã xếp lịch",
  WAITING_ARRIVAL: "Chờ hàng đến",
  READY_FOR_IRRADIATION: "Sẵn sàng chiếu",
  IN_IRRADIATION: "Đang chiếu xạ",
  COMPLETED_IRRADIATION: "Chiếu xong",
  READY_FOR_RETURN: "Chờ trả",
  RETURNED: "Đã trả",
  CLOSED: "Đóng",
  LINE_INCIDENT: "Sự cố line",
  SLA_RISK: "Rủi ro SLA",
  RESCHEDULE_REQUIRED: "Cần xếp lại",
  ESCALATED_TO_BUSINESS: "Đã escalate",
  BLOCK_NEW_ORDER: "Bị chặn (BLOCK)",
};

export type ColumnKey =
  | "draft"
  | "approval"
  | "scheduled"
  | "arrival"
  | "irradiating"
  | "return"
  | "done"
  | "sla_risk"
  | "escalated";

export interface KanbanColumn {
  key: ColumnKey;
  label: string;
  exception?: boolean;
}

// Cột theo nhóm trạng thái (ADC-003 §UI/UX) — ngoại lệ đứng cuối
export const COLUMNS: KanbanColumn[] = [
  { key: "draft", label: "Nháp" },
  { key: "approval", label: "Chờ duyệt" },
  { key: "scheduled", label: "Đã xếp lịch" },
  { key: "arrival", label: "Chờ hàng đến" },
  { key: "irradiating", label: "Đang chiếu xạ" },
  { key: "return", label: "Chờ trả" },
  { key: "done", label: "Hoàn tất" },
  { key: "sla_risk", label: "Rủi ro SLA", exception: true },
  { key: "escalated", label: "Đã escalate", exception: true },
];

const STATE_COLUMN: Record<WorkOrderState, ColumnKey> = {
  DRAFT: "draft",
  FEASIBILITY_CHECK: "draft",
  PENDING_APPROVAL: "approval",
  RESCHEDULE_REQUIRED: "approval",
  BLOCK_NEW_ORDER: "approval",
  SCHEDULED: "scheduled",
  WAITING_ARRIVAL: "arrival",
  READY_FOR_IRRADIATION: "arrival",
  IN_IRRADIATION: "irradiating",
  COMPLETED_IRRADIATION: "return",
  READY_FOR_RETURN: "return",
  RETURNED: "done",
  CLOSED: "done",
  LINE_INCIDENT: "sla_risk",
  SLA_RISK: "sla_risk",
  ESCALATED_TO_BUSINESS: "escalated",
};

/** Lịch dự kiến trễ giờ trả (sla_ok=false) → cột Rủi ro SLA, trừ khi đơn đã trả / đóng hoặc đã escalate. */
export function columnOf(card: WorkOrderCard): ColumnKey {
  const col = STATE_COLUMN[card.state];
  if (card.slot && !card.slot.sla_ok && col !== "done" && col !== "escalated") return "sla_risk";
  return col;
}

const PRIORITY_RANK: Record<Priority, number> = { VIP: 0, URGENT: 1, NORMAL: 2 };

function returnTime(c: WorkOrderCard): number {
  return c.requested_return ? Date.parse(c.requested_return) : Number.POSITIVE_INFINITY;
}

/** BR-05: VIP → Khẩn → Thường, cùng mức giờ trả sớm hơn trước; mã đơn làm khóa phụ để thứ tự ổn định. */
export function byPriority(a: WorkOrderCard, b: WorkOrderCard): number {
  const pa = a.priority ? PRIORITY_RANK[a.priority] : 3;
  const pb = b.priority ? PRIORITY_RANK[b.priority] : 3;
  return pa - pb || returnTime(a) - returnTime(b) || a.id.localeCompare(b.id);
}

export function groupByColumn(cards: WorkOrderCard[]): Record<ColumnKey, WorkOrderCard[]> {
  const out = Object.fromEntries(COLUMNS.map((c) => [c.key, [] as WorkOrderCard[]])) as Record<
    ColumnKey,
    WorkOrderCard[]
  >;
  for (const c of cards) out[columnOf(c)].push(c);
  for (const list of Object.values(out)) list.sort(byPriority);
  return out;
}

/** Đơn xếp được ngay (FEASIBILITY_CHECK + có ước tính), theo thứ tự ưu tiên BR-05. */
export function scheduleQueue(cards: WorkOrderCard[]): WorkOrderCard[] {
  return cards.filter((c) => c.state === "FEASIBILITY_CHECK" && c.estimated_duration_min).sort(byPriority);
}

// Bước vận hành kế tiếp Điều phối bấm được — khớp OPERATIONAL_STATES + bảng chuyển ở backend
export const NEXT_STEP: Partial<Record<WorkOrderState, { to: WorkOrderState; label: string }>> = {
  SCHEDULED: { to: "WAITING_ARRIVAL", label: "Chờ hàng đến" },
  WAITING_ARRIVAL: { to: "READY_FOR_IRRADIATION", label: "Hàng đã đến" },
  READY_FOR_IRRADIATION: { to: "IN_IRRADIATION", label: "Bắt đầu chiếu" },
  IN_IRRADIATION: { to: "COMPLETED_IRRADIATION", label: "Chiếu xong" },
  COMPLETED_IRRADIATION: { to: "READY_FOR_RETURN", label: "Sẵn sàng trả" },
  READY_FOR_RETURN: { to: "RETURNED", label: "Đã trả khách" },
  RETURNED: { to: "CLOSED", label: "Đóng lệnh" },
};

export const PRIORITY_CLASS: Record<Priority, string> = {
  VIP: "prio prio-vip",
  URGENT: "prio prio-urgent",
  NORMAL: "prio prio-normal",
};

const VN_OFFSET_MS = 7 * 3600 * 1000;

/** ISO → "HH:MM" giờ Việt Nam. */
export function hhmm(iso: string): string {
  return new Date(Date.parse(iso) + VN_OFFSET_MS).toISOString().slice(11, 16);
}

/** "Line A · 09:00–12:00". */
export function slotText(slot: Pick<CardSlot, "line" | "start" | "end">): string {
  return `Line ${slot.line} · ${hhmm(slot.start)}–${hhmm(slot.end)}`;
}

/** Thẻ Kanban → màn lịch đúng ngày bắt đầu (giờ VN), đúng plan version nếu là đề xuất, mở sẵn khối của lệnh. */
export function scheduleHref(
  workOrderId: string,
  slot: Pick<CardSlot, "start" | "plan_version" | "plan_status">,
): string {
  const q = new URLSearchParams({ date: todayVN(Date.parse(slot.start)), wo: workOrderId });
  if (slot.plan_status !== "ACTIVE") q.set("version", String(slot.plan_version));
  return `/schedule?${q}`;
}

// ---------- Lịch 2 line dạng timeline — T-030 ----------

export interface ScheduleSlot {
  work_order_id: string;
  product_name: string | null;
  priority: Priority | null;
  state: WorkOrderState;
  line: Line;
  start: string;
  end: string;
  requested_return: string | null;
  sla_ok: boolean;
  reason: string | null;
}

export interface PlanVersion {
  id: number;
  status: PlanStatus;
  parent_version_id: number | null;
  trigger: "NEW_ORDER" | "INCIDENT" | "MANUAL";
  requires_approval: boolean;
  created_by: string;
  created_at: string;
  slot_count: number;
}

export interface ScheduleView {
  plan_version: PlanVersion | null;
  date: string | null;
  lines: Record<Line, ScheduleSlot[]>;
}

export const PLAN_STATUS_LABEL: Record<PlanStatus, string> = {
  PROPOSED: "Đề xuất",
  PENDING_APPROVAL: "Chờ duyệt",
  ACTIVE: "Đang áp dụng",
  SUPERSEDED: "Đã thay thế",
  REJECTED: "Bị từ chối",
};

const DAY_MS = 24 * 3600 * 1000;

/** Ngày hôm nay theo giờ Việt Nam, "YYYY-MM-DD". */
export function todayVN(now: number = Date.now()): string {
  return new Date(now + VN_OFFSET_MS).toISOString().slice(0, 10);
}

/** "YYYY-MM-DD" ± n ngày. */
export function shiftDay(day: string, n: number): string {
  return new Date(Date.parse(`${day}T00:00:00Z`) + n * DAY_MS).toISOString().slice(0, 10);
}

/** Mốc 00:00 giờ Việt Nam của ngày `day` (ms epoch). */
export function dayStartVN(day: string): number {
  return Date.parse(`${day}T00:00:00+07:00`);
}

/** Vị trí % trên trục 24h của ngày; phần ngoài ngày bị cắt. null nếu không giao ngày. */
export function blockPosition(
  start: string,
  end: string,
  day: string,
): { left: number; width: number; clippedStart: boolean; clippedEnd: boolean } | null {
  const d0 = dayStartVN(day);
  const s = Date.parse(start) - d0;
  const e = Date.parse(end) - d0;
  if (e <= 0 || s >= DAY_MS) return null;
  const cs = Math.max(s, 0);
  const ce = Math.min(e, DAY_MS);
  const pct = (ms: number) => Math.round((ms / DAY_MS) * 10000) / 100;
  return { left: pct(cs), width: pct(ce - cs), clippedStart: s < 0, clippedEnd: e > DAY_MS };
}

/** Vị trí % của 1 mốc giờ (vạch đỏ giờ trả); null nếu ngoài ngày. */
export function markerPosition(at: string | null, day: string): number | null {
  if (!at) return null;
  const t = Date.parse(at) - dayStartVN(day);
  if (t < 0 || t > DAY_MS) return null;
  return Math.round((t / DAY_MS) * 10000) / 100;
}

/** Chữ giờ trả khi hover cờ / khối: "trả 16:00" nếu cùng ngày đang xem, khác ngày thì kèm ngày "trả 17:00 05/10". */
export function returnLabel(at: string | null, day: string): string | null {
  if (!at) return null;
  const local = new Date(Date.parse(at) + VN_OFFSET_MS).toISOString();
  return local.slice(0, 10) === day ? `trả ${hhmm(at)}` : `trả ${hhmm(at)} ${local.slice(8, 10)}/${local.slice(5, 7)}`;
}

// ---------- Xếp / sửa lịch thủ công — BR-15 ----------

// RESCHEDULE_REQUIRED = phương án bị từ chối, Điều phối xếp lại (T-040)
export const MANUAL_STATES: WorkOrderState[] = ["FEASIBILITY_CHECK", "RESCHEDULE_REQUIRED", "SCHEDULED", "WAITING_ARRIVAL"];

export interface ManualScheduleResult {
  line: Line;
  start: string;
  end: string;
  plan_version: number;
  sla_ok: boolean;
  plan_status: PlanStatus;
  reason: string;
}

/** Đơn chưa chạy, có thời lượng, không có đề xuất đang chờ duyệt → Điều phối xếp / sửa tay được. */
export function canEditManually(card: Pick<WorkOrderCard, "state" | "estimated_duration_min" | "slot">): boolean {
  if (!MANUAL_STATES.includes(card.state) || !card.estimated_duration_min) return false;
  return !card.slot || card.slot.plan_status === "ACTIVE";
}

/** T-055: chỉ lệnh nháp xóa được (backend: khác DRAFT → 409); quyền UPLOAD_TICKET kiểm tra ở trang. */
export function canDeleteDraft(card: Pick<WorkOrderCard, "state">): boolean {
  return card.state === "DRAFT";
}

/** Xem trước giờ xong + kịp / trễ giờ trả (backend vẫn kiểm tra lại). */
export function manualPreview(
  startIso: string | null,
  durationMin: number,
  requestedReturn: string | null,
): { end: string; slaOk: boolean; lateMin: number } | null {
  const start = startIso ? Date.parse(startIso) : NaN;
  if (Number.isNaN(start)) return null;
  const end = start + durationMin * 60_000;
  const ret = requestedReturn ? Date.parse(requestedReturn) : NaN;
  const lateMin = Number.isNaN(ret) ? 0 : Math.max(0, Math.ceil((end - ret) / 60_000));
  return { end: new Date(end).toISOString(), slaOk: lateMin === 0, lateMin };
}
