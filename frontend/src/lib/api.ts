"use client";

// Gọi backend qua proxy cùng origin (next.config.ts) — cookie phiên HttpOnly tự đi kèm.
import type {
  Line,
  ManualScheduleResult,
  PlanVersion,
  ScheduleResult,
  ScheduleView,
  WorkOrderCard,
  WorkOrderState,
} from "./board";
import type { HistoryEntry, PlanDiff } from "./approval";
import type { EstimateResult } from "./estimate";
import type { ExplanationResult, Incident, IncidentInput } from "./incident";
import { type IngestJob, type IntakeWarning, type JobWorkOrder, sourcePdfOutcome, type WorkOrderReview } from "./intake";
import type { DraftResult, Escalation, RiskCheck } from "./risk";
import { fallbackMessage } from "./http";
import { loginUrl, type Me, type Role, type UserStatus } from "./roles";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    /** `detail` gốc của FastAPI — object khi lỗi có cấu trúc (vd 409 NEW_ORDER_BLOCKED). */
    public detail?: unknown,
  ) {
    super(message);
  }
}

/** Câu báo lỗi từ `detail`: chuỗi, hoặc `detail.message` của lỗi có cấu trúc. */
function detailMessage(detail: unknown, fallback: string): string {
  if (typeof detail === "string") return detail;
  if (typeof detail === "object" && detail !== null && typeof (detail as { message?: unknown }).message === "string")
    return (detail as { message: string }).message;
  return detail === undefined ? fallback : JSON.stringify(detail);
}

/** Phiên hết hạn (401) → sang đăng nhập, rồi quay lại đúng trang này (ADC-008 TC8). */
function redirectToLogin(): never {
  const here = window.location.pathname + window.location.search;
  window.location.assign(loginUrl(here));
  throw new ApiError(401, "Chưa đăng nhập");
}

export async function api<T>(path: string, init?: RequestInit & { allow401?: boolean }): Promise<T> {
  const resp = await fetch(path, {
    ...init,
    credentials: "same-origin",
    headers: { "content-type": "application/json", ...init?.headers },
    cache: "no-store",
  });
  if (resp.status === 401 && !init?.allow401) redirectToLogin();
  if (!resp.ok) {
    let detail: unknown;
    try {
      detail = (await resp.json()).detail;
    } catch {
      /* body rỗng */
    }
    throw new ApiError(resp.status, detailMessage(detail, fallbackMessage(resp.status, resp.statusText)), detail);
  }
  return (resp.status === 204 ? undefined : await resp.json()) as T;
}

export const getMe = () => api<Me>("/api/me");

/** null nếu chưa đăng nhập — dùng ở màn login để không vòng lặp chuyển hướng. */
export async function getMeOrNull(): Promise<Me | null> {
  try {
    return await api<Me>("/api/me", { allow401: true });
  } catch (e) {
    if (e instanceof ApiError && (e.status === 401 || e.status === 403)) return null;
    throw e;
  }
}

export const logout = () => api<void>("/auth/logout", { method: "POST", allow401: true });
export const logoutAll = () => api<void>("/auth/logout-all", { method: "POST", allow401: true });

export const demoLogin = (role: Role) =>
  api<void>("/auth/demo-login", { method: "POST", body: JSON.stringify({ role }), allow401: true });

export const completeSignup = (requested_role: Role, note: string) =>
  api<Me>("/api/signup/complete", { method: "POST", body: JSON.stringify({ requested_role, note }) });

export interface AdminUser extends Me {
  request_note: string | null;
  created_at: string;
  approved_by: string | null;
  approved_at: string | null;
  last_login_at: string | null;
}

export const listUsers = (status?: UserStatus) =>
  api<AdminUser[]>(status ? `/api/users?status=${status}` : "/api/users");

export const patchUser = (id: string, patch: { role?: Role; status?: UserStatus }) =>
  api<AdminUser>(`/api/users/${id}`, { method: "PATCH", body: JSON.stringify(patch) });

export interface EstimateInput {
  product_group: string;
  quantity: number;
  pkg_length_cm: number;
  pkg_width_cm: number;
  pkg_height_cm: number;
  pkg_weight_kg: number;
  required_dose_kgy: number;
}

export const estimate = (input: EstimateInput) =>
  api<EstimateResult>("/api/estimate", { method: "POST", body: JSON.stringify(input) });

export const getThroughputConfig = () => api<Record<string, unknown>>("/api/config/throughput");

export interface DemoResetResult {
  demo_date: string;
  work_orders: { id: string; ref: string; state: string; estimated_duration_min: number }[];
  incidents: { ref: string; line: "A" | "B"; start_at: string; est_downtime_min: number; note: string }[];
}

/** POST /api/demo/reset — 404 khi môi trường không bật reset (ADC-002 T-025). */
export const resetDemo = () => api<DemoResetResult>("/api/demo/reset", { method: "POST" });

// ---------- Tiếp nhận ticket — ADC-001 (T-021) ----------

export interface UploadAccepted {
  job_id: string;
  file_id: string;
}

/** multipart — không đặt content-type để trình duyệt tự gắn boundary. */
/** PDF gốc để nhúng trình xem; null nếu file không còn (filesystem tạm của bản demo — ADR-0012). */
export async function getSourcePdf(fileId: string): Promise<Blob | null> {
  const resp = await fetch(`/api/files/${fileId}`, { credentials: "same-origin", cache: "no-store" });
  if (resp.status === 401) redirectToLogin();
  const outcome = sourcePdfOutcome(resp.status);
  if (outcome === "missing") return null;
  if (outcome === "error") throw new ApiError(resp.status, resp.statusText);
  return resp.blob();
}

export async function uploadTicket(file: File): Promise<UploadAccepted> {
  const body = new FormData();
  body.append("file", file);
  body.append("received_at", new Date().toISOString());
  const resp = await fetch("/api/tickets/upload", { method: "POST", body, credentials: "same-origin" });
  if (resp.status === 401) redirectToLogin();
  if (!resp.ok) {
    let detail: unknown;
    try {
      detail = (await resp.json()).detail;
    } catch {
      /* body rỗng hoặc không phải JSON */
    }
    throw new ApiError(resp.status, detailMessage(detail, fallbackMessage(resp.status, resp.statusText)), detail);
  }
  return resp.json();
}

export const getIngestJob = (id: string) => api<IngestJob>(`/api/ingest-jobs/${id}`);

export const createTicket = (source: "TEXT" | "MANUAL", raw_text?: string) =>
  api<{ work_orders: JobWorkOrder[] }>("/api/tickets", {
    method: "POST",
    body: JSON.stringify({ source, raw_text: raw_text ?? null, received_at: new Date().toISOString() }),
  });

export const getIntake = (id: string) => api<WorkOrderReview>(`/api/work-orders/${id}/intake`);

export const patchWorkOrder = (id: string, fields: Record<string, unknown>) =>
  api<WorkOrderReview>(`/api/work-orders/${id}`, { method: "PATCH", body: JSON.stringify({ fields }) });

export const submitWorkOrder = (id: string) =>
  api<WorkOrderReview>(`/api/work-orders/${id}/submit`, { method: "POST" });

/** Chỉ lệnh DRAFT (khác → 409); xóa cả ticket + dữ liệu tiếp nhận, giữ file PDF gốc. */
export const deleteWorkOrder = (id: string) => api<void>(`/api/work-orders/${id}`, { method: "DELETE" });

export const listIntakeWarnings = () => api<IntakeWarning[]>("/api/intake-warnings?status=open");

export const ackIntakeWarning = (id: number, note?: string) =>
  api<IntakeWarning>(`/api/intake-warnings/${id}/ack`, { method: "POST", body: JSON.stringify({ note: note ?? null }) });

// ---------- Lịch Line A / B & Kanban — ADC-003 (T-028 → T-030) ----------

export const listWorkOrders = () => api<WorkOrderCard[]>("/api/work-orders");

export const scheduleWorkOrder = (id: string) =>
  api<ScheduleResult>(`/api/work-orders/${id}/schedule`, { method: "POST" });

/** PUT — Điều phối xếp / sửa lịch thủ công (BR-15); trùng slot → 409, sai giờ / ca → 422. */
export const scheduleManually = (id: string, line: Line, start: string) =>
  api<ManualScheduleResult>(`/api/work-orders/${id}/schedule`, { method: "PUT", body: JSON.stringify({ line, start }) });

export const changeWorkOrderState = (id: string, to_state: WorkOrderState, reason = "") =>
  api<WorkOrderCard>(`/api/work-orders/${id}/state`, { method: "PATCH", body: JSON.stringify({ to_state, reason }) });

/** `version`: "current" hoặc số version; `date`: "YYYY-MM-DD" giờ địa phương. */
export const getSchedule = (version: string, date: string) =>
  api<ScheduleView>(`/api/schedule?version=${encodeURIComponent(version)}&date=${encodeURIComponent(date)}`);

export const listPlanVersions = () => api<PlanVersion[]>("/api/plan-versions");

// ---------- Sự cố line — ADC-004 (T-031) ----------

/** Chỉ Điều phối; trùng khung dừng với sự cố OPEN cùng line → 409. Phương án luôn chờ duyệt, lịch ACTIVE giữ nguyên. */
export const declareIncident = (input: IncidentInput) =>
  api<Incident>("/api/incidents", { method: "POST", body: JSON.stringify(input) });

export const getIncident = (id: number) => api<Incident>(`/api/incidents/${id}`);

export const listIncidents = () => api<Incident[]>("/api/incidents");

/** Scheduler Agent viết lại giải thích (T-034); LLM lỗi / tắt / sai số liệu → bản deterministic (TEMPLATE). */
export const explainIncident = (id: number) =>
  api<ExplanationResult>(`/api/incidents/${id}/explanation`, { method: "POST" });

// ---------- Rủi ro đơn mới & escalation — ADC-005 (T-036 → T-039) ----------

/** Chỉ mô phỏng (không đổi lịch) — banner vàng/đỏ khi tạo đơn. */
export const riskCheck = (id: string) => api<RiskCheck>(`/api/work-orders/${id}/risk-check`, { method: "POST" });

/** `status`: "open" (= OPEN + DRAFTED), 1 trạng thái, hoặc bỏ trống = tất cả. */
export const listEscalations = (status?: string) =>
  api<Escalation[]>(status ? `/api/escalations?status=${encodeURIComponent(status)}` : "/api/escalations");

export const draftEscalation = (id: number) => api<DraftResult>(`/api/escalations/${id}/draft`, { method: "POST" });

export const approveEscalation = (id: number, final_message: string) =>
  api<Escalation>(`/api/escalations/${id}/approve`, { method: "POST", body: JSON.stringify({ final_message }) });

// ---------- Phê duyệt plan version & lịch sử — ADC-006 (T-041, T-042) ----------

export const listPendingPlanVersions = () => api<PlanVersion[]>("/api/plan-versions?status=pending");

export const getPlanDiff = (id: number) => api<PlanDiff>(`/api/plan-versions/${id}/diff`);

/** Version không còn chờ duyệt / lịch đã đổi và trùng giờ / người khác vừa duyệt → 409. */
export const approvePlanVersion = (id: number, comment: string) =>
  api<PlanVersion>(`/api/plan-versions/${id}/approve`, { method: "POST", body: JSON.stringify({ comment }) });

export const rejectPlanVersion = (id: number, reason: string) =>
  api<PlanVersion>(`/api/plan-versions/${id}/reject`, { method: "POST", body: JSON.stringify({ reason }) });

export const getWorkOrderHistory = (id: string) => api<HistoryEntry[]>(`/api/work-orders/${id}/history`);
