"use client";

// So sánh 2 plan version — ADC-006 §UI/UX (T-042): "diff lịch trước / sau" cho người duyệt. 2 timeline cùng trục giờ:
// lịch nền (ACTIVE hiện tại khi còn chờ duyệt, version cha khi đã xử lý) ↔ version đề xuất; đơn thay đổi làm nổi, khung
// dừng sự cố tô xám. Bên dưới là thẻ thay đổi + Duyệt / Từ chối dùng chung với trang Chờ duyệt.
import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { FlagIcon, LineTimeline } from "@/components/LineTimeline";
import { type Notice, PlanVersionCard } from "@/components/PlanVersionCard";
import { ApiError, getPlanDiff, getSchedule, listIncidents } from "@/lib/api";
import { compareVersions, diffDays, type PlanDiff, sourceLabel } from "@/lib/approval";
import { PLAN_STATUS_LABEL, type ScheduleView } from "@/lib/board";
import { downtimesOf, type Incident } from "@/lib/incident";
import type { Role } from "@/lib/roles";

const ALL: Role[] = ["SALES", "PLANNER", "OPS_MANAGER", "ADMIN"];

function ComparePanel({ id, role }: { id: number; role: Role }) {
  const [diff, setDiff] = useState<PlanDiff | null>(null);
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [day, setDay] = useState<string | null>(null);
  const [views, setViews] = useState<{ day: string; before: ScheduleView; after: ScheduleView } | null>(null);
  const [notice, setNotice] = useState<Notice | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(
    () =>
      Promise.all([getPlanDiff(id), listIncidents()])
        .then(([d, list]) => {
          setDiff(d);
          setIncidents(list);
          const own = list.find((i) => i.incident_id === d.incident_id);
          setDay((cur) => cur ?? diffDays(d.changes, own ? [own.start_at] : [])[0] ?? null);
        })
        .catch((e) => setError(e instanceof ApiError ? e.message : "Không tải được plan version.")),
    [id],
  );

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (!diff || !day) return;
    const { before, after } = compareVersions(diff);
    Promise.all([getSchedule(before, day), getSchedule(after, day)])
      .then(([b, a]) => setViews({ day, before: b, after: a }))
      .catch((e) => setError(e instanceof ApiError ? e.message : "Không tải được lịch."));
  }, [diff, day]);

  const changed = useMemo(() => new Set(diff?.changes.map((c) => c.work_order_id)), [diff]);
  const downtimes = useMemo(() => downtimesOf(incidents), [incidents]);

  async function decided(n: Notice) {
    setNotice(n);
    await load();
  }

  if (error)
    return (
      <div className="notice notice-error span-all" role="alert">
        {error}
      </div>
    );
  if (!diff) return <p className="muted span-all">Đang tải…</p>;

  const v = diff.plan_version;
  const own = incidents.find((i) => i.incident_id === diff.incident_id);
  const days = diffDays(diff.changes, own ? [own.start_at] : []);
  const pending = v.status === "PENDING_APPROVAL";
  return (
    <>
      {notice && (
        <div className={`notice notice-${notice.tone} span-all`} role="status">
          {notice.text}
        </div>
      )}
      <section className="card span-all" aria-labelledby="compare-title">
        <div className="row" style={{ justifyContent: "space-between", flexWrap: "wrap", gap: 8 }}>
          <h2 className="card-title" id="compare-title" style={{ margin: 0 }}>
            v{diff.base_version_id ?? "—"} → v{v.id} · {sourceLabel(diff)}
          </h2>
          <span className={pending ? "badge badge-warn" : "badge"}>{PLAN_STATUS_LABEL[v.status]}</span>
        </div>
        <div className="row" style={{ gap: 8, flexWrap: "wrap", alignItems: "center" }}>
          <span className="small muted">Ngày xem:</span>
          {days.map((d) => (
            <button
              key={d}
              className={d === day ? "btn btn-sm btn-primary" : "btn btn-sm"}
              aria-pressed={d === day}
              onClick={() => setDay(d)}
            >
              {d.slice(8, 10)}/{d.slice(5, 7)}
            </button>
          ))}
          <span style={{ flex: 1 }} />
          <Link className="btn btn-sm btn-ghost" href="/approvals">
            Danh sách chờ duyệt
          </Link>
          {diff.incident_id && (
            <Link className="btn btn-sm" href={`/incidents/${diff.incident_id}`}>
              Chi tiết sự cố
            </Link>
          )}
          {day && (
            <Link className="btn btn-sm" href={`/schedule?${new URLSearchParams({ date: day, version: String(v.id) })}`}>
              Mở trên lịch
            </Link>
          )}
        </div>
        <div className="row small" style={{ gap: 12, flexWrap: "wrap" }}>
          <span className="legend prio-block-vip">VIP</span>
          <span className="legend prio-block-urgent">Khẩn</span>
          <span className="legend prio-block-normal">Thường</span>
          {downtimes.length > 0 && <span className="legend timeline-downtime">Khung dừng</span>}
          <span className="legend legend-flag">
            <FlagIcon /> Giờ trả
          </span>
          <span className="legend timeline-late">Trễ giờ trả</span>
          <span className="muted">Đơn không thay đổi hiện mờ.</span>
        </div>
      </section>

      {views && (
        <>
          <section className="card span-all timeline-card" aria-labelledby="before-title">
            <h2 className="card-title" id="before-title">
              Trước · {views.before.plan_version ? `v${views.before.plan_version.id}` : "chưa có lịch"} (
              {pending ? "lịch đang áp dụng" : "lịch nền của phương án"})
            </h2>
            <LineTimeline
              view={views.before}
              day={views.day}
              downtimes={downtimes}
              highlight={changed}
              caption={`Lịch trước ngày ${views.day}`}
            />
          </section>
          <section className="card span-all timeline-card" aria-labelledby="after-title">
            <h2 className="card-title" id="after-title">
              Sau · v{v.id} ({PLAN_STATUS_LABEL[v.status]})
            </h2>
            <LineTimeline
              view={views.after}
              day={views.day}
              downtimes={downtimes}
              highlight={changed}
              caption={`Phương án v${v.id} ngày ${views.day}`}
            />
          </section>
        </>
      )}

      <PlanVersionCard diff={diff} role={role} onDecided={decided} />
    </>
  );
}

export default function PlanComparePage() {
  const { id } = useParams<{ id: string }>();
  return (
    <AppShell
      allow={ALL}
      crumb="Kiểm soát / Chờ duyệt / So sánh"
      title="So sánh lịch trước / sau"
      subtitle="Lịch đang áp dụng và phương án đề xuất trên cùng trục giờ — duyệt hoặc từ chối cả version."
    >
      {(me) => <ComparePanel id={Number(id)} role={me.role!} />}
    </AppShell>
  );
}
