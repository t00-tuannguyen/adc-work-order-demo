"use client";

// Thẻ plan version chờ duyệt — ADC-006 §UI/UX (T-042), dùng ở trang Chờ duyệt và màn so sánh 2 version: nguồn, số đơn
// bị ảnh hưởng, thay đổi có nhãn loại, lịch trước → sau, lý do; Duyệt / Từ chối (bắt buộc lý do). Version đã xử lý →
// hiện người quyết định thay cho nút.
import Link from "next/link";
import { useState } from "react";

import { ApiError, approvePlanVersion, rejectPlanVersion } from "@/lib/api";
import {
  affectedCount,
  approvalLabels,
  CHANGE_LABEL,
  CHANGE_TONE,
  type PlanDiff,
  rejectReasonError,
  sourceLabel,
  spanText,
} from "@/lib/approval";
import { PLAN_STATUS_LABEL, PRIORITY_CLASS, STATE_LABEL } from "@/lib/board";
import { formatVN, PRIORITY_LABEL, shortId } from "@/lib/intake";
import { can, type Role } from "@/lib/roles";

export type Notice = { tone: "success" | "warn" | "error"; text: string };

export function PlanVersionCard({
  diff,
  role,
  onDecided,
  compareHref,
}: {
  diff: PlanDiff;
  role: Role;
  onDecided: (notice: Notice) => Promise<void>;
  /** Link sang màn so sánh 2 version; bỏ trống khi đang ở chính màn so sánh. */
  compareHref?: string;
}) {
  const [comment, setComment] = useState("");
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const v = diff.plan_version;
  const allowed = can(role, "APPROVE_PLAN_VERSION");
  const pending = v.status === "PENDING_APPROVAL";
  const labels = approvalLabels(diff.changes);

  async function act(action: () => Promise<Notice>) {
    setBusy(true);
    setError(null);
    try {
      await onDecided(await action());
    } catch (e) {
      // 409: version đã được người khác xử lý / bị thay / lịch đổi và trùng giờ → tải lại danh sách
      if (e instanceof ApiError && e.status === 409) await onDecided({ tone: "warn", text: e.message });
      else setError(e instanceof ApiError ? e.message : "Thao tác thất bại.");
    } finally {
      setBusy(false);
    }
  }

  const approve = () =>
    act(async () => {
      await approvePlanVersion(v.id, comment.trim());
      return { tone: "success", text: `Đã duyệt plan version ${v.id} — lịch mới đang áp dụng.` };
    });

  const reject = () => {
    const err = rejectReasonError(reason);
    if (err) return setError(err);
    return act(async () => {
      await rejectPlanVersion(v.id, reason.trim());
      return { tone: "success", text: `Đã từ chối plan version ${v.id} — đơn liên quan chuyển "Cần xếp lại".` };
    });
  };

  return (
    <section className="card span-all" aria-labelledby={`pv-${v.id}`}>
      <div className="row" style={{ justifyContent: "space-between", flexWrap: "wrap", gap: 8 }}>
        <h2 className="card-title" id={`pv-${v.id}`} style={{ margin: 0 }}>
          Plan version {v.id} · {sourceLabel(diff)}
        </h2>
        <div className="row" style={{ gap: 6, flexWrap: "wrap" }}>
          {labels.map((l) => (
            <span key={l} className="badge badge-warn">
              {l}
            </span>
          ))}
        </div>
      </div>
      <div className="small muted">
        {affectedCount(diff.changes)} đơn bị ảnh hưởng · đề xuất lúc {formatVN(v.created_at)}
        {compareHref && (
          <>
            {" · "}
            <Link href={compareHref}>so sánh lịch trước / sau</Link>
          </>
        )}
      </div>
      {diff.base_changed && (
        <div className="notice notice-warn">
          Lịch đang áp dụng đã đổi sau khi đề xuất (v{diff.base_version_id}) — duyệt sẽ gộp các thay đổi dưới đây vào
          lịch hiện tại; nếu trùng giờ hệ thống sẽ từ chối duyệt.
        </div>
      )}
      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>
              <th>Đơn</th>
              <th>Thay đổi</th>
              <th>Trước → sau</th>
              <th>Giờ trả</th>
              <th>Lý do</th>
            </tr>
          </thead>
          <tbody>
            {diff.changes.map((c) => (
              <tr key={c.work_order_id}>
                <td>
                  {c.product_name || "—"}{" "}
                  {c.priority && <span className={PRIORITY_CLASS[c.priority]}>{PRIORITY_LABEL[c.priority]}</span>}
                  <div className="mono small muted">
                    {shortId(c.work_order_id)} · {STATE_LABEL[c.state] ?? c.state}
                  </div>
                </td>
                <td>
                  <span className={CHANGE_TONE[c.change_type]}>{CHANGE_LABEL[c.change_type]}</span>
                </td>
                <td className="small">
                  <span className={c.old ? "diff-old" : "muted"}>{spanText(c.old)}</span>
                  <br />→ {spanText(c.new)}
                </td>
                <td className="small">
                  {formatVN(c.requested_return)}{" "}
                  {c.sla_ok ? (
                    <span className="badge badge-success">kịp</span>
                  ) : (
                    <span className="badge badge-danger">trễ</span>
                  )}
                </td>
                <td className="small">{c.reason ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {error && (
        <div className="notice notice-error" role="alert">
          {error}
        </div>
      )}
      {!pending ? (
        <div className={v.status === "REJECTED" ? "notice notice-error" : "notice notice-success"} role="status">
          {PLAN_STATUS_LABEL[v.status]}
          {diff.decided_by_name && ` · ${diff.decided_by_name}`}
          {diff.decided_at && ` · ${formatVN(diff.decided_at)}`}
          {diff.comment && ` · ${diff.comment}`}
        </div>
      ) : allowed ? (
        rejecting ? (
          <div className="stack" style={{ gap: 8 }}>
            <div className="field">
              <label htmlFor={`reason-${v.id}`}>Lý do từ chối (bắt buộc)</label>
              <textarea
                id={`reason-${v.id}`}
                className="textarea"
                rows={2}
                maxLength={500}
                value={reason}
                autoFocus
                onChange={(e) => setReason(e.target.value)}
              />
            </div>
            <div className="row" style={{ gap: 8, justifyContent: "flex-end" }}>
              <button className="btn" disabled={busy} onClick={() => setRejecting(false)}>
                Hủy
              </button>
              <button className="btn btn-danger" disabled={busy || !reason.trim()} onClick={reject}>
                Từ chối version
              </button>
            </div>
          </div>
        ) : (
          <div className="stack" style={{ gap: 8 }}>
            <div className="field">
              <label htmlFor={`comment-${v.id}`}>Ghi chú khi duyệt (tùy chọn)</label>
              <input
                id={`comment-${v.id}`}
                className="input"
                maxLength={500}
                value={comment}
                placeholder="vd: đã báo khách giờ trả mới"
                onChange={(e) => setComment(e.target.value)}
              />
            </div>
            <div className="row" style={{ gap: 8, justifyContent: "flex-end" }}>
              <button className="btn" disabled={busy} onClick={() => setRejecting(true)}>
                Từ chối…
              </button>
              <button className="btn btn-primary" disabled={busy} onClick={approve}>
                Duyệt cả version
              </button>
            </div>
          </div>
        )
      ) : (
        <p className="small muted">Chỉ Kinh doanh / Quản lý vận hành duyệt hoặc từ chối plan version.</p>
      )}
    </section>
  );
}
