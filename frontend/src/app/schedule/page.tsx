"use client";

// Lịch Line A / B dạng timeline — ADC-003 (T-030): 2 hàng theo giờ (giờ Việt Nam), khối màu theo ưu tiên,
// vạch đỏ tại giờ trả, bấm khối xem chi tiết + lý do xếp; chọn plan version để xem lịch cũ / đề xuất chờ duyệt.
// Dựng bằng CSS (không thêm thư viện timeline — ADR-0002). BR-15: Điều phối sửa lịch tay từ chi tiết khối.
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { FlagIcon, LineTimeline } from "@/components/LineTimeline";
import { ManualScheduleForm } from "@/components/ManualScheduleForm";
import { ApiError, getSchedule, listPlanVersions } from "@/lib/api";
import {
  hhmm,
  MANUAL_STATES,
  type ManualScheduleResult,
  PLAN_STATUS_LABEL,
  type PlanVersion,
  type ScheduleSlot,
  type ScheduleView,
  shiftDay,
  STATE_LABEL,
  todayVN,
} from "@/lib/board";
import { formatVN, PRIORITY_LABEL, shortId } from "@/lib/intake";
import { can, type Role } from "@/lib/roles";

const ALL: Role[] = ["SALES", "PLANNER", "OPS_MANAGER", "ADMIN"];

function Detail({
  slot,
  editable,
  onClose,
  onEdited,
}: {
  slot: ScheduleSlot;
  editable: boolean;
  onClose: () => void;
  onEdited: (r: ManualScheduleResult) => void;
}) {
  const [editing, setEditing] = useState(false);
  const durationMin = Math.round((Date.parse(slot.end) - Date.parse(slot.start)) / 60_000);
  return (
    <section className="card span-all" aria-labelledby="slot-title">
      <div className="row" style={{ justifyContent: "space-between" }}>
        <h2 className="card-title" id="slot-title">
          {shortId(slot.work_order_id)} · {slot.product_name || "—"}
        </h2>
        <button className="btn btn-sm btn-ghost" onClick={onClose} aria-label="Đóng chi tiết">
          Đóng
        </button>
      </div>
      <dl className="kv">
        <dt>Line</dt>
        <dd>
          Line {slot.line} · {hhmm(slot.start)}–{hhmm(slot.end)} ({formatVN(slot.start)} → {formatVN(slot.end)})
        </dd>
        <dt>Ưu tiên</dt>
        <dd>{slot.priority ? PRIORITY_LABEL[slot.priority] : "—"}</dd>
        <dt>Giờ trả yêu cầu</dt>
        <dd>
          {formatVN(slot.requested_return)}{" "}
          {slot.sla_ok ? (
            <span className="badge badge-success">Kịp giờ trả</span>
          ) : (
            <span className="badge badge-danger">Trễ giờ trả</span>
          )}
        </dd>
        <dt>Trạng thái</dt>
        <dd>{STATE_LABEL[slot.state] ?? slot.state}</dd>
        <dt>Lý do xếp</dt>
        <dd>{slot.reason ?? "—"}</dd>
      </dl>
      <p className="small muted" style={{ margin: 0 }}>
        Lý do sinh từ luật xếp lịch (earliest feasible, hòa → Line A) hoặc do Điều phối xếp tay, không do AI tự đặt giờ.
      </p>
      {editable &&
        (editing ? (
          <ManualScheduleForm
            workOrderId={slot.work_order_id}
            durationMin={durationMin}
            requestedReturn={slot.requested_return}
            expectedArrival={null}
            initialLine={slot.line}
            initialStart={slot.start}
            onDone={(r) => {
              setEditing(false);
              onEdited(r);
            }}
            onCancel={() => setEditing(false)}
          />
        ) : (
          <button className="btn btn-sm" onClick={() => setEditing(true)} style={{ alignSelf: "flex-start" }}>
            Sửa lịch
          </button>
        ))}
    </section>
  );
}

function SchedulePanel({ role }: { role: Role }) {
  // Từ thẻ Kanban: ?date=YYYY-MM-DD&wo=<id>[&version=<n>] → mở đúng ngày, mở sẵn khối của lệnh
  const params = useSearchParams();
  const focusWo = useRef(params.get("wo"));
  const [day, setDay] = useState(() => params.get("date") || todayVN());
  const [version, setVersion] = useState(() => params.get("version") || "current");
  const [versions, setVersions] = useState<PlanVersion[]>([]);
  const [view, setView] = useState<ScheduleView | null>(null);
  const [picked, setPicked] = useState<ScheduleSlot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<{ tone: "success" | "warn"; text: string } | null>(null);
  const [reload, setReload] = useState(0);

  useEffect(() => {
    listPlanVersions()
      .then(setVersions)
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    getSchedule(version, day)
      .then((v) => {
        setView(v);
        setError(null);
        const id = focusWo.current;
        const hit = id ? [...v.lines.A, ...v.lines.B].find((s) => s.work_order_id === id) : undefined;
        if (hit) {
          focusWo.current = null;
          setPicked(hit);
          requestAnimationFrame(() =>
            document.getElementById(`slot-${id}`)?.scrollIntoView({ behavior: "smooth", block: "center", inline: "center" }),
          );
        }
      })
      .catch((e) => setError(e instanceof ApiError ? e.message : "Không tải được lịch."));
  }, [version, day, reload]);

  function edited(r: ManualScheduleResult) {
    const pending = r.plan_status !== "ACTIVE";
    setNotice({
      tone: pending ? "warn" : "success",
      text: `${r.reason} (plan v${r.plan_version}${pending ? " — chờ duyệt, lịch hiện tại giữ nguyên" : ""})`,
    });
    setPicked(null);
    setReload((n) => n + 1);
    listPlanVersions()
      .then(setVersions)
      .catch(() => undefined);
  }

  const pv = view?.plan_version;
  const count = view ? view.lines.A.length + view.lines.B.length : 0;

  return (
    <>
      <section className="card span-all">
        <div className="row" style={{ flexWrap: "wrap", gap: 12, alignItems: "flex-end" }}>
          <label className="field" style={{ minWidth: 220 }}>
            Plan version
            <select
              className="select"
              value={version}
              onChange={(e) => {
                setVersion(e.target.value);
                setPicked(null);
              }}
            >
              <option value="current">Đang áp dụng (ACTIVE)</option>
              {versions.map((v) => (
                <option key={v.id} value={String(v.id)}>
                  v{v.id} · {PLAN_STATUS_LABEL[v.status]} · {v.slot_count} slot
                </option>
              ))}
            </select>
          </label>
          <div className="row" style={{ gap: 6, alignItems: "flex-end" }}>
            <button className="btn btn-sm" onClick={() => setDay((d) => shiftDay(d, -1))} aria-label="Ngày trước">
              ←
            </button>
            <label className="field">
              Ngày
              <input className="input" type="date" value={day} onChange={(e) => e.target.value && setDay(e.target.value)} />
            </label>
            <button className="btn btn-sm" onClick={() => setDay((d) => shiftDay(d, 1))} aria-label="Ngày sau">
              →
            </button>
            <button className="btn btn-sm" onClick={() => setDay(todayVN())}>
              Hôm nay
            </button>
          </div>
          <Link className="btn btn-sm" href="/board" style={{ marginLeft: "auto" }}>
            Kanban lệnh
          </Link>
        </div>
        <p className="small muted" style={{ margin: "12px 0 0" }}>
          {pv
            ? `Plan v${pv.id} · ${PLAN_STATUS_LABEL[pv.status]}${pv.parent_version_id ? ` · dựa trên v${pv.parent_version_id}` : ""} · ${count} lệnh trong ngày · giờ Việt Nam`
            : "Chưa có lịch đang áp dụng — xếp lịch ở Kanban lệnh."}
        </p>
        <div className="row small" style={{ gap: 12, marginTop: 8, flexWrap: "wrap" }}>
          <span className="legend prio-block-vip">VIP</span>
          <span className="legend prio-block-urgent">Khẩn</span>
          <span className="legend prio-block-normal">Thường</span>
          <span className="legend legend-flag" title="Rê chuột vào cờ trên lịch để xem giờ trả">
            <FlagIcon /> Giờ trả
          </span>
          <span className="legend timeline-late">Trễ giờ trả</span>
        </div>
        {notice && (
          <div className={`notice notice-${notice.tone}`} role="status" style={{ marginTop: 12 }}>
            {notice.text}
          </div>
        )}
        {error && (
          <div className="notice notice-error" role="alert" style={{ marginTop: 12 }}>
            {error}
          </div>
        )}
      </section>
      {view && (
        <section className="card span-all timeline-card">
          <LineTimeline view={view} day={day} pickedId={picked?.work_order_id ?? null} onPick={setPicked} />
        </section>
      )}
      {picked && (
        <Detail
          key={picked.work_order_id}
          slot={picked}
          editable={
            can(role, "EDIT_SCHEDULE") && pv?.status === "ACTIVE" && MANUAL_STATES.includes(picked.state)
          }
          onClose={() => setPicked(null)}
          onEdited={edited}
        />
      )}
    </>
  );
}

export default function SchedulePage() {
  return (
    <Suspense>
      <AppShell
        allow={ALL}
        crumb="Vận hành / Lịch Line A / B"
        title="Lịch Line A / B"
        subtitle="Timeline theo giờ của 2 line. Bấm khối để xem chi tiết và lý do xếp."
      >
        {(me) => <SchedulePanel role={me.role!} />}
      </AppShell>
    </Suspense>
  );
}
