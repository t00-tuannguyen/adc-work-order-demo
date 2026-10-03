// Tiếp nhận ticket — ADC-001 (T-021). Kiểu + hàm thuần; gọi API ở intakeApi.ts.

import type { EstimateResult } from "./estimate.ts";

export type SourceKind = "VERBATIM" | "INFERRED" | "CONVERTED" | "OCR_LOW" | "MANUAL" | "DEFAULT";
export type ReviewStatus = "AUTO_ACCEPTED" | "ACCEPTED_WITH_WARNINGS" | "NEEDS_REVIEW" | "NEEDS_CLARIFICATION";
export type IngestStep = "UPLOADED" | "READING" | "DETECTING" | "EXTRACTING" | "DONE" | "FAILED";
export type Priority = "NORMAL" | "URGENT" | "VIP";
export type ErrorCode = "MISSING" | "NOT_POSITIVE" | "RETURN_NOT_AFTER_ARRIVAL" | "DOSE_OUT_OF_RANGE";
export type FlagCode =
  | "LOW_CONFIDENCE"
  | "BOUNDARY_UNCERTAIN"
  | "AMBIGUOUS_OCR"
  | "INFERRED_VALUE"
  | "DEFAULT_VALUE"
  | "POSSIBLE_DUPLICATE";

export interface WorkOrderFields {
  product_name: string | null;
  quantity: number | null;
  pkg_length_cm: number | null;
  pkg_width_cm: number | null;
  pkg_height_cm: number | null;
  pkg_weight_kg: number | null;
  required_dose_kgy: number | null;
  priority: Priority | null;
  expected_arrival: string | null;
  requested_return: string | null;
}
export type Column = keyof WorkOrderFields;

export interface JobWorkOrder {
  id: string;
  review_status: ReviewStatus | null;
  state: string;
}

export interface IngestJob {
  status: "QUEUED" | "RUNNING" | "SUCCEEDED" | "FAILED";
  step: IngestStep;
  progress: number;
  work_orders: JobWorkOrder[];
  error_code: string | null;
}

export interface Extraction {
  field: string;
  value: unknown;
  source_kind: SourceKind;
  page: number | null;
  bbox: number[] | null;
  snippet: string | null;
  confidence: number | null;
}

export interface WorkOrderReview {
  id: string;
  state: string;
  review_status: ReviewStatus | null;
  fields: WorkOrderFields;
  boundary_uncertain: boolean;
  errors: { field: string; code: ErrorCode }[];
  unconfirmed_fields: string[];
  can_submit: boolean;
  extractions: Extraction[];
  clarifications: { field: string; question: string; status: "OPEN" | "ANSWERED" }[];
  warnings: { id: number; field: string | null; code: FlagCode; status: "OPEN" | "ACKNOWLEDGED" }[];
  source: {
    type: "PDF" | "TEXT" | "MANUAL";
    file_id: string | null;
    file_name: string | null;
    page_count: number | null;
    page_from: number | null;
    page_to: number | null;
    ocr_used: boolean | null;
    channel: string | null;
    received_at: string | null;
    raw_text: string | null;
  };
  /** ADC-002 — có khi lệnh đã vào FEASIBILITY_CHECK; null + `estimate_error` khi không tính được (BR-02). */
  estimate: EstimateResult | null;
  estimate_error: string | null;
}

export interface IntakeWarning {
  id: number;
  work_order_id: string;
  field: string | null;
  code: FlagCode;
  created_at: string;
}

// ---------- 8 trường (thứ tự & nhãn theo thiết kế ADC-001) ----------

export type FieldKind = "text" | "int" | "number" | "dims" | "priority" | "datetime";

export interface FieldDef {
  key: string; // tên trường trích xuất (khớp field_extractions.field, clarification.field)
  label: string;
  columns: Column[];
  kind: FieldKind;
  unit?: string;
  group: "goods" | "irradiation" | "time";
}

export const FIELD_DEFS: FieldDef[] = [
  { key: "product_name", label: "Tên sản phẩm", columns: ["product_name"], kind: "text", group: "goods" },
  { key: "quantity", label: "Số lượng", columns: ["quantity"], kind: "int", unit: "thùng", group: "goods" },
  {
    key: "package_dimensions_cm",
    label: "Kích thước D × R × C",
    columns: ["pkg_length_cm", "pkg_width_cm", "pkg_height_cm"],
    kind: "dims",
    unit: "cm",
    group: "goods",
  },
  {
    key: "pkg_weight_kg",
    label: "Khối lượng mỗi thùng",
    columns: ["pkg_weight_kg"],
    kind: "number",
    unit: "kg",
    group: "goods",
  },
  {
    key: "required_dose_kgy",
    label: "Liều yêu cầu",
    columns: ["required_dose_kgy"],
    kind: "number",
    unit: "kGy",
    group: "irradiation",
  },
  { key: "priority", label: "Mức ưu tiên", columns: ["priority"], kind: "priority", group: "irradiation" },
  { key: "expected_arrival", label: "Giờ hàng đến", columns: ["expected_arrival"], kind: "datetime", group: "time" },
  {
    key: "requested_return",
    label: "Giờ trả mong muốn",
    columns: ["requested_return"],
    kind: "datetime",
    group: "time",
  },
];

export const GROUP_LABEL: Record<FieldDef["group"], string> = {
  goods: "Hàng hóa",
  irradiation: "Chiếu xạ và ưu tiên",
  time: "Thời gian",
};

/** Cột work order (vd pkg_width_cm) → trường trích xuất (package_dimensions_cm). */
export function fieldKeyOf(column: string): string {
  return FIELD_DEFS.find((d) => (d.columns as string[]).includes(column))?.key ?? column;
}

export function fieldLabel(key: string | null): string {
  if (!key) return "Cả ticket";
  return FIELD_DEFS.find((d) => d.key === key)?.label ?? key;
}

// ---------- Nhãn ----------

export const SOURCE_LABEL: Record<SourceKind, string> = {
  VERBATIM: "Nguyên văn",
  INFERRED: "AI suy luận",
  CONVERTED: "Đã quy đổi",
  OCR_LOW: "OCR tin cậy thấp",
  MANUAL: "Nhập tay",
  DEFAULT: "Mặc định",
};

/** Class badge theo nhãn nguồn — cần người chú ý thì nổi bật. */
export const SOURCE_TONE: Record<SourceKind, string> = {
  VERBATIM: "badge",
  INFERRED: "badge badge-warn",
  CONVERTED: "badge badge-primary",
  OCR_LOW: "badge badge-danger",
  MANUAL: "badge badge-success",
  DEFAULT: "badge badge-warn",
};

export const PRIORITY_LABEL: Record<Priority, string> = { NORMAL: "Thường", URGENT: "Khẩn", VIP: "VIP" };

export const REVIEW_LABEL: Record<ReviewStatus, string> = {
  AUTO_ACCEPTED: "Tự động tạo lệnh",
  ACCEPTED_WITH_WARNINGS: "Đã tạo lệnh · có cảnh báo",
  NEEDS_REVIEW: "Cần xác nhận",
  NEEDS_CLARIFICATION: "Chờ khách bổ sung",
};

export const REVIEW_TONE: Record<ReviewStatus, string> = {
  AUTO_ACCEPTED: "badge badge-success",
  ACCEPTED_WITH_WARNINGS: "badge badge-warn",
  NEEDS_REVIEW: "badge badge-danger",
  NEEDS_CLARIFICATION: "badge badge-warn",
};

export const STATE_LABEL: Record<string, string> = {
  DRAFT: "Nháp",
  FEASIBILITY_CHECK: "Kiểm tra khả thi",
};

export const ERROR_MESSAGE: Record<ErrorCode, string> = {
  MISSING: "Bắt buộc — nguồn không nêu, cần hỏi khách.",
  NOT_POSITIVE: "Phải lớn hơn 0.",
  RETURN_NOT_AFTER_ARRIVAL: "Giờ trả phải sau giờ hàng đến.",
  DOSE_OUT_OF_RANGE: "Liều phải trong khoảng 0 < liều ≤ 25 kGy.",
};

/** Lệnh nhập tay không có nguồn để hỏi lại — thông báo thiếu trường khác đi. */
export function errorMessage(code: ErrorCode, manual: boolean): string {
  return manual && code === "MISSING" ? "Bắt buộc — nhập giá trị." : ERROR_MESSAGE[code];
}

export const FLAG_LABEL: Record<FlagCode, string> = {
  LOW_CONFIDENCE: "Độ tin cậy thấp",
  BOUNDARY_UNCERTAIN: "Không chắc ranh giới ticket",
  AMBIGUOUS_OCR: "Đọc chưa rõ",
  INFERRED_VALUE: "Giá trị AI suy luận",
  DEFAULT_VALUE: "Giá trị mặc định",
  POSSIBLE_DUPLICATE: "Có thể trùng đơn (file đã tải trước đó)",
};

// ---------- Tiến độ job (4 bước UI) ----------

export const STEPS: { step: IngestStep; label: string }[] = [
  { step: "UPLOADED", label: "Tải lên" },
  { step: "READING", label: "Đọc PDF / OCR" },
  { step: "DETECTING", label: "Nhận diện ticket" },
  { step: "EXTRACTING", label: "Trích xuất 8 trường" },
];

/** Sau upload 1 file → 1 lệnh: còn DRAFT (cần xác nhận / chờ khách) → mở màn xác nhận; đã tự tạo lệnh → về Kanban. */
export const afterUploadPath = (wo: Pick<JobWorkOrder, "id" | "state">) =>
  wo.state === "DRAFT" ? `/intake/${wo.id}` : "/board";

/** Chờ giữa 2 lần hỏi trạng thái job: 1s rồi giãn ×1.5, tối đa 5s — OCR ~30s chỉ còn ~10 lần gọi thay vì ~30. */
export const pollDelay = (attempt: number, base = 1000, max = 5000) => Math.min(Math.round(base * 1.5 ** attempt), max);

/** Trạng thái từng bước: done / active / todo. DONE → tất cả done; FAILED → bước đang chạy báo lỗi. */
export function stepStates(job: Pick<IngestJob, "step" | "status">, lastStep: IngestStep = "UPLOADED") {
  const current = job.step === "FAILED" ? lastStep : job.step;
  const idx = current === "DONE" ? STEPS.length : STEPS.findIndex((s) => s.step === current);
  return STEPS.map((s, i) => {
    if (i < idx) return "done" as const;
    if (i === idx) return job.step === "FAILED" ? ("failed" as const) : ("active" as const);
    return "todo" as const;
  });
}

// ---------- PDF gốc: bản demo lưu file trên filesystem tạm (ADR-0012) → có thể đã mất ----------

export type SourcePdfOutcome = "ok" | "missing" | "error";

/** 404 = file đã mất sau deploy/restart (hoặc không tồn tại) → báo rõ thay vì nhúng trang lỗi JSON. */
export function sourcePdfOutcome(status: number): SourcePdfOutcome {
  if (status >= 200 && status < 300) return "ok";
  return status === 404 ? "missing" : "error";
}

export const SOURCE_PDF_MESSAGE: Record<Exclude<SourcePdfOutcome, "ok">, string> = {
  missing:
    "File gốc không còn trên server (bản demo lưu file tạm, mất sau mỗi lần triển khai lại). Đối chiếu bằng trang và đoạn nguồn cạnh từng trường.",
  error: "Không tải được file gốc. Thử tải lại trang.",
};

export const JOB_ERROR: Record<string, string> = {
  OCR_FAILED: "Không đọc được nội dung PDF (bản scan quá mờ hoặc Order Agent lỗi). Bạn có thể tải file khác hoặc nhập tay.",
};

// ---------- Giờ: ô datetime-local theo giờ Việt Nam (UTC+7, không có giờ mùa hè) ----------

const VN_OFFSET_MS = 7 * 3600 * 1000;

/** ISO có múi giờ → "YYYY-MM-DDTHH:MM" giờ Việt Nam cho <input type="datetime-local">. */
export function toLocalInput(iso: string | null): string {
  if (!iso) return "";
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return "";
  return new Date(t + VN_OFFSET_MS).toISOString().slice(0, 16);
}

/** "YYYY-MM-DDTHH:MM" giờ Việt Nam → ISO có múi giờ +07:00; rỗng → null. */
export function fromLocalInput(value: string): string | null {
  return value ? `${value}:00+07:00` : null;
}

export function formatVN(iso: string | null): string {
  const v = toLocalInput(iso);
  if (!v) return "—";
  const [d, t] = v.split("T");
  const [y, m, day] = d.split("-");
  return `${t} ${day}/${m}/${y}`;
}

// ---------- Form ----------

export type FormValues = Record<Column, string>;

export function toForm(f: WorkOrderFields): FormValues {
  const s = (v: number | string | null) => (v === null || v === undefined ? "" : String(v));
  return {
    product_name: s(f.product_name),
    quantity: s(f.quantity),
    pkg_length_cm: s(f.pkg_length_cm),
    pkg_width_cm: s(f.pkg_width_cm),
    pkg_height_cm: s(f.pkg_height_cm),
    pkg_weight_kg: s(f.pkg_weight_kg),
    required_dose_kgy: s(f.required_dose_kgy),
    priority: s(f.priority),
    expected_arrival: toLocalInput(f.expected_arrival),
    requested_return: toLocalInput(f.requested_return),
  };
}

function parseColumn(column: Column, raw: string): string | number | null {
  const v = raw.trim();
  if (!v) return null;
  if (column === "product_name" || column === "priority") return v;
  if (column === "expected_arrival" || column === "requested_return") return fromLocalInput(v);
  const n = Number(v.replace(",", "."));
  return Number.isFinite(n) ? n : null;
}

/** Chỉ các cột người đã đổi so với dữ liệu server → body PATCH `{fields}`. */
export function changedFields(original: WorkOrderFields, form: FormValues): Partial<Record<Column, unknown>> {
  const base = toForm(original);
  const out: Partial<Record<Column, unknown>> = {};
  for (const c of Object.keys(form) as Column[]) {
    if (form[c].trim() !== base[c].trim()) out[c] = parseColumn(c, form[c]);
  }
  return out;
}

/** Xác nhận 1 trường = gửi lại giá trị đang hiển thị (server đổi nhãn thành MANUAL). */
export function confirmPayload(def: FieldDef, form: FormValues): Partial<Record<Column, unknown>> {
  return Object.fromEntries(def.columns.map((c) => [c, parseColumn(c, form[c])]));
}

/** Lỗi validator theo trường trích xuất (3 cột kích thước gộp về 1 trường). */
export function errorsByField(errors: WorkOrderReview["errors"]): Record<string, ErrorCode> {
  const out: Record<string, ErrorCode> = {};
  for (const e of errors) out[fieldKeyOf(e.field)] ??= e.code;
  return out;
}

export function shortId(id: string): string {
  return `WO-${id.slice(0, 6).toUpperCase()}`;
}

export interface PickedFile {
  name: string;
  size: number;
  type: string;
}

/** Lọc file kéo thả / chọn nhiều: chỉ PDF, ≤ maxMb, bỏ file trùng (cùng tên + dung lượng) với danh sách đã có. */
export function pickPdfFiles<F extends PickedFile>(
  incoming: F[],
  existing: PickedFile[],
  maxMb: number,
): { accepted: F[]; rejected: { name: string; reason: string }[] } {
  const seen = new Set(existing.map((f) => `${f.name}|${f.size}`));
  const accepted: F[] = [];
  const rejected: { name: string; reason: string }[] = [];
  for (const f of incoming) {
    const key = `${f.name}|${f.size}`;
    const isPdf = f.type ? f.type === "application/pdf" : f.name.toLowerCase().endsWith(".pdf");
    if (!isPdf) rejected.push({ name: f.name, reason: "chỉ nhận file PDF" });
    else if (f.size > maxMb * 1024 * 1024) rejected.push({ name: f.name, reason: `vượt ${maxMb} MB` });
    else if (!seen.has(key)) {
      seen.add(key);
      accepted.push(f);
    }
  }
  return { accepted, rejected };
}
