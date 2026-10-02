"use client";

import Link from "next/link";
import { useState } from "react";

import { ApiError, type DemoResetResult, resetDemo } from "@/lib/api";
import { breakdownRows, type EstimateResult, formatDuration, formatMinutes, SIM_LABEL as SIM } from "@/lib/estimate";
import { type Action, PERMISSIONS, type Role, ROLE_LABEL } from "@/lib/roles";

export function PermissionsCard({ role }: { role: Role }) {
  const actions = Object.entries(PERMISSIONS) as [Action, (typeof PERMISSIONS)[Action]][];
  return (
    <section className="card" aria-labelledby="perm-title">
      <h2 className="card-title" id="perm-title">
        Quyền của {ROLE_LABEL[role]}
      </h2>
      <p className="card-sub">Theo ma trận quyền (specs/user-roles.md). Backend kiểm tra lại ở mọi API.</p>
      <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "flex", flexDirection: "column", gap: 6 }}>
        {actions.map(([key, p]) => {
          const ok = p.roles.includes(role);
          return (
            <li key={key} style={{ display: "flex", justifyContent: "space-between", gap: 12, fontSize: 14 }}>
              <span className={ok ? "" : "muted"}>{p.label}</span>
              <span className={ok ? "badge badge-success" : "badge"}>{ok ? "Được phép" : "Không"}</span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

export function IntakeLinkCard() {
  return (
    <section className="card">
      <h2 className="card-title">Tiếp nhận ticket</h2>
      <p className="muted" style={{ margin: 0, fontSize: 14 }}>
        Tải PDF ticket của khách, AI trích xuất 8 trường; chỉ cần bạn xác nhận khi dữ liệu chưa chắc chắn (ADC-001).
      </p>
      <Link className="btn btn-primary" href="/intake" style={{ alignSelf: "flex-start" }}>
        Mở Tiếp nhận đơn
      </Link>
    </section>
  );
}

export function ScheduleLinkCard() {
  return (
    <section className="card">
      <h2 className="card-title">Kanban lệnh & lịch Line A / B</h2>
      <p className="muted" style={{ margin: 0, fontSize: 14 }}>
        Xếp lịch earliest feasible (hòa → Line A), theo dõi trạng thái lệnh và timeline 2 line (ADC-003).
      </p>
      <div className="row" style={{ gap: 8 }}>
        <Link className="btn btn-primary" href="/board">
          Mở Kanban
        </Link>
        <Link className="btn" href="/schedule">
          Xem lịch
        </Link>
      </div>
    </section>
  );
}

export function EscalationLinkCard() {
  return (
    <section className="card">
      <h2 className="card-title">Hàng đợi escalation</h2>
      <p className="muted" style={{ margin: 0, fontSize: 14 }}>
        Đơn có nguy cơ trả trễ: AI soạn nháp thông điệp cho khách, bạn sửa và duyệt trước khi gửi (ADC-005).
      </p>
      <Link className="btn btn-primary" href="/escalations" style={{ alignSelf: "flex-start" }}>
        Mở hàng đợi escalation
      </Link>
    </section>
  );
}

export function ComingSoonCard({ title, task, children }: { title: string; task: string; children: React.ReactNode }) {
  return (
    <section className="card">
      <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center" }}>
        <h2 className="card-title">{title}</h2>
        <span className="badge badge-warn">Chưa làm · {task}</span>
      </div>
      <p className="muted" style={{ margin: 0, fontSize: 14 }}>
        {children}
      </p>
    </section>
  );
}

/** "Thời lượng dự kiến: 3h00" + bảng breakdown từng thành phần (ADC-002 §UI). */
export function DurationBreakdown({ e }: { e: EstimateResult }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }} aria-live="polite">
      <div style={{ display: "flex", alignItems: "baseline", gap: 10, flexWrap: "wrap" }}>
        <span className="muted small">Thời lượng dự kiến</span>
        <span className="big-number">{formatDuration(e.duration_min)}</span>
        <span className="muted small">
          ({e.duration_min} phút · cấu hình v{e.config_version})
        </span>
      </div>
      <dl className="breakdown">
        {breakdownRows(e).map((r) => (
          <div key={r.key} style={{ display: "contents" }}>
            <dt>{r.label}</dt>
            <dd>{formatMinutes(r.minutes)}</dd>
          </div>
        ))}
      </dl>
      <span className="sim-label">Làm tròn lên bội số 15 phút · {SIM}</span>
    </div>
  );
}

/** POST /api/demo/reset — xóa ticket/lệnh, nạp lại seed. Bấm 2 lần để xác nhận (thao tác xóa dữ liệu). */
export function DemoResetCard() {
  const [armed, setArmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<DemoResetResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function reset() {
    if (!armed) return setArmed(true);
    setBusy(true);
    setError(null);
    try {
      setResult(await resetDemo());
    } catch (e) {
      setResult(null);
      setError(
        e instanceof ApiError && e.status === 404
          ? "Reset demo đang tắt ở môi trường này (chỉ bật ở demo/staging)."
          : e instanceof ApiError
            ? e.message
            : "Không gọi được API",
      );
    } finally {
      setBusy(false);
      setArmed(false);
    }
  }

  return (
    <section className="card" aria-labelledby="reset-title">
      <h2 className="card-title" id="reset-title">
        Dữ liệu demo
      </h2>
      <p className="card-sub">
        <code>POST /api/demo/reset</code> · xóa toàn bộ ticket và lệnh hiện có, nạp lại bộ lệnh mẫu cho hôm nay. Người
        dùng và nhật ký audit được giữ nguyên.
      </p>
      <div className="row">
        <button className={armed ? "btn btn-danger" : "btn"} onClick={reset} disabled={busy}>
          {busy ? "Đang reset…" : armed ? "Bấm lần nữa để xác nhận" : "Reset dữ liệu demo"}
        </button>
        {armed && !busy && (
          <button className="btn btn-ghost" onClick={() => setArmed(false)}>
            Hủy
          </button>
        )}
      </div>
      <div aria-live="polite">
        {error && (
          <div className="notice notice-error" role="alert">
            {error}
          </div>
        )}
        {result && (
          <div className="notice notice-success">
            Đã nạp {result.work_orders.length} lệnh mẫu và {result.incidents.length} sự cố cho ngày {result.demo_date}.
          </div>
        )}
      </div>
      {result && (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Mã seed</th>
                <th style={{ textAlign: "right" }}>Thời lượng</th>
              </tr>
            </thead>
            <tbody>
              {result.work_orders.map((w) => (
                <tr key={w.id}>
                  <td>
                    <Link href={`/intake/${w.id}`}>{w.ref}</Link>
                  </td>
                  <td className="mono" style={{ textAlign: "right" }}>
                    {formatDuration(w.estimated_duration_min)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
