"use client";

// Sự cố line — ADC-004 (T-035): danh sách sự cố, mới nhất trước; Điều phối khai báo ngay tại đây rồi sang màn
// so sánh trước / sau. Mọi vai trò xem được (người duyệt cần xem phương án trước khi duyệt).
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { IncidentCard } from "@/components/IncidentForm";
import { ApiError, listIncidents } from "@/lib/api";
import { PLAN_STATUS_LABEL } from "@/lib/board";
import { formatDuration } from "@/lib/estimate";
import { type Incident, INCIDENT_STATUS_LABEL } from "@/lib/incident";
import { formatVN } from "@/lib/intake";
import { can, type Role } from "@/lib/roles";

const ALL: Role[] = ["SALES", "PLANNER", "OPS_MANAGER", "ADMIN"];

function IncidentList() {
  const [items, setItems] = useState<Incident[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listIncidents()
      .then(setItems)
      .catch((e) => setError(e instanceof ApiError ? e.message : "Không tải được danh sách sự cố."));
  }, []);

  return (
    <section className="card span-all" aria-labelledby="incident-list-title">
      <h2 className="card-title" id="incident-list-title">
        Sự cố đã khai báo
      </h2>
      {error && (
        <div className="notice notice-error" role="alert">
          {error}
        </div>
      )}
      {items && items.length === 0 && <p className="muted small">Chưa có sự cố nào.</p>}
      {items && items.length > 0 && (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Sự cố</th>
                <th>Khung dừng</th>
                <th>Trạng thái</th>
                <th style={{ textAlign: "right" }}>Đơn bị ảnh hưởng</th>
                <th>Phương án</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {items.map((inc) => (
                <tr key={inc.incident_id}>
                  <td>
                    <strong>#{inc.incident_id}</strong> · Line {inc.line}
                    {inc.note && <div className="small muted">{inc.note}</div>}
                  </td>
                  <td>
                    {formatVN(inc.start_at)} → {formatVN(inc.end_at)}
                    <div className="small muted">{formatDuration(inc.est_downtime_min)} dự kiến</div>
                  </td>
                  <td>
                    <span className={inc.status === "OPEN" ? "badge badge-danger" : "badge badge-success"}>
                      {INCIDENT_STATUS_LABEL[inc.status]}
                    </span>
                  </td>
                  <td style={{ textAlign: "right" }}>
                    {inc.affected_orders.length}
                    {inc.sla_risks.length > 0 && (
                      <span className="badge badge-danger" style={{ marginLeft: 6 }}>
                        {inc.sla_risks.length} trễ
                      </span>
                    )}
                  </td>
                  <td>
                    {inc.proposed_plan_version
                      ? `v${inc.proposed_plan_version.id} · ${PLAN_STATUS_LABEL[inc.proposed_plan_version.status]}`
                      : "—"}
                  </td>
                  <td>
                    <Link className="btn btn-sm" href={`/incidents/${inc.incident_id}`}>
                      Trước / sau
                    </Link>
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

export default function IncidentsPage() {
  const router = useRouter();
  return (
    <AppShell
      allow={ALL}
      crumb="Vận hành / Sự cố line"
      title="Sự cố line"
      subtitle="Khai báo line dừng, xem đơn bị ảnh hưởng và phương án phục hồi trước / sau. Phương án luôn chờ duyệt."
    >
      {(me) => (
        <>
          {can(me.role, "DECLARE_INCIDENT") && (
            <IncidentCard onDeclared={(inc) => router.push(`/incidents/${inc.incident_id}`)} />
          )}
          <IncidentList />
        </>
      )}
    </AppShell>
  );
}
