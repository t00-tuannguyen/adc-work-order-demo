"use client";

// Kanban lệnh — ADC-003 (T-029): cột theo nhóm trạng thái + 2 cột ngoại lệ; Điều phối xếp lịch và chuyển
// trạng thái vận hành ngay trên thẻ. Lịch tự tính theo luật (earliest feasible), không phải AI.
// ADC-005 (T-039): kiểm tra rủi ro đơn mới trên thẻ — banner vàng WARN / đỏ BLOCK; xếp lịch WARN = yêu cầu duyệt.
// BR-15: Điều phối xếp tay / sửa lịch (chọn line + giờ) cho đơn chưa chạy.
// T-055: Kinh doanh xóa lệnh nháp ngay trên thẻ (icon thùng rác → xác nhận trên thẻ); bấm thẻ → màn chi tiết lệnh.
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { HistoryTimeline } from "@/components/HistoryTimeline";
import { ManualScheduleForm } from "@/components/ManualScheduleForm";
import { RiskBanner } from "@/components/RiskBanner";
import {
  ApiError,
  changeWorkOrderState,
  deleteWorkOrder,
  listWorkOrders,
  riskCheck,
  scheduleWorkOrder,
} from "@/lib/api";
import {
  canDeleteDraft,
  canEditManually,
  COLUMNS,
  columnOf,
  groupByColumn,
  hhmm,
  type ManualScheduleResult,
  NEXT_STEP,
  PRIORITY_CLASS,
  type ScheduleResult,
  scheduleQueue,
  scheduleHref,
  slotText,
  STATE_LABEL,
  type WorkOrderCard,
} from "@/lib/board";
import { formatDuration } from "@/lib/estimate";
import { formatVN, PRIORITY_LABEL, shortId } from "@/lib/intake";
import { blockedRisk, canCheckRisk, type RiskCheck } from "@/lib/risk";
import { can, type Role } from "@/lib/roles";

const ALL: Role[] = ["SALES", "PLANNER", "OPS_MANAGER", "ADMIN"];

type Notice = { tone: "success" | "warn" | "error"; text: string };

function TrashIcon() {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      aria-hidden="true"
    >
      <path
        d="M4 7h16M10 11v6M14 11v6M5 7l1 12a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2l1-12M9 7V4h6v3"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function Card({
  card,
  role,
  busy,
  risk,
  onSchedule,
  onNext,
  onCheckRisk,
  onManualDone,
  onDelete,
}: {
  card: WorkOrderCard;
  role: Role;
  busy: boolean;
  risk?: RiskCheck;
  onSchedule: (c: WorkOrderCard) => void;
  onNext: (c: WorkOrderCard) => void;
  onCheckRisk: (c: WorkOrderCard) => void;
  onManualDone: (c: WorkOrderCard, r: ManualScheduleResult) => void;
  onDelete: (c: WorkOrderCard) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const router = useRouter();
  const canOpen = can(role, "UPLOAD_TICKET"); // màn /intake/[id] chỉ cho Kinh doanh
  const next = NEXT_STEP[card.state];
  const canSchedule = can(role, "EDIT_SCHEDULE") && card.state === "FEASIBILITY_CHECK" && risk?.level !== "BLOCK";
  const canMove = can(role, "CHANGE_OPERATIONAL_STATE") && next;
  // Thẻ ở cột Nháp (DRAFT / chờ xếp lịch) không có nút kiểm tra rủi ro — xếp lịch tự kiểm tra (BR-07)
  const canRisk = canCheckRisk(card.state) && !!card.estimated_duration_min && columnOf(card) !== "draft";
  const canManual = can(role, "EDIT_SCHEDULE") && canEditManually(card);
  const canDelete = can(role, "UPLOAD_TICKET") && canDeleteDraft(card);
  // Có phương án chờ duyệt → người duyệt mở thẳng trang Chờ duyệt (ADC-006 T-042)
  const canReview = can(role, "APPROVE_PLAN_VERSION") && card.slot?.plan_status === "PENDING_APPROVAL";
  return (
    <li
      className={`kanban-card${canOpen ? " kanban-card-link" : ""}`}
      onClick={(e) => {
        // Bấm nút / form trong thẻ không mở chi tiết; mã lệnh vẫn là link cho bàn phím
        if (!canOpen || (e.target as HTMLElement).closest("a, button, input, select, textarea, label, form, [role=alertdialog]")) return;
        router.push(`/intake/${card.id}`);
      }}
    >
      <div className="row" style={{ justifyContent: "space-between" }}>
        {canOpen ? (
          <Link className="mono small" href={`/intake/${card.id}`}>
            {shortId(card.id)}
          </Link>
        ) : (
          <span className="mono small">{shortId(card.id)}</span>
        )}
        <div className="row" style={{ gap: 6 }}>
          {card.priority && <span className={PRIORITY_CLASS[card.priority]}>{PRIORITY_LABEL[card.priority]}</span>}
          {canDelete && (
            <button
              className="btn btn-sm btn-danger-text btn-icon"
              disabled={busy || confirmDelete}
              onClick={() => setConfirmDelete(true)}
              aria-label={`Xóa lệnh nháp ${shortId(card.id)}`}
              title="Xóa nháp"
            >
              <TrashIcon />
            </button>
          )}
        </div>
      </div>
      <div className="kanban-product">{card.product_name || "—"}</div>
      <dl className="kanban-meta">
        <dt>Giờ trả</dt>
        <dd>{formatVN(card.requested_return)}</dd>
        {card.estimated_duration_min != null && (
          <>
            <dt>Thời lượng</dt>
            <dd>{formatDuration(card.estimated_duration_min)}</dd>
          </>
        )}
        {card.slot && (
          <>
            <dt>Lịch</dt>
            <dd>
              <Link href={scheduleHref(card.id, card.slot)} title="Xem trên lịch Line A / B">
                {slotText(card.slot)}
              </Link>
              {card.slot.plan_status !== "ACTIVE" && <span className="muted"> (đề xuất v{card.slot.plan_version})</span>}
            </dd>
          </>
        )}
      </dl>
      <div className="row" style={{ gap: 6, flexWrap: "wrap" }}>
        <span className="badge">{STATE_LABEL[card.state] ?? card.state}</span>
        {card.slot && !card.slot.sla_ok && <span className="badge badge-danger">Trễ giờ trả</span>}
      </div>
      {risk && risk.level !== "OK" && <RiskBanner risk={risk} compact />}
      {canDelete && confirmDelete && (
        <div className="notice notice-error" role="alertdialog" aria-label={`Xác nhận xóa ${shortId(card.id)}`}>
          <div className="stack" style={{ gap: 6 }}>
            <span className="small">Xóa lệnh nháp này? Không khôi phục được.</span>
            <div className="row" style={{ gap: 6, justifyContent: "flex-end" }}>
              <button className="btn btn-sm" disabled={busy} onClick={() => setConfirmDelete(false)} autoFocus>
                Hủy
              </button>
              <button className="btn btn-sm btn-danger" disabled={busy} onClick={() => onDelete(card)}>
                Xóa
              </button>
            </div>
          </div>
        </div>
      )}
      {editing && (
        <ManualScheduleForm
          workOrderId={card.id}
          durationMin={card.estimated_duration_min!}
          requestedReturn={card.requested_return}
          expectedArrival={card.expected_arrival}
          initialLine={card.slot?.line}
          initialStart={card.slot?.start}
          onDone={(r) => {
            setEditing(false);
            onManualDone(card, r);
          }}
          onCancel={() => setEditing(false)}
        />
      )}
      {!editing && (
        <div className="row" style={{ gap: 6, flexWrap: "wrap" }}>
          {canReview && (
            <Link className="btn btn-sm btn-primary" href="/approvals">
              Xem để duyệt
            </Link>
          )}
          {canSchedule && (
            <button
              className="btn btn-sm btn-primary"
              disabled={busy || !card.estimated_duration_min}
              title={card.estimated_duration_min ? undefined : "Chưa có ước tính thời lượng"}
              onClick={() => onSchedule(card)}
            >
              {risk?.level === "WARN" ? "Yêu cầu duyệt nhận đơn" : "Xếp lịch"}
            </button>
          )}
          {canManual && (
            <button className="btn btn-sm" disabled={busy} onClick={() => setEditing(true)}>
              {card.slot ? "Sửa lịch" : "Xếp tay"}
            </button>
          )}
          {canRisk && (
            <button className="btn btn-sm" disabled={busy} onClick={() => onCheckRisk(card)}>
              {risk ? "Kiểm tra lại rủi ro" : "Kiểm tra rủi ro"}
            </button>
          )}
          {canMove && (
            <button className="btn btn-sm" disabled={busy} onClick={() => onNext(card)}>
              {next.label}
            </button>
          )}
          <button
            className="btn btn-sm btn-ghost"
            aria-expanded={showHistory}
            onClick={() => setShowHistory((s) => !s)}
          >
            {showHistory ? "Ẩn lịch sử" : "Lịch sử"}
          </button>
        </div>
      )}
      {showHistory && <HistoryTimeline workOrderId={card.id} />}
    </li>
  );
}

function Board({ role }: { role: Role }) {
  const [cards, setCards] = useState<WorkOrderCard[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<Notice | null>(null);
  const [risks, setRisks] = useState<Record<string, RiskCheck>>({});
  const remember = (id: string, risk: RiskCheck) => setRisks((r) => ({ ...r, [id]: risk }));

  const load = useCallback(
    () =>
      listWorkOrders()
        .then(setCards)
        .catch((e) =>
          setNotice({ tone: "error", text: e instanceof ApiError ? e.message : "Không tải được danh sách lệnh." }),
        ),
    [],
  );

  useEffect(() => {
    listWorkOrders()
      .then(setCards)
      .catch(() => setNotice({ tone: "error", text: "Không tải được danh sách lệnh." }));
  }, []);

  async function run(action: () => Promise<Notice>) {
    setBusy(true);
    try {
      setNotice(await action());
    } catch (e) {
      const text = e instanceof ApiError ? e.message : "Thao tác thất bại.";
      setNotice({ tone: "error", text: e instanceof ApiError && e.status === 409 ? `${text} — đã tải lại.` : text });
    } finally {
      await load();
      setBusy(false);
    }
  }

  /** Xếp 1 lệnh; 409 NEW_ORDER_BLOCKED → `blocked` (đơn đã sang BLOCK_NEW_ORDER), giữ rủi ro để hiện banner đỏ. */
  async function scheduleOne(c: WorkOrderCard): Promise<{ r: ScheduleResult } | { blocked: RiskCheck }> {
    try {
      const r = await scheduleWorkOrder(c.id);
      remember(c.id, r.risk);
      return { r };
    } catch (e) {
      const risk = e instanceof ApiError ? blockedRisk(e.detail) : null;
      if (!risk) throw e;
      remember(c.id, risk);
      return { blocked: risk };
    }
  }

  const schedule = (c: WorkOrderCard) =>
    run(async () => {
      const out = await scheduleOne(c);
      if ("blocked" in out) return { tone: "error", text: `${shortId(c.id)} bị chặn (BLOCK): ${out.blocked.reasons[0]}` };
      const { r } = out;
      if (r.risk.level === "WARN")
        return { tone: "warn", text: `${shortId(c.id)}: ${r.risk.reasons[0]} Plan v${r.plan_version} chờ duyệt nhận đơn.` };
      return { tone: "success", text: `${shortId(c.id)}: ${r.reason} (plan v${r.plan_version})` };
    });

  const scheduleAll = () =>
    run(async () => {
      const queue = scheduleQueue(cards ?? []);
      const lines: string[] = [];
      let warn = 0;
      let blocked = 0;
      for (const c of queue) {
        const out = await scheduleOne(c);
        if ("blocked" in out) {
          blocked += 1;
          lines.push(`${shortId(c.id)} bị chặn`);
          continue;
        }
        const { r } = out;
        if (r.risk.level === "WARN") warn += 1;
        lines.push(
          `${shortId(c.id)} → Line ${r.line} ${hhmm(r.start)}–${hhmm(r.end)}${r.risk.level === "WARN" ? " (chờ duyệt nhận đơn)" : ""}`,
        );
      }
      const extra = [warn && `${warn} lệnh cần duyệt nhận đơn`, blocked && `${blocked} lệnh bị chặn`].filter(Boolean);
      const text = `Đã xếp ${queue.length} lệnh theo VIP → Khẩn → Thường${extra.length ? `, ${extra.join(", ")}` : ""}: ${lines.join("; ")}`;
      return { tone: blocked ? "error" : warn ? "warn" : "success", text };
    });

  const manualDone = (c: WorkOrderCard, r: ManualScheduleResult) => {
    const pending = r.plan_status !== "ACTIVE";
    setNotice({
      tone: pending ? "warn" : "success",
      text: `${shortId(c.id)}: ${r.reason} (plan v${r.plan_version}${pending ? " — chờ duyệt, lịch hiện tại giữ nguyên" : ""})`,
    });
    void load();
  };

  const remove = (c: WorkOrderCard) =>
    run(async () => {
      await deleteWorkOrder(c.id);
      return { tone: "success", text: `Đã xóa lệnh nháp ${shortId(c.id)}.` };
    });

  const checkRisk = (c: WorkOrderCard) =>
    run(async () => {
      const r = await riskCheck(c.id);
      remember(c.id, r);
      const tone = r.level === "OK" ? "success" : r.level === "WARN" ? "warn" : "error";
      return { tone, text: `${shortId(c.id)} — rủi ro ${r.level}: ${r.reasons[0]}` };
    });

  const next = (c: WorkOrderCard) =>
    run(async () => {
      const step = NEXT_STEP[c.state]!;
      const r = await changeWorkOrderState(c.id, step.to, step.label);
      return { tone: "success", text: `${shortId(c.id)} → ${STATE_LABEL[r.state]}` };
    });

  if (!cards) return <div className="card span-all muted">Đang tải…</div>;
  const groups = groupByColumn(cards);
  const queue = scheduleQueue(cards);

  return (
    <>
      <section className="card span-all">
        <div className="row" style={{ justifyContent: "space-between", flexWrap: "wrap", gap: 12 }}>
          <p className="muted small" style={{ margin: 0 }}>
            {cards.length} lệnh · lịch tính bằng luật earliest feasible (hòa → Line A); đơn mới kịp nhờ đẩy đơn khác
            cần duyệt, không kịp thì bị chặn.
          </p>
          <div className="row" style={{ gap: 8 }}>
            <Link className="btn btn-sm" href="/schedule">
              Xem lịch Line A / B
            </Link>
            <button
              className="btn btn-sm"
              disabled={busy}
              onClick={() => {
                setNotice(null);
                void load();
              }}
            >
              Tải lại
            </button>
            {can(role, "EDIT_SCHEDULE") && (
              <button className="btn btn-sm btn-primary" disabled={busy || !queue.length} onClick={scheduleAll}>
                Xếp tất cả đơn chờ ({queue.length})
              </button>
            )}
          </div>
        </div>
        {notice && (
          <div className={`notice notice-${notice.tone}`} role="status" style={{ marginTop: 12 }}>
            {notice.text}
          </div>
        )}
      </section>
      <div className="kanban span-all" role="list" aria-label="Kanban lệnh theo trạng thái">
        {COLUMNS.map((col) => (
          <section
            key={col.key}
            className={`kanban-col${col.exception ? " kanban-col-exception" : ""}`}
            role="listitem"
            aria-label={col.label}
          >
            <h2 className="kanban-col-title">
              {col.label}
              <span className="kanban-count">{groups[col.key].length}</span>
            </h2>
            <ul className="kanban-list">
              {groups[col.key].map((c) => (
                <Card
                  key={c.id}
                  card={c}
                  role={role}
                  busy={busy}
                  risk={canCheckRisk(c.state) ? risks[c.id] : undefined}
                  onSchedule={schedule}
                  onNext={next}
                  onCheckRisk={checkRisk}
                  onManualDone={manualDone}
                  onDelete={remove}
                />
              ))}
            </ul>
          </section>
        ))}
      </div>
    </>
  );
}

export default function BoardPage() {
  return (
    <AppShell
      allow={ALL}
      crumb="Vận hành / Kanban lệnh"
      title="Kanban lệnh"
      subtitle="Trạng thái và phân bổ line của mọi lệnh. Màu ưu tiên: VIP · Khẩn · Thường."
    >
      {(me) => <Board role={me.role!} />}
    </AppShell>
  );
}
