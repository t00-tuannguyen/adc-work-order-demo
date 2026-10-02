"use client";

// So sánh trước / sau sự cố — ADC-004 (T-035): 2 timeline (lịch đang áp dụng lúc khai báo ↔ phương án đề xuất) cùng
// trục giờ, khung dừng tô xám gạch chéo, đơn bị ảnh hưởng làm nổi; bảng số liệu là nguồn chính, đoạn giải thích của
// Scheduler Agent (T-034) đặt cạnh. Phương án sự cố luôn tự gửi duyệt khi tạo (T-033) — duyệt ở T-042.
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { FlagIcon, LineTimeline } from "@/components/LineTimeline";
import { ApiError, explainIncident, getIncident, getSchedule, listIncidents } from "@/lib/api";
import { PLAN_STATUS_LABEL, PRIORITY_CLASS, type ScheduleView, STATE_LABEL } from "@/lib/board";
import { formatDuration } from "@/lib/estimate";
import {
  compareVersions,
  downtimesOf,
  type ExplanationResult,
  finishShiftMin,
  type Incident,
  incidentDays,
  INCIDENT_STATUS_LABEL,
  OUTCOME_LABEL,
  proposalHref,
  spanText,
  timeText,
  windowText,
} from "@/lib/incident";
import { formatVN, PRIORITY_LABEL, shortId } from "@/lib/intake";
import type { Role } from "@/lib/roles";

const ALL: Role[] = ["SALES", "PLANNER", "OPS_MANAGER", "ADMIN"];

function PlanStatus({ inc }: { inc: Incident }) {
  const pv = inc.proposed_plan_version;
  if (!pv) return <div className="notice notice-success">Không có đơn nào bị ảnh hưởng — không cần phương án mới.</div>;
  if (pv.status === "PENDING_APPROVAL")
    return (
      <div className="notice notice-warn" role="status">
        <strong>Đã gửi duyệt</strong> · phương án v{pv.id} chờ Kinh doanh / Quản lý vận hành duyệt. Lịch đang áp dụng
        giữ nguyên tới khi duyệt.
      </div>
    );
  if (pv.status === "SUPERSEDED")
    return (
      <div className="notice notice-warn" role="status">
        Phương án v{pv.id} đã được thay bằng phương án mới hơn (sự cố khác hoặc tính lại khi hồi phục) — xem ở danh
        sách sự cố.
      </div>
    );
  return (
    <div className={pv.status === "ACTIVE" ? "notice notice-success" : "notice notice-error"} role="status">
      Phương án v{pv.id} · {PLAN_STATUS_LABEL[pv.status]}.
    </div>
  );
}

function AffectedTable({ inc }: { inc: Incident }) {
  const pulled = inc.affected_orders.filter((a) => a.outcome === "PULLED_FORWARD").length;
  return (
    <section className="card span-all" aria-labelledby="affected-title">
      <h2 className="card-title" id="affected-title">
        Đơn thay đổi trong phương án ({inc.affected_orders.length})
      </h2>
      <p className="card-sub">
        {inc.affected_orders.length - pulled} đơn bị ảnh hưởng, xử lý theo VIP → Khẩn → Thường rồi giờ trả sớm hơn
        {pulled > 0 && ` · ${pulled} đơn khác được kéo sớm để line không nghỉ`}. Giờ Việt Nam.
      </p>
      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>
              <th>Lệnh</th>
              <th>Ưu tiên</th>
              <th>Line cũ → mới</th>
              <th>Giờ chạy cũ → mới</th>
              <th>Giờ xong</th>
              <th>Giờ trả</th>
              <th>SLA</th>
              <th>Kết quả</th>
            </tr>
          </thead>
          <tbody>
            {inc.affected_orders.map((a) => {
              const shift = finishShiftMin(a);
              return (
                <tr key={a.work_order_id}>
                  <td>
                    <span className="mono">{shortId(a.work_order_id)}</span>
                    <div className="small">{a.product_name ?? "—"}</div>
                    <div className="small muted">{STATE_LABEL[a.state] ?? a.state}</div>
                  </td>
                  <td>{a.priority ? <span className={PRIORITY_CLASS[a.priority]}>{PRIORITY_LABEL[a.priority]}</span> : "—"}</td>
                  <td className="mono">
                    {a.old.line} → {a.new.line}
                  </td>
                  <td className="mono small">
                    {spanText(a.old.start, a.old.end, inc.start_at)}
                    <br />→ {spanText(a.new.start, a.new.end, inc.start_at)}
                  </td>
                  <td className="small">
                    {timeText(a.old.end, inc.start_at)} → {timeText(a.new.end, inc.start_at)}
                    <div className={shift > 0 ? "small" : "small muted"}>
                      {shift === 0 ? "không đổi" : shift > 0 ? `muộn ${formatDuration(shift)}` : `sớm ${formatDuration(-shift)}`}
                    </div>
                  </td>
                  <td className="small">{formatVN(a.requested_return)}</td>
                  <td>
                    {a.sla_ok ? (
                      <span className="badge badge-success">Kịp</span>
                    ) : (
                      <span className="badge badge-danger">Trễ · SLA_RISK</span>
                    )}
                  </td>
                  <td className="small">
                    {OUTCOME_LABEL[a.outcome]}
                    {a.change_type === "PRIORITY_OVERRIDE" && <div className="muted">Nhường đơn ưu tiên cao hơn</div>}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function ExplanationCard({ inc }: { inc: Incident }) {
  const [result, setResult] = useState<ExplanationResult | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    explainIncident(inc.incident_id)
      .then(setResult)
      .catch(() => setFailed(true));
  }, [inc.incident_id]);

  const text = result?.explanation ?? inc.explanation;
  return (
    <section className="card span-all" aria-labelledby="explain-title" aria-busy={!result && !failed}>
      <div className="row" style={{ justifyContent: "space-between", flexWrap: "wrap", gap: 8 }}>
        <h2 className="card-title" id="explain-title">
          Giải thích phương án
        </h2>
        {result?.source === "LLM" ? (
          <span className="badge badge-primary">Scheduler Agent (AI) · đã đối chiếu số liệu</span>
        ) : result || failed ? (
          <span className="badge">Bản tự động theo luật</span>
        ) : (
          <span className="badge">Scheduler Agent đang viết…</span>
        )}
      </div>
      <p style={{ margin: 0, whiteSpace: "pre-line", fontSize: 14 }}>{text}</p>
      <p className="small muted" style={{ margin: 0 }}>
        Thứ tự, line và giờ do thuật toán xếp lịch tính; AI chỉ diễn giải. Bảng số liệu ở trên là nguồn chính.
      </p>
    </section>
  );
}

function ComparePanel({ id }: { id: number }) {
  const [inc, setInc] = useState<Incident | null>(null);
  const [all, setAll] = useState<Incident[]>([]);
  const [day, setDay] = useState<string | null>(null);
  const [views, setViews] = useState<{ day: string; before: ScheduleView; after: ScheduleView | null } | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([getIncident(id), listIncidents()])
      .then(([one, list]) => {
        setInc(one);
        setAll(list);
        setDay(incidentDays(one)[0]);
      })
      .catch((e) => setError(e instanceof ApiError ? e.message : "Không tải được sự cố."));
  }, [id]);

  useEffect(() => {
    if (!inc || !day) return;
    const { before, after } = compareVersions(inc);
    Promise.all([getSchedule(before, day), after ? getSchedule(after, day) : Promise.resolve(null)])
      .then(([b, a]) => setViews({ day, before: b, after: a }))
      .catch((e) => setError(e instanceof ApiError ? e.message : "Không tải được lịch."));
  }, [inc, day]);

  const affected = useMemo(() => new Set(inc?.affected_orders.map((a) => a.work_order_id)), [inc]);
  const downtimes = useMemo(() => downtimesOf(all.length ? all : inc ? [inc] : []), [all, inc]);

  if (error)
    return (
      <div className="notice notice-error span-all" role="alert">
        {error}
      </div>
    );
  if (!inc || !day) return <p className="muted span-all">Đang tải…</p>;

  const pv = inc.proposed_plan_version;
  const days = incidentDays(inc);
  const scheduleLink = proposalHref(inc);
  return (
    <>
      <section className="card span-all" aria-labelledby="incident-title">
        <div className="row" style={{ justifyContent: "space-between", flexWrap: "wrap", gap: 8 }}>
          <h2 className="card-title" id="incident-title">
            Sự cố #{inc.incident_id} · {windowText(inc)} {formatVN(inc.start_at).slice(6)}
          </h2>
          <span className={inc.status === "OPEN" ? "badge badge-danger" : "badge badge-success"}>
            {INCIDENT_STATUS_LABEL[inc.status]}
          </span>
        </div>
        <p className="card-sub" style={{ margin: 0 }}>
          {formatVN(inc.start_at)} → {formatVN(inc.end_at)} · dừng {formatDuration(inc.est_downtime_min)} dự kiến
          {inc.actual_end_at && ` · hồi phục thực tế ${formatVN(inc.actual_end_at)}`}
          {inc.note && ` · ${inc.note}`}
        </p>
        <PlanStatus inc={inc} />
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
          <Link className="btn btn-sm btn-ghost" href="/incidents">
            Danh sách sự cố
          </Link>
          {scheduleLink && (
            <Link className="btn btn-sm" href={scheduleLink}>
              Mở trên lịch
            </Link>
          )}
        </div>
        <div className="row small" style={{ gap: 12, flexWrap: "wrap" }}>
          <span className="legend prio-block-vip">VIP</span>
          <span className="legend prio-block-urgent">Khẩn</span>
          <span className="legend prio-block-normal">Thường</span>
          <span className="legend timeline-downtime">Khung dừng</span>
          <span className="legend legend-flag">
            <FlagIcon /> Giờ trả
          </span>
          <span className="legend timeline-late">Trễ giờ trả</span>
          <span className="muted">Đơn không bị ảnh hưởng hiện mờ.</span>
        </div>
      </section>

      {views && (
        <>
          <section className="card span-all timeline-card" aria-labelledby="before-title">
            <h2 className="card-title" id="before-title">
              Trước · {views.before.plan_version ? `v${views.before.plan_version.id}` : "chưa có lịch"} (lịch đang áp dụng
              lúc khai báo)
            </h2>
            <LineTimeline
              view={views.before}
              day={views.day}
              downtimes={downtimes}
              highlight={affected}
              caption={`Lịch trước sự cố ngày ${views.day}`}
            />
          </section>
          {views.after && pv && (
            <section className="card span-all timeline-card" aria-labelledby="after-title">
              <h2 className="card-title" id="after-title">
                Sau · v{pv.id} ({PLAN_STATUS_LABEL[pv.status]})
              </h2>
              <LineTimeline
                view={views.after}
                day={views.day}
                downtimes={downtimes}
                highlight={affected}
                caption={`Phương án sau sự cố ngày ${views.day}`}
              />
            </section>
          )}
        </>
      )}

      {inc.affected_orders.length > 0 && <AffectedTable inc={inc} />}
      <ExplanationCard inc={inc} />
    </>
  );
}

export default function IncidentComparePage() {
  const { id } = useParams<{ id: string }>();
  return (
    <AppShell
      allow={ALL}
      crumb="Vận hành / Sự cố line / So sánh trước – sau"
      title="So sánh trước / sau sự cố"
      subtitle="Lịch đang áp dụng và phương án phục hồi trên cùng trục giờ. Khung dừng tô xám gạch chéo."
    >
      {() => <ComparePanel id={Number(id)} />}
    </AppShell>
  );
}
