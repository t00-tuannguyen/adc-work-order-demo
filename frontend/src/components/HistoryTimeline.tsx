"use client";

// Lịch sử trạng thái lệnh — ADC-006 §UI/UX (T-041): ai, khi nào, vì sao; mọi vai trò xem được.
import { useEffect, useState } from "react";

import { getWorkOrderHistory } from "@/lib/api";
import { ACTOR_LABEL, type HistoryEntry } from "@/lib/approval";
import { STATE_LABEL } from "@/lib/board";
import { formatVN } from "@/lib/intake";

export function HistoryTimeline({ workOrderId }: { workOrderId: string }) {
  const [items, setItems] = useState<HistoryEntry[] | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    getWorkOrderHistory(workOrderId)
      .then(setItems)
      .catch(() => setError(true));
  }, [workOrderId]);

  if (error) return <p className="small muted">Không tải được lịch sử trạng thái.</p>;
  if (!items) return <p className="small muted">Đang tải lịch sử…</p>;
  if (!items.length) return <p className="small muted">Chưa có lịch sử.</p>;
  return (
    <ol className="history">
      {items.map((h) => (
        <li key={h.id}>
          <div className="row" style={{ gap: 6, flexWrap: "wrap" }}>
            <strong>{STATE_LABEL[h.to_state] ?? h.to_state}</strong>
            {h.from_state && <span className="small muted">từ {STATE_LABEL[h.from_state] ?? h.from_state}</span>}
            {h.plan_version_id && <span className="badge">v{h.plan_version_id}</span>}
          </div>
          <div className="small muted">
            {formatVN(h.at)} · {h.actor_name}
            {h.actor_type !== "USER" && ` (${ACTOR_LABEL[h.actor_type]})`}
          </div>
          {h.reason && <div className="small">{h.reason}</div>}
        </li>
      ))}
    </ol>
  );
}
