"use client";

// Banner rủi ro đơn mới — ADC-005 §UI/UX (T-039): vàng = WARN, đỏ = BLOCK, kèm lý do và giờ trả sớm nhất khả thi.
// Mức rủi ro do luật deterministic ở backend tính (BR-07), không phải AI.
import { useEffect, useState } from "react";

import { ApiError, riskCheck, scheduleWorkOrder } from "@/lib/api";
import { formatVN } from "@/lib/intake";
import { blockedRisk, RISK_NOTICE, RISK_TITLE, type RiskCheck } from "@/lib/risk";

export function RiskBanner({
  risk,
  compact = false,
  children,
}: {
  risk: RiskCheck;
  compact?: boolean; // trên thẻ Kanban: chỉ lý do đầu
  children?: React.ReactNode; // nút hành động, vd "Yêu cầu duyệt nhận đơn"
}) {
  const reasons = compact ? risk.reasons.slice(0, 1) : risk.reasons;
  return (
    <div className={RISK_NOTICE[risk.level]} role={risk.level === "BLOCK" ? "alert" : "status"}>
      <div className="stack" style={{ gap: 6, minWidth: 0 }}>
        <strong>{RISK_TITLE[risk.level]}</strong>
        <ul className="plain-list small">
          {reasons.map((r) => (
            <li key={r}>{r}</li>
          ))}
        </ul>
        <span className="small">
          {risk.level === "BLOCK" ? "Giờ trả sớm nhất khả thi" : "Giờ xong dự kiến"}:{" "}
          <strong>{formatVN(risk.earliest_feasible_return)}</strong>
        </span>
        {risk.level === "BLOCK" && !compact && (
          <span className="small">Báo khách giờ trả mới, hoặc Quản lý vận hành override kèm lý do.</span>
        )}
        {children && (
          <div className="row" style={{ gap: 6, flexWrap: "wrap" }}>
            {children}
          </div>
        )}
      </div>
    </div>
  );
}

/** Rủi ro của 1 đơn vừa tạo (màn xác nhận lệnh): tự kiểm tra khi đơn chưa xếp / bị chặn. Điều phối gửi yêu cầu
 * duyệt nhận đơn (WARN) bằng cách xếp lịch — phương án vào hàng chờ duyệt, lịch đang chạy không đổi. */
export function NewOrderRisk({ workOrderId, canSchedule }: { workOrderId: string; canSchedule: boolean }) {
  const [risk, setRisk] = useState<RiskCheck | null>(null);
  const [message, setMessage] = useState<{ tone: "success" | "error"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    riskCheck(workOrderId)
      .then(setRisk)
      .catch(() => setMessage({ tone: "error", text: "Không kiểm tra được rủi ro giờ trả." }));
  }, [workOrderId]);

  async function requestApproval() {
    setBusy(true);
    try {
      const r = await scheduleWorkOrder(workOrderId);
      setRisk(r.risk);
      setMessage({ tone: "success", text: `Đã gửi yêu cầu duyệt nhận đơn — plan v${r.plan_version} chờ duyệt.` });
    } catch (e) {
      const blocked = e instanceof ApiError ? blockedRisk(e.detail) : null;
      if (blocked) setRisk(blocked);
      setMessage({ tone: "error", text: e instanceof ApiError ? e.message : "Không gửi được yêu cầu." });
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      {risk && (
        <RiskBanner risk={risk}>
          {risk.level === "WARN" && !message && canSchedule && (
            <button className="btn btn-sm btn-primary" disabled={busy} onClick={requestApproval}>
              Yêu cầu duyệt nhận đơn
            </button>
          )}
          {risk.level === "WARN" && !canSchedule && (
            <span className="small">Điều phối sản xuất gửi yêu cầu duyệt khi xếp lịch đơn này.</span>
          )}
        </RiskBanner>
      )}
      {message && <div className={`notice notice-${message.tone}`}>{message.text}</div>}
    </>
  );
}
