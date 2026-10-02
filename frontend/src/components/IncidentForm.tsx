"use client";

// Khai báo sự cố line — ADC-004 (T-031): nút "Khai báo sự cố" → form line, thời điểm, thời gian dừng dự kiến, ghi chú.
// Backend tính phương án (luôn chờ duyệt, lịch ACTIVE giữ nguyên); ở đây chỉ tóm tắt — màn Trước / Sau ở /incidents/[id].
import Link from "next/link";
import { useState } from "react";

import { ApiError, declareIncident } from "@/lib/api";
import { hhmm, PLAN_STATUS_LABEL, PRIORITY_CLASS } from "@/lib/board";
import { formatDuration } from "@/lib/estimate";
import {
  defaultIncidentForm,
  downtimeEnd,
  type Incident,
  type IncidentForm,
  incidentPayload,
  MAX_NOTE_LEN,
  OUTCOME_LABEL,
  slotTimeText,
  validateIncident,
} from "@/lib/incident";
import { formatVN, PRIORITY_LABEL, shortId } from "@/lib/intake";

function IncidentResult({ inc }: { inc: Incident }) {
  const pv = inc.proposed_plan_version;
  return (
    <div className="stack" style={{ gap: 8 }} aria-live="polite">
      <div className={`notice ${inc.affected_orders.length ? "notice-warn" : "notice-success"}`} role="status">
        Đã khai báo sự cố #{inc.incident_id}: Line {inc.line} dừng {hhmm(inc.start_at)}–{hhmm(inc.end_at)} (
        {formatVN(inc.start_at)} → {formatVN(inc.end_at)}).{" "}
        {pv
          ? `Phương án v${pv.id} · ${PLAN_STATUS_LABEL[pv.status]} — lịch đang áp dụng giữ nguyên tới khi duyệt.`
          : "Không có đơn nào bị ảnh hưởng."}
      </div>
      {inc.affected_orders.length > 0 && (
        <ul className="plain-list" style={{ gap: 10 }} aria-label="Đơn bị ảnh hưởng">
          {inc.affected_orders.map((a) => (
            <li key={a.work_order_id} className="stack" style={{ gap: 2 }}>
              <span>
                <span className="mono">{shortId(a.work_order_id)}</span> {a.product_name ?? ""}{" "}
                {a.priority && <span className={PRIORITY_CLASS[a.priority]}>{PRIORITY_LABEL[a.priority]}</span>}
              </span>
              <span className="small mono">
                {slotTimeText(a.old, inc.start_at)} → {slotTimeText(a.new, inc.start_at)}
              </span>
              <span className="small">
                {OUTCOME_LABEL[a.outcome]} · trả {formatVN(a.requested_return)}{" "}
                {a.sla_ok ? (
                  <span className="badge badge-success">Kịp</span>
                ) : (
                  <span className="badge badge-danger">Trễ</span>
                )}
              </span>
            </li>
          ))}
        </ul>
      )}
      <p className="small" style={{ margin: 0, whiteSpace: "pre-line" }}>
        {inc.explanation}
      </p>
      <Link className="btn btn-sm btn-primary" href={`/incidents/${inc.incident_id}`} style={{ alignSelf: "flex-start" }}>
        So sánh trước / sau
      </Link>
    </div>
  );
}

/** `onDeclared`: thay cho tóm tắt tại chỗ (vd màn danh sách chuyển thẳng sang so sánh trước / sau). */
export function IncidentCard({ onDeclared }: { onDeclared?: (inc: Incident) => void } = {}) {
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState<IncidentForm>(() => defaultIncidentForm());
  const [touched, setTouched] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<Incident | null>(null);

  const errors = touched ? validateIncident(form) : {};
  const end = downtimeEnd(form);
  const payload = incidentPayload(form);
  const set = (patch: Partial<IncidentForm>) => setForm((f) => ({ ...f, ...patch }));

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setTouched(true);
    if (!payload) return;
    setBusy(true);
    setError(null);
    try {
      const inc = await declareIncident(payload);
      if (onDeclared) return onDeclared(inc);
      setResult(inc);
      setOpen(false);
      setTouched(false);
      setForm(defaultIncidentForm());
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Không khai báo được sự cố.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card" aria-labelledby="incident-title">
      <h2 className="card-title" id="incident-title">
        Khai báo sự cố line
      </h2>
      <p className="card-sub">
        Khai báo line dừng và thời gian dừng dự kiến; hệ thống tìm đơn bị ảnh hưởng và đề xuất lịch mới theo ưu tiên VIP
        → Khẩn → Thường. Phương án luôn chờ duyệt (ADC-004).
      </p>
      {!open && (
        <button
          className="btn btn-danger"
          onClick={() => {
            setOpen(true);
            setError(null);
          }}
          style={{ alignSelf: "flex-start" }}
        >
          Khai báo sự cố
        </button>
      )}
      {open && (
        <form className="stack" style={{ gap: 10 }} onSubmit={submit} noValidate>
          <div className="form-grid">
            <label className="field" style={{ gridColumn: "1 / -1" }}>
              Bắt đầu dừng
              <input
                className="input"
                type="datetime-local"
                step={900}
                value={form.start}
                onChange={(e) => set({ start: e.target.value })}
                disabled={busy}
                aria-invalid={!!errors.start}
              />
              {errors.start && <span className="field-error">{errors.start}</span>}
            </label>
            <label className="field">
              Line
              <select
                className="select"
                value={form.line}
                onChange={(e) => set({ line: e.target.value as IncidentForm["line"] })}
                disabled={busy}
              >
                <option value="A">Line A</option>
                <option value="B">Line B</option>
              </select>
            </label>
            <div className="field">
              <span>Thời gian dừng dự kiến</span>
              <div className="with-unit">
                <input
                  className="input"
                  inputMode="numeric"
                  value={form.hours}
                  onChange={(e) => set({ hours: e.target.value })}
                  disabled={busy}
                  aria-label="Số giờ dừng"
                  aria-invalid={!!errors.downtime}
                />
                <span className="small muted">giờ</span>
                <input
                  className="input"
                  inputMode="numeric"
                  value={form.minutes}
                  onChange={(e) => set({ minutes: e.target.value })}
                  disabled={busy}
                  aria-label="Số phút dừng"
                  aria-invalid={!!errors.downtime}
                />
                <span className="small muted">phút</span>
              </div>
              {errors.downtime && <span className="field-error">{errors.downtime}</span>}
            </div>
          </div>
          <label className="field">
            Ghi chú
            <textarea
              className="textarea"
              rows={2}
              maxLength={MAX_NOTE_LEN}
              value={form.note}
              onChange={(e) => set({ note: e.target.value })}
              disabled={busy}
              placeholder="Ví dụ: hỏng băng tải, chờ kỹ thuật"
            />
            {errors.note && <span className="field-error">{errors.note}</span>}
          </label>
          {payload && end && (
            <p className="small" style={{ margin: 0 }}>
              Line {payload.line} dừng {formatVN(payload.start_at)} → {formatVN(end)} (
              {formatDuration(payload.est_downtime_min)})
            </p>
          )}
          {error && (
            <div className="notice notice-error" role="alert">
              {error}
            </div>
          )}
          <div className="row" style={{ gap: 6 }}>
            <button className="btn btn-sm btn-danger" type="submit" disabled={busy}>
              {busy ? "Đang tính phương án…" : "Khai báo"}
            </button>
            <button className="btn btn-sm btn-ghost" type="button" onClick={() => setOpen(false)} disabled={busy}>
              Hủy
            </button>
          </div>
        </form>
      )}
      {result && <IncidentResult inc={result} />}
    </section>
  );
}
