"use client";

// Xác nhận ticket → lệnh — ADC-001 (T-021). Tài liệu gốc (trình xem PDF của trình duyệt, không highlight)
// + form 8 trường kèm nhãn nguồn / trang / đoạn nguồn; lỗi dưới từng trường; câu hỏi bổ sung; lưu & submit; xóa nháp.
// Lệnh đã tạo: banner rủi ro giờ trả OK / WARN / BLOCK (ADC-005, T-039). Lịch sử trạng thái (ADC-006, T-041).
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { HistoryTimeline } from "@/components/HistoryTimeline";
import { DurationBreakdown } from "@/components/cards";
import { NewOrderRisk } from "@/components/RiskBanner";
import { ackIntakeWarning, ApiError, deleteWorkOrder, getIntake, getSourcePdf, patchWorkOrder, submitWorkOrder } from "@/lib/api";
import {
  changedFields,
  type Column,
  confirmPayload,
  errorMessage,
  errorsByField,
  type Extraction,
  FIELD_DEFS,
  type FieldDef,
  fieldLabel,
  FLAG_LABEL,
  type FormValues,
  formatVN,
  GROUP_LABEL,
  PRIORITY_LABEL,
  type Priority,
  REVIEW_LABEL,
  REVIEW_TONE,
  shortId,
  SOURCE_LABEL,
  SOURCE_PDF_MESSAGE,
  SOURCE_TONE,
  STATE_LABEL,
  toForm,
  type WorkOrderReview,
} from "@/lib/intake";
import { canCheckRisk } from "@/lib/risk";
import { can, type Role } from "@/lib/roles";

const DIM_LABEL: Partial<Record<Column, string>> = { pkg_length_cm: "Dài", pkg_width_cm: "Rộng", pkg_height_cm: "Cao" };
const DOSES = ["5", "10", "25"];

type PdfState = { kind: "loading" } | { kind: "ok"; url: string } | { kind: "missing" } | { kind: "error" };

/** Tải PDF trước rồi nhúng blob — file có thể đã mất trên filesystem tạm của bản demo (ADR-0012). */
function SourcePdf({ fileId, page, name }: { fileId: string; page: number; name: string | null }) {
  const [pdf, setPdf] = useState<PdfState>({ kind: "loading" });
  useEffect(() => {
    let alive = true;
    let url: string | null = null;
    getSourcePdf(fileId)
      .then((blob) => {
        if (!alive) return;
        if (blob === null) return setPdf({ kind: "missing" });
        url = URL.createObjectURL(blob);
        setPdf({ kind: "ok", url });
      })
      .catch(() => alive && setPdf({ kind: "error" }));
    return () => {
      alive = false;
      if (url) URL.revokeObjectURL(url);
    };
  }, [fileId]);

  if (pdf.kind === "loading") return <p className="muted small" style={{ margin: 0 }}>Đang tải file gốc…</p>;
  if (pdf.kind !== "ok") return <p className="small" role="status" style={{ margin: 0 }}>{SOURCE_PDF_MESSAGE[pdf.kind]}</p>;
  return (
    <>
      <iframe className="pdf-frame" src={`${pdf.url}#page=${page}&view=FitH`} title={`Tài liệu gốc ${name ?? ""}`} />
      <a className="btn btn-sm" href={`/api/files/${fileId}`} target="_blank" rel="noopener" style={{ alignSelf: "flex-start" }}>
        Mở file gốc ở tab mới
      </a>
    </>
  );
}

function SourceDoc({ r }: { r: WorkOrderReview }) {
  const s = r.source;
  return (
    <section className="card doc-card" aria-labelledby="doc-title">
      <h2 className="card-title" id="doc-title">
        Tài liệu gốc
      </h2>
      {s.type === "PDF" && s.file_id ? (
        <>
          <p className="small muted" style={{ margin: 0 }}>
            <strong>{s.file_name}</strong> · {s.page_count} trang
            {s.page_from && ` · ticket ở trang ${s.page_from}${s.page_to && s.page_to !== s.page_from ? `–${s.page_to}` : ""}`}
            {s.channel && ` · ${s.channel}`} · nhận {formatVN(s.received_at)} · {s.ocr_used ? "PDF scan · đã OCR" : "PDF văn bản"}
          </p>
          <SourcePdf fileId={s.file_id} page={s.page_from ?? 1} name={s.file_name} />
        </>
      ) : s.type === "TEXT" ? (
        <>
          <p className="small muted" style={{ margin: 0 }}>
            Nội dung dán
          </p>
          <pre className="raw-text">{s.raw_text}</pre>
        </>
      ) : (
        <p className="muted small" style={{ margin: 0 }}>
          Nhập tay — không có tài liệu gốc.
        </p>
      )}
    </section>
  );
}

function SourceLine({ ex, flagged, manual }: { ex?: Extraction; flagged: boolean; manual: boolean }) {
  if (!ex) return <span className="badge">{manual ? "Chưa nhập" : "Không có trong nguồn"}</span>;
  return (
    <span className="source-line">
      {ex.page && <span className="small muted">Trang {ex.page} ·</span>}
      <span className={flagged ? "badge badge-danger" : SOURCE_TONE[ex.source_kind]}>{SOURCE_LABEL[ex.source_kind]}</span>
      {ex.confidence !== null && ex.confidence < 0.9 && (
        <span className="small muted">tin cậy {Math.round(ex.confidence * 100)}%</span>
      )}
    </span>
  );
}

function FieldInput({
  def,
  form,
  setForm,
  disabled,
  describedBy,
  invalid,
}: {
  def: FieldDef;
  form: FormValues;
  setForm: (f: FormValues) => void;
  disabled: boolean;
  describedBy: string;
  invalid: boolean;
}) {
  const id = `field-${def.key}`;
  const common = { disabled, "aria-describedby": describedBy, "aria-invalid": invalid || undefined };
  const set = (c: Column, v: string) => setForm({ ...form, [c]: v });

  if (def.kind === "dims") {
    return (
      <div className="dims" role="group" aria-labelledby={`${id}-label`} id={id}>
        {def.columns.map((c) => (
          <label key={c} className="dim">
            <span className="sr-only">{DIM_LABEL[c]}</span>
            <input
              className="input"
              inputMode="decimal"
              placeholder={DIM_LABEL[c]}
              value={form[c]}
              onChange={(e) => set(c, e.target.value)}
              {...common}
            />
          </label>
        ))}
        <span className="muted small">{def.unit}</span>
      </div>
    );
  }
  const c = def.columns[0];
  if (def.kind === "priority") {
    return (
      <select id={id} className="select" value={form[c]} onChange={(e) => set(c, e.target.value)} {...common}>
        <option value="">— Chưa có —</option>
        {(Object.keys(PRIORITY_LABEL) as Priority[]).map((p) => (
          <option key={p} value={p}>
            {PRIORITY_LABEL[p]}
          </option>
        ))}
      </select>
    );
  }
  const input = (
    <input
      id={id}
      className="input"
      type={def.kind === "datetime" ? "datetime-local" : "text"}
      inputMode={def.kind === "int" ? "numeric" : def.kind === "number" ? "decimal" : undefined}
      list={def.key === "required_dose_kgy" ? "doses" : undefined}
      value={form[c]}
      onChange={(e) => set(c, e.target.value)}
      {...common}
    />
  );
  return def.unit ? (
    <div className="with-unit">
      {input}
      <span className="muted small">{def.unit}</span>
    </div>
  ) : (
    input
  );
}

function Review({ id, role }: { id: string; role: Role }) {
  const [r, setR] = useState<WorkOrderReview | null>(null);
  const [form, setForm] = useState<FormValues | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  // Nhập tay: chưa báo lỗi khi form còn trống — chỉ báo sau lần bấm "Xác nhận & tạo lệnh" đầu tiên
  const [attempted, setAttempted] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const router = useRouter();

  const apply = useCallback((next: WorkOrderReview) => {
    setR(next);
    setForm(toForm(next.fields));
  }, []);

  useEffect(() => {
    getIntake(id)
      .then(apply)
      .catch((e) => setError(e instanceof ApiError && e.status === 404 ? "Không tìm thấy lệnh." : "Không tải được lệnh."));
  }, [id, apply]);

  if (error && !r) {
    return (
      <div className="card span-all">
        <div className="notice notice-error" role="alert">
          {error}
        </div>
        <Link href="/intake">← Về Tiếp nhận đơn</Link>
      </div>
    );
  }
  if (!r || !form) return <p className="muted span-all">Đang tải…</p>;

  const isDraft = r.state === "DRAFT";
  const manual = r.source.type === "MANUAL";
  const changes = changedFields(r.fields, form);
  const dirty = Object.keys(changes).length > 0;
  const showIssues = !manual || attempted;
  const errs = showIssues ? errorsByField(r.errors) : {};
  const extraction = Object.fromEntries(r.extractions.map((e) => [e.field, e]));
  const unconfirmed = new Set(r.unconfirmed_fields);
  const openQuestions = showIssues ? r.clarifications.filter((c) => c.status === "OPEN") : [];
  const openWarnings = r.warnings.filter((w) => w.status === "OPEN");

  async function run(action: () => Promise<WorkOrderReview>, done?: string) {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      apply(await action());
      if (done) setNotice(done);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Thao tác thất bại.");
      getIntake(id).then(apply).catch(() => undefined);
    } finally {
      setBusy(false);
    }
  }

  const save = () => run(() => patchWorkOrder(id, changes), "Đã lưu nháp.");
  const confirm = (def: FieldDef) => run(() => patchWorkOrder(id, confirmPayload(def, form)), `Đã xác nhận ${def.label}.`);
  const submit = () =>
    run(async () => {
      setAttempted(true);
      const saved = dirty ? await patchWorkOrder(id, changes) : r;
      if (!saved.can_submit) return saved; // lỗi hiện ngay dưới trường
      return submitWorkOrder(id);
    });
  async function remove() {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await deleteWorkOrder(id);
      router.replace("/intake");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Xóa nháp thất bại.");
      setConfirmDelete(false);
      setBusy(false);
      getIntake(id).then(apply).catch(() => undefined);
    }
  }
  async function ack(warningId: number) {
    await ackIntakeWarning(warningId).catch(() => undefined);
    getIntake(id).then(apply).catch(() => undefined);
  }
  async function copyQuestions() {
    const text = openQuestions.map((q, i) => `${i + 1}. ${q.question}`).join("\n");
    try {
      await navigator.clipboard.writeText(text);
      setNotice("Đã sao chép câu hỏi.");
    } catch {
      setError("Trình duyệt chặn sao chép — hãy bôi đen và sao chép thủ công.");
    }
  }

  const errorList = FIELD_DEFS.filter((d) => errs[d.key]);
  const flaggedList = FIELD_DEFS.filter((d) => unconfirmed.has(d.key));

  return (
    <>
      <div className="intake-layout span-all">
        <SourceDoc r={r} />

        <section className="card" aria-labelledby="wo-title">
          <div className="row" style={{ justifyContent: "space-between" }}>
            <div>
              <div className="small muted">{isDraft ? "Lệnh sản xuất nháp" : "Lệnh sản xuất"}</div>
              <h2 className="card-title mono" id="wo-title">
                {shortId(r.id)}
              </h2>
            </div>
            <div className="row">
              <span className="badge">{STATE_LABEL[r.state] ?? r.state}</span>
              {r.review_status && showIssues && <span className={REVIEW_TONE[r.review_status]}>{REVIEW_LABEL[r.review_status]}</span>}
            </div>
          </div>

          {!isDraft && (
            <div className="notice notice-success" role="status">
              Đã tạo lệnh — đang ở bước kiểm tra khả thi. Xếp lịch làm ở bước tiếp theo.
            </div>
          )}
          {canCheckRisk(r.state) && r.estimate && (
            <NewOrderRisk workOrderId={r.id} canSchedule={can(role, "EDIT_SCHEDULE")} />
          )}
          {!isDraft && (
            <section className="estimate-box" aria-labelledby="est-title">
              <h3 id="est-title" className="small" style={{ margin: 0 }}>
                Ước tính thời lượng
              </h3>
              {r.estimate ? (
                <DurationBreakdown e={r.estimate} />
              ) : (
                <div className="notice notice-warn">
                  Chưa ước tính được thời lượng{r.estimate_error ? `: ${r.estimate_error}` : ""}.
                </div>
              )}
            </section>
          )}
          <details className="estimate-box">
            <summary className="small" style={{ fontWeight: 600, cursor: "pointer" }}>
              Lịch sử trạng thái
            </summary>
            <HistoryTimeline key={`${r.id}-${r.state}`} workOrderId={r.id} />
          </details>
          {openWarnings.length > 0 && (
            <div className="notice notice-warn">
              <div className="stack" style={{ gap: 6 }}>
                <strong>Lệnh đã tạo kèm cảnh báo — hãy xem lại:</strong>
                <ul className="plain-list">
                  {openWarnings.map((w) => (
                    <li key={w.id} className="row" style={{ justifyContent: "space-between" }}>
                      <span>
                        {fieldLabel(w.field)}: {FLAG_LABEL[w.code]}
                      </span>
                      <button className="btn btn-sm" onClick={() => ack(w.id)}>
                        Đã xem
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          )}
          {isDraft && (errorList.length > 0 || flaggedList.length > 0 || r.boundary_uncertain) && (
            <div className="notice notice-error" role="alert" aria-labelledby="summary-title">
              <div className="stack" style={{ gap: 6 }}>
                <strong id="summary-title">Chưa thể tạo lệnh</strong>
                <ul className="plain-list">
                  {errorList.map((d) => (
                    <li key={d.key}>
                      <a href={`#field-${d.key}`}>{d.label}</a>: {errorMessage(errs[d.key], manual)}
                    </li>
                  ))}
                  {flaggedList.map((d) => (
                    <li key={d.key}>
                      <a href={`#field-${d.key}`}>{d.label}</a>: độ tin cậy thấp — đối chiếu file gốc rồi bấm “Xác nhận”.
                    </li>
                  ))}
                  {r.boundary_uncertain && (
                    <li>AI không chắc ticket này bắt đầu/kết thúc ở trang nào — kiểm tra file gốc trước khi tạo lệnh.</li>
                  )}
                </ul>
              </div>
            </div>
          )}

          {(["goods", "irradiation", "time"] as const).map((group) => (
            <fieldset key={group} className="field-group">
              <legend>{GROUP_LABEL[group]}</legend>
              {FIELD_DEFS.filter((d) => d.group === group).map((def) => {
                const n = FIELD_DEFS.indexOf(def) + 1;
                const flagged = unconfirmed.has(def.key);
                const code = errs[def.key];
                const ex = extraction[def.key];
                const hintId = `hint-${def.key}`;
                const errId = `err-${def.key}`;
                return (
                  <div key={def.key} className={`intake-field${flagged ? " flagged" : ""}${code ? " has-error" : ""}`}>
                    <div className="row" style={{ justifyContent: "space-between" }}>
                      <label id={`field-${def.key}-label`} htmlFor={`field-${def.key}`} className="field-label">
                        {n} · {def.label}
                      </label>
                      <SourceLine ex={ex} flagged={flagged} manual={manual} />
                    </div>
                    <FieldInput
                      def={def}
                      form={form}
                      setForm={setForm}
                      disabled={!isDraft || busy}
                      describedBy={`${hintId}${code ? ` ${errId}` : ""}`}
                      invalid={Boolean(code) || flagged}
                    />
                    <div id={hintId} className="small muted">
                      {ex?.snippet ? <>Nguồn: “{ex.snippet}”</> : null}
                    </div>
                    {code && (
                      <div id={errId} className="field-error">
                        {errorMessage(code, manual)}
                      </div>
                    )}
                    {flagged && isDraft && (
                      <button className="btn btn-sm" onClick={() => confirm(def)} disabled={busy}>
                        Xác nhận giá trị này
                      </button>
                    )}
                  </div>
                );
              })}
            </fieldset>
          ))}
          <datalist id="doses">
            {DOSES.map((d) => (
              <option key={d} value={d} />
            ))}
          </datalist>

          {openQuestions.length > 0 && (
            <section className="questions" aria-labelledby="q-title">
              <h3 id="q-title" className="small" style={{ margin: 0 }}>
                Câu hỏi bổ sung gửi khách
              </h3>
              <ol>
                {openQuestions.map((q) => (
                  <li key={q.field}>
                    {q.question} <span className="small muted">— {fieldLabel(q.field)}</span>
                  </li>
                ))}
              </ol>
              <button className="btn btn-sm" onClick={copyQuestions} style={{ alignSelf: "flex-start" }}>
                Sao chép câu hỏi
              </button>
            </section>
          )}

          <div aria-live="polite">
            {notice && <div className="notice notice-success">{notice}</div>}
            {error && (
              <div className="notice notice-error" role="alert">
                {error}
              </div>
            )}
          </div>

          {isDraft && confirmDelete && (
            <div className="notice notice-error" role="alertdialog" aria-labelledby="del-title">
              <div className="stack" style={{ gap: 6 }}>
                <strong id="del-title">Xóa lệnh nháp {shortId(r.id)}?</strong>
                <span className="small">
                  Lệnh và dữ liệu đã trích xuất sẽ bị xóa, không khôi phục được.
                  {r.source.type === "PDF" && " File PDF gốc vẫn được giữ."}
                </span>
                <div className="row" style={{ justifyContent: "flex-end" }}>
                  <button className="btn btn-sm" onClick={() => setConfirmDelete(false)} disabled={busy} autoFocus>
                    Hủy
                  </button>
                  <button className="btn btn-sm btn-danger" onClick={remove} disabled={busy}>
                    Xóa nháp
                  </button>
                </div>
              </div>
            </div>
          )}

          {isDraft && (
            <div className="row" style={{ justifyContent: "flex-end" }}>
              <button
                className="btn btn-ghost btn-danger-text"
                onClick={() => setConfirmDelete(true)}
                disabled={busy || confirmDelete}
                style={{ marginRight: "auto" }}
              >
                Xóa nháp
              </button>
              <Link className="btn btn-ghost" href="/intake">
                Để sau
              </Link>
              <button className="btn" onClick={save} disabled={!dirty || busy}>
                Lưu nháp
              </button>
              <button className="btn btn-primary" onClick={submit} disabled={busy || (!dirty && !r.can_submit)}>
                Xác nhận & tạo lệnh
              </button>
            </div>
          )}
        </section>
      </div>
    </>
  );
}

export default function IntakeReviewPage() {
  const { id } = useParams<{ id: string }>();
  return (
    <AppShell allow={["SALES"]} crumb="Vận hành / Tiếp nhận đơn / Xác nhận lệnh" title="Xác nhận lệnh">
      {(me) => <Review id={id} role={me.role!} />}
    </AppShell>
  );
}
