// Khai báo sự cố line — ADC-004 (T-031). Kiểu + hàm thuần, test bằng node --test.
// Contract: specs/api-contracts.md §4.

import { hhmm, type Line, type PlanVersion, todayVN, type WorkOrderState } from "./board.ts";
import type { Priority } from "./intake.ts";

export type IncidentStatus = "OPEN" | "RESOLVED";
export type AffectedOutcome = "MOVED_ALT_LINE" | "DELAYED" | "UNCHANGED" | "PULLED_FORWARD";
export type IncidentChangeType = "LINE_ASSIGNMENT" | "INCIDENT_DELAY" | "PRIORITY_OVERRIDE";

export interface SlotTime {
  line: Line;
  start: string;
  end: string;
}

export interface AffectedOrder {
  work_order_id: string;
  product_name: string | null;
  priority: Priority | null;
  state: WorkOrderState;
  outcome: AffectedOutcome;
  change_type: IncidentChangeType;
  old: SlotTime;
  new: SlotTime;
  requested_return: string | null;
  sla_ok: boolean;
  reason: string;
}

export interface Incident {
  incident_id: number;
  line: Line;
  start_at: string;
  est_downtime_min: number;
  end_at: string;
  actual_end_at: string | null;
  status: IncidentStatus;
  note: string;
  created_by: string;
  created_at: string;
  affected_orders: AffectedOrder[];
  proposed_plan_version: PlanVersion | null;
  sla_risks: string[];
  explanation: string;
}

export interface IncidentInput {
  line: Line;
  start_at: string;
  est_downtime_min: number;
  note: string;
}

/** Khớp validator backend: `est_downtime_min` 0–10080 (7 ngày), `note` ≤ 500. */
export const MAX_DOWNTIME_MIN = 7 * 24 * 60;
export const MAX_NOTE_LEN = 500;

export const OUTCOME_LABEL: Record<AffectedOutcome, string> = {
  MOVED_ALT_LINE: "Sang line còn lại",
  DELAYED: "Hoãn sau hồi phục",
  UNCHANGED: "Giữ nguyên",
  PULLED_FORWARD: "Kéo sớm lấp khe trống",
};

/** Form dùng chuỗi như input HTML; thời gian dừng nhập giờ + phút cho dễ đọc. */
export interface IncidentForm {
  line: Line;
  start: string; // "YYYY-MM-DDTHH:MM" giờ Việt Nam (datetime-local)
  hours: string;
  minutes: string;
  note: string;
}

/** Tổng phút dừng; null nếu không phải số nguyên không âm. */
export function downtimeMin(form: Pick<IncidentForm, "hours" | "minutes">): number | null {
  const parse = (v: string) => (v.trim() === "" ? 0 : /^\d+$/.test(v.trim()) ? Number(v.trim()) : NaN);
  const total = parse(form.hours) * 60 + parse(form.minutes);
  return Number.isInteger(total) ? total : null;
}

/** Lỗi theo trường (rỗng = hợp lệ). Backend kiểm tra lại; trùng sự cố đang mở → 409. */
export function validateIncident(form: IncidentForm): Partial<Record<"start" | "downtime" | "note", string>> {
  const errors: Partial<Record<"start" | "downtime" | "note", string>> = {};
  if (!form.start) errors.start = "Chọn thời điểm bắt đầu dừng.";
  const d = downtimeMin(form);
  if (d === null) errors.downtime = "Thời gian dừng phải là số nguyên giờ / phút.";
  else if (d > MAX_DOWNTIME_MIN) errors.downtime = "Thời gian dừng tối đa 7 ngày.";
  if (form.note.trim().length > MAX_NOTE_LEN) errors.note = `Ghi chú tối đa ${MAX_NOTE_LEN} ký tự.`;
  return errors;
}

/** Body POST /api/incidents; null khi form chưa hợp lệ. */
export function incidentPayload(form: IncidentForm): IncidentInput | null {
  const d = downtimeMin(form);
  if (Object.keys(validateIncident(form)).length > 0 || d === null) return null;
  return { line: form.line, start_at: `${form.start}:00+07:00`, est_downtime_min: d, note: form.note.trim() };
}

/** Giờ hồi phục dự kiến (ISO) để xem trước khung dừng; null nếu form chưa đủ. */
export function downtimeEnd(form: IncidentForm): string | null {
  const p = incidentPayload(form);
  return p ? new Date(Date.parse(p.start_at) + p.est_downtime_min * 60_000).toISOString() : null;
}

/** Giá trị mặc định: Line A, bắt đầu bây giờ làm tròn xuống 15 phút (giờ VN), dừng 3 giờ. */
export function defaultIncidentForm(now: number = Date.now()): IncidentForm {
  const step = 15 * 60_000;
  const local = new Date(Math.floor(now / step) * step + 7 * 3600 * 1000).toISOString().slice(0, 16);
  return { line: "A", start: local, hours: "3", minutes: "0", note: "" };
}

/** "A · 10:45–17:15", kèm ngày "04/10" khi slot bắt đầu khác ngày (giờ VN) với `refAt` — đơn bị dời sang ngày khác. */
export function slotTimeText(slot: SlotTime, refAt: string): string {
  return `${slot.line} · ${spanText(slot.start, slot.end, refAt)}`;
}

/** "10:45–17:15", kèm ngày bắt đầu "04/10" khi khác ngày (giờ VN) với `refAt`. */
export function spanText(start: string, end: string, refAt: string): string {
  return `${hhmm(start)}–${hhmm(end)}${dateSuffix(start, refAt)}`;
}

/** "17:15", kèm ngày "17:15 04/10" khi khác ngày (giờ VN) với `refAt`. */
export function timeText(at: string, refAt: string): string {
  return `${hhmm(at)}${dateSuffix(at, refAt)}`;
}

function dateSuffix(at: string, refAt: string): string {
  const day = todayVN(Date.parse(at));
  return day === todayVN(Date.parse(refAt)) ? "" : ` ${day.slice(8, 10)}/${day.slice(5, 7)}`;
}

/** Link tới timeline của phương án đề xuất, mở đúng ngày bắt đầu dừng. */
export function proposalHref(inc: Pick<Incident, "start_at" | "proposed_plan_version">): string | null {
  if (!inc.proposed_plan_version) return null;
  const day = new Date(Date.parse(inc.start_at) + 7 * 3600 * 1000).toISOString().slice(0, 10);
  return `/schedule?${new URLSearchParams({ date: day, version: String(inc.proposed_plan_version.id) })}`;
}

// ---------- Màn so sánh trước / sau — T-035 ----------

export const INCIDENT_STATUS_LABEL: Record<IncidentStatus, string> = { OPEN: "Đang mở", RESOLVED: "Đã hồi phục" };

export type ExplanationSource = "LLM" | "TEMPLATE";

export interface ExplanationResult {
  explanation: string;
  source: ExplanationSource;
  plan_version_id: number | null;
}

/** "Line A dừng 09:00–12:00". */
export function windowText(inc: Pick<Incident, "line" | "start_at" | "end_at">): string {
  return `Line ${inc.line} dừng ${spanText(inc.start_at, inc.end_at, inc.start_at)}`;
}

/** Khung dừng để tô trên timeline — mọi sự cố đã biết (phương án mới tính cho mọi khung dừng chưa kết thúc). */
export function downtimesOf(incidents: Pick<Incident, "incident_id" | "line" | "start_at" | "end_at">[]) {
  return incidents
    .filter((i) => Date.parse(i.end_at) > Date.parse(i.start_at))
    .map((i) => ({ line: i.line, start: i.start_at, end: i.end_at, label: `Sự cố #${i.incident_id}: ${windowText(i)}` }));
}

/** Version "trước" = version cha của phương án (lịch đang áp dụng lúc tính); chưa có phương án → lịch ACTIVE. */
export function compareVersions(inc: Pick<Incident, "proposed_plan_version">): { before: string; after: string | null } {
  const pv = inc.proposed_plan_version;
  if (!pv) return { before: "current", after: null };
  return { before: pv.parent_version_id ? String(pv.parent_version_id) : "current", after: String(pv.id) };
}

/** Các ngày (giờ VN) có khung dừng hoặc slot cũ / mới của đơn bị ảnh hưởng — để chọn ngày xem. */
export function incidentDays(inc: Pick<Incident, "start_at" | "end_at" | "affected_orders">): string[] {
  const stamps = [inc.start_at, ...inc.affected_orders.flatMap((a) => [a.old.start, a.new.start, a.new.end])];
  return [...new Set(stamps.map((t) => todayVN(Date.parse(t))))].sort();
}

/** Giờ xong mới lệch bao nhiêu phút so với lịch cũ (dương = muộn hơn). */
export function finishShiftMin(a: Pick<AffectedOrder, "old" | "new">): number {
  return Math.round((Date.parse(a.new.end) - Date.parse(a.old.end)) / 60_000);
}
