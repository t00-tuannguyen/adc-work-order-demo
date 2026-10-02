"use client";

// Hàng đợi escalation — ADC-005 §UI/UX (T-039). Đơn trễ giờ trả (tạo tự động, BR-06): số phút trễ, ưu tiên, giờ trả
// cũ → giờ dự kiến. Mở 1 mục: AI (Risk Agent) soạn nháp, người sửa rồi "Duyệt và đánh dấu đã gửi" — nháp không bao
// giờ tự gửi; MVP không gửi email thật. Soạn / duyệt: Kinh doanh, Quản lý vận hành.
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { ApiError, approveEscalation, draftEscalation, listEscalations } from "@/lib/api";
import { PRIORITY_CLASS, STATE_LABEL } from "@/lib/board";
import { formatVN, PRIORITY_LABEL, shortId } from "@/lib/intake";
import {
  delayText,
  type DraftResult,
  type Escalation,
  ESCALATION_STATUS_LABEL,
  ESCALATION_STATUS_TONE,
  ESCALATIONS_CHANGED,
  isOpen,
} from "@/lib/risk";
import { can, type Role } from "@/lib/roles";

const ALL: Role[] = ["SALES", "PLANNER", "OPS_MANAGER", "ADMIN"];
const FILTERS = [
  { key: "open", label: "Đang mở" },
  { key: "APPROVED", label: "Đã duyệt" },
  { key: "", label: "Tất cả" },
] as const;

type Notice = { tone: "success" | "warn" | "error"; text: string };

function Detail({
  esc,
  role,
  onChanged,
}: {
  esc: Escalation;
  role: Role;
  onChanged: (notice: Notice) => Promise<void>;
}) {
  const [text, setText] = useState(esc.final_message ?? esc.draft_message ?? "");
  const [source, setSource] = useState<DraftResult["source"] | null>(null);
  const [busy, setBusy] = useState(false);
  const allowed = can(role, "APPROVE_ESCALATION_MESSAGE");
  const editable = allowed && isOpen(esc);

  async function act(action: () => Promise<Notice>) {
    setBusy(true);
    try {
      await onChanged(await action());
    } catch (e) {
      await onChanged({ tone: "error", text: e instanceof ApiError ? e.message : "Thao tác thất bại." });
    } finally {
      setBusy(false);
    }
  }

  const draft = () =>
    act(async () => {
      const d = await draftEscalation(esc.id);
      setText(d.message_draft);
      setSource(d.source);
      return d.source === "LLM"
        ? { tone: "success", text: "AI đã soạn nháp — đọc kỹ, sửa nếu cần rồi duyệt." }
        : { tone: "warn", text: "AI soạn thông điệp đang tắt hoặc lỗi — đã điền mẫu soạn sẵn, hãy sửa tay." };
    });

  const approve = () =>
    act(async () => {
      await approveEscalation(esc.id, text);
      return { tone: "success", text: `Đã duyệt thông điệp cho ${esc.product_name ?? shortId(esc.work_order_id)}.` };
    });

  return (
    <section className="card" aria-labelledby="esc-title">
      <div className="row" style={{ justifyContent: "space-between", flexWrap: "wrap", gap: 8 }}>
        <h2 className="card-title" id="esc-title" style={{ margin: 0 }}>
          {esc.product_name || "—"} <span className="mono small muted">{shortId(esc.work_order_id)}</span>
        </h2>
        <span className={ESCALATION_STATUS_TONE[esc.status]}>{ESCALATION_STATUS_LABEL[esc.status]}</span>
      </div>
      <dl className="kv">
        <dt>Ưu tiên</dt>
        <dd>{esc.priority ? <span className={PRIORITY_CLASS[esc.priority]}>{PRIORITY_LABEL[esc.priority]}</span> : "—"}</dd>
        <dt>Giờ trả đã hẹn</dt>
        <dd>{formatVN(esc.requested_return)}</dd>
        <dt>Giờ xong dự kiến</dt>
        <dd>
          {formatVN(esc.expected_finish)} <span className="badge badge-danger">trễ {delayText(esc.delay_min)}</span>
        </dd>
        <dt>Nguyên nhân</dt>
        <dd>{esc.incident_id ? `Sự cố line #${esc.incident_id}` : "Bị đẩy lùi khi nhận đơn ưu tiên cao hơn"}</dd>
        <dt>Trạng thái lệnh</dt>
        <dd>{STATE_LABEL[esc.state] ?? esc.state}</dd>
      </dl>
      {esc.can_close && (
        <div className="notice notice-success">
          Đơn đã hết trễ theo lịch mới nhất (sự cố kết thúc sớm hoặc phương án bị từ chối) — có thể đóng mục này.
        </div>
      )}
      <div className="field">
        <label htmlFor="esc-message">
          Thông điệp cho khách{" "}
          {source && <span className="badge">{source === "LLM" ? "AI soạn nháp" : "Mẫu soạn sẵn"}</span>}
        </label>
        <textarea
          id="esc-message"
          className="textarea"
          rows={9}
          maxLength={2000}
          value={text}
          readOnly={!editable || esc.status === "OPEN"}
          placeholder={editable ? "Bấm “AI soạn nháp” để có bản nháp, rồi sửa trước khi duyệt." : "Chưa có thông điệp."}
          onChange={(e) => setText(e.target.value)}
        />
        {esc.approved_at && (
          <span className="small muted">Đã duyệt lúc {formatVN(esc.approved_at)} — MVP chưa gửi email thật.</span>
        )}
      </div>
      {editable && (
        <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
          <button className="btn" disabled={busy} onClick={draft}>
            {esc.status === "OPEN" ? "AI soạn nháp" : "Soạn lại"}
          </button>
          <button
            className="btn btn-primary"
            disabled={busy || esc.status !== "DRAFTED" || !text.trim()}
            title={esc.status !== "DRAFTED" ? "Cần có nháp trước khi duyệt" : undefined}
            onClick={approve}
          >
            Duyệt và đánh dấu đã gửi
          </button>
        </div>
      )}
      {!allowed && <p className="small muted">Chỉ Kinh doanh / Quản lý vận hành soạn và duyệt thông điệp.</p>}
    </section>
  );
}

function Queue({ role }: { role: Role }) {
  const [filter, setFilter] = useState<string>("open");
  const [items, setItems] = useState<Escalation[] | null>(null);
  const [selected, setSelected] = useState<number | null>(null);
  const [notice, setNotice] = useState<Notice | null>(null);

  const load = useCallback(
    (f: string) =>
      listEscalations(f || undefined)
        .then(setItems)
        .catch(() => setNotice({ tone: "error", text: "Không tải được hàng đợi escalation." })),
    [],
  );

  useEffect(() => {
    listEscalations("open")
      .then(setItems)
      .catch(() => setNotice({ tone: "error", text: "Không tải được hàng đợi escalation." }));
  }, []);

  async function changed(n: Notice) {
    setNotice(n);
    await load(filter);
    window.dispatchEvent(new Event(ESCALATIONS_CHANGED));
  }

  const current = items?.find((e) => e.id === selected) ?? null;

  return (
    <>
      <section className="card span-all">
        <div className="row" style={{ justifyContent: "space-between", flexWrap: "wrap", gap: 12 }}>
          <div className="row" role="tablist" aria-label="Lọc escalation" style={{ gap: 6 }}>
            {FILTERS.map((f) => (
              <button
                key={f.key}
                role="tab"
                aria-selected={filter === f.key}
                className={`btn btn-sm${filter === f.key ? " btn-primary" : ""}`}
                onClick={() => {
                  setFilter(f.key);
                  setSelected(null);
                  void load(f.key);
                }}
              >
                {f.label}
              </button>
            ))}
          </div>
          <span className="muted small">Tạo tự động cho mọi đơn trễ giờ trả · sắp VIP → Khẩn → Thường, trễ nhiều trước.</span>
        </div>
        {notice && (
          <div className={`notice notice-${notice.tone}`} role="status" style={{ marginTop: 12 }}>
            {notice.text}
          </div>
        )}
        {!items ? (
          <p className="muted">Đang tải…</p>
        ) : items.length === 0 ? (
          <p className="muted">Không có escalation nào.</p>
        ) : (
          <div className="table-wrap" style={{ marginTop: 12 }}>
            <table className="table">
              <thead>
                <tr>
                  <th>Đơn</th>
                  <th>Ưu tiên</th>
                  <th>Trễ</th>
                  <th>Giờ trả → dự kiến</th>
                  <th>Trạng thái</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {items.map((e) => (
                  <tr key={e.id} aria-selected={e.id === selected}>
                    <td>
                      {e.product_name || "—"}
                      <div className="mono small muted">{shortId(e.work_order_id)}</div>
                    </td>
                    <td>{e.priority && <span className={PRIORITY_CLASS[e.priority]}>{PRIORITY_LABEL[e.priority]}</span>}</td>
                    <td>
                      <span className="badge badge-danger">{delayText(e.delay_min)}</span>
                    </td>
                    <td className="small">
                      {formatVN(e.requested_return)} → {formatVN(e.expected_finish)}
                    </td>
                    <td>
                      <span className={ESCALATION_STATUS_TONE[e.status]}>{ESCALATION_STATUS_LABEL[e.status]}</span>
                      {e.can_close && <span className="badge badge-success">Có thể đóng</span>}
                    </td>
                    <td>
                      <button className="btn btn-sm" onClick={() => setSelected(e.id)}>
                        Mở
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
      {current && (
        <div className="span-all">
          <Detail key={current.id} esc={current} role={role} onChanged={changed} />
        </div>
      )}
      <p className="small muted span-all">
        Thông điệp chỉ được coi là đã gửi sau khi người duyệt bấm duyệt. Xem đơn trên <Link href="/board">Kanban</Link>.
      </p>
    </>
  );
}

export default function EscalationsPage() {
  return (
    <AppShell
      allow={ALL}
      crumb="Kiểm soát / Escalation"
      title="Escalation"
      subtitle="Đơn có nguy cơ trả trễ cần kinh doanh liên hệ khách. AI soạn nháp, người duyệt trước khi gửi."
    >
      {(me) => <Queue role={me.role!} />}
    </AppShell>
  );
}
