"use client";

// Xếp / sửa lịch thủ công — BR-15: Điều phối chọn line + giờ bắt đầu; xem trước giờ xong, kịp / trễ giờ trả.
// Backend kiểm tra lại trùng slot (409), giờ đã qua / trước giờ hàng đến / sai ca (422); trễ → chờ duyệt.
import { useState } from "react";

import { ApiError, scheduleManually } from "@/lib/api";
import { hhmm, type Line, type ManualScheduleResult, manualPreview } from "@/lib/board";
import { formatDuration } from "@/lib/estimate";
import { formatVN, fromLocalInput, toLocalInput } from "@/lib/intake";

const STEP_MS = 15 * 60_000;

/** Giờ gợi ý: max(giờ hàng đến, bây giờ), làm tròn lên 15 phút. */
function suggestedStart(expectedArrival: string | null): string {
  const arrival = expectedArrival ? Date.parse(expectedArrival) : 0;
  const t = Math.max(Number.isNaN(arrival) ? 0 : arrival, Date.now());
  return new Date(Math.ceil(t / STEP_MS) * STEP_MS).toISOString();
}

export function ManualScheduleForm({
  workOrderId,
  durationMin,
  requestedReturn,
  expectedArrival,
  initialLine = "A",
  initialStart,
  onDone,
  onCancel,
}: {
  workOrderId: string;
  durationMin: number;
  requestedReturn: string | null;
  expectedArrival: string | null;
  initialLine?: Line;
  initialStart?: string;
  onDone: (r: ManualScheduleResult) => void;
  onCancel: () => void;
}) {
  const [line, setLine] = useState<Line>(initialLine);
  const [start, setStart] = useState(() => toLocalInput(initialStart ?? suggestedStart(expectedArrival)));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const startIso = fromLocalInput(start);
  const preview = manualPreview(startIso, durationMin, requestedReturn);

  async function save() {
    if (!startIso) return;
    setBusy(true);
    setError(null);
    try {
      onDone(await scheduleManually(workOrderId, line, startIso));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Không lưu được lịch.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="stack" style={{ gap: 8 }}>
      <div className="row" style={{ gap: 8, flexWrap: "wrap", alignItems: "flex-end" }}>
        <label className="field">
          Line
          <select className="select" value={line} onChange={(e) => setLine(e.target.value as Line)} disabled={busy}>
            <option value="A">Line A</option>
            <option value="B">Line B</option>
          </select>
        </label>
        <label className="field">
          Bắt đầu
          <input
            className="input"
            type="datetime-local"
            step={900}
            value={start}
            onChange={(e) => setStart(e.target.value)}
            disabled={busy}
          />
        </label>
      </div>
      <p className="small" style={{ margin: 0 }}>
        Thời lượng {formatDuration(durationMin)}
        {preview && (
          <>
            {" "}
            · xong {hhmm(preview.end)} ({formatVN(preview.end)}) ·{" "}
            {preview.slaOk ? (
              <span className="badge badge-success">Kịp giờ trả</span>
            ) : (
              <span className="badge badge-danger" style={{ whiteSpace: "normal" }}>
                Trễ {formatDuration(preview.lateMin)} — cần duyệt đổi giờ trả
              </span>
            )}
          </>
        )}
      </p>
      {error && (
        <div className="notice notice-error" role="alert">
          {error}
        </div>
      )}
      <div className="row" style={{ gap: 6 }}>
        <button className="btn btn-sm btn-primary" onClick={save} disabled={busy || !startIso}>
          {busy ? "Đang lưu…" : preview && !preview.slaOk ? "Gửi duyệt" : "Lưu lịch"}
        </button>
        <button className="btn btn-sm btn-ghost" onClick={onCancel} disabled={busy}>
          Hủy
        </button>
      </div>
    </div>
  );
}
