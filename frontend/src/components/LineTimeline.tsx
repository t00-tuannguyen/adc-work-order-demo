"use client";

// Timeline 2 line theo giờ (giờ Việt Nam) — dùng chung cho màn lịch (ADC-003 T-030) và màn so sánh trước / sau sự cố
// (ADC-004 T-035). Khối màu theo ưu tiên, vạch đỏ tại giờ trả, khung dừng sự cố tô xám gạch chéo.
// Dựng bằng CSS (không thêm thư viện timeline — ADR-0002).
import {
  blockPosition,
  hhmm,
  type Line,
  markerPosition,
  returnLabel,
  type ScheduleSlot,
  type ScheduleView,
} from "@/lib/board";
import { shortId } from "@/lib/intake";

const LINES: Line[] = ["A", "B"];
const HOURS = Array.from({ length: 13 }, (_, i) => i * 2); // vạch mỗi 2 giờ

export interface Downtime {
  line: Line;
  start: string;
  end: string;
  label: string; // "Sự cố #1: Line A dừng 09:00–12:00"
}

export function FlagIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path d="M5 21V4h11l-2 4 2 4H7v9z" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
    </svg>
  );
}

export function LineTimeline({
  view,
  day,
  pickedId = null,
  onPick,
  downtimes = [],
  highlight,
  caption,
}: {
  view: ScheduleView;
  day: string;
  pickedId?: string | null;
  onPick?: (s: ScheduleSlot) => void;
  downtimes?: Downtime[];
  /** Đơn cần làm nổi (vd đơn bị ảnh hưởng bởi sự cố); đơn khác mờ đi. Bỏ trống = không làm mờ. */
  highlight?: ReadonlySet<string>;
  caption?: string;
}) {
  return (
    <div className="timeline" role="table" aria-label={caption ?? `Lịch Line A / B ngày ${day}`}>
      <div className="timeline-row timeline-axis" role="row">
        <div className="timeline-label" role="columnheader">
          Giờ
        </div>
        <div className="timeline-track">
          {HOURS.map((h) => (
            <span key={h} className="timeline-tick" style={{ left: `${(h / 24) * 100}%` }}>
              {String(h).padStart(2, "0")}:00
            </span>
          ))}
        </div>
      </div>
      {LINES.map((line) => (
        <div className="timeline-row" role="row" key={line}>
          <div className="timeline-label" role="rowheader">
            Line {line}
          </div>
          <div className="timeline-track timeline-lane">
            {HOURS.map((h) => (
              <span key={h} className="timeline-grid" style={{ left: `${(h / 24) * 100}%` }} />
            ))}
            {downtimes
              .filter((d) => d.line === line)
              .map((d) => {
                const pos = blockPosition(d.start, d.end, day);
                if (!pos) return null;
                return (
                  <span
                    key={`${d.start}-${d.end}`}
                    className="timeline-downtime"
                    style={{ left: `${pos.left}%`, width: `${pos.width}%` }}
                    title={d.label}
                    role="img"
                    aria-label={d.label}
                  />
                );
              })}
            {view.lines[line].map((s) => {
              const pos = blockPosition(s.start, s.end, day);
              if (!pos) return null;
              const marker = markerPosition(s.requested_return, day);
              const ret = returnLabel(s.requested_return, day);
              const label = `${shortId(s.work_order_id)} ${s.product_name ?? ""}, ${hhmm(s.start)}–${hhmm(s.end)}${
                ret ? `, ${ret}` : ""
              }${s.sla_ok ? "" : ", trễ giờ trả"}`;
              const dim = highlight && !highlight.has(s.work_order_id);
              return (
                <span key={s.work_order_id}>
                  <button
                    className={`timeline-block prio-block-${(s.priority ?? "NORMAL").toLowerCase()}${
                      s.sla_ok ? "" : " timeline-late"
                    }${pos.clippedStart ? " clip-start" : ""}${pos.clippedEnd ? " clip-end" : ""}${
                      s.work_order_id === pickedId ? " timeline-picked" : ""
                    }${dim ? " timeline-dim" : ""}`}
                    id={`slot-${s.work_order_id}`}
                    aria-pressed={onPick ? s.work_order_id === pickedId : undefined}
                    style={{ left: `${pos.left}%`, width: `${pos.width}%` }}
                    title={label}
                    aria-label={label}
                    onClick={() => onPick?.(s)}
                  >
                    <span className="mono">{shortId(s.work_order_id)}</span> {hhmm(s.start)}–{hhmm(s.end)}
                    {marker === null && ret && (
                      <span className="timeline-block-flag" title={`Giờ ${ret}`}>
                        <FlagIcon />
                      </span>
                    )}
                  </button>
                  {marker !== null && <span className="timeline-return" style={{ left: `${marker}%` }} aria-hidden="true" />}
                  {marker !== null && (
                    <span className="timeline-return-flag" style={{ left: `${marker}%` }} title={`Giờ ${ret}`}>
                      <FlagIcon />
                    </span>
                  )}
                </span>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}
