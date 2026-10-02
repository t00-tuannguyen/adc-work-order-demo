"use client";

// Tiếp nhận đơn — ADC-001 (T-021): tải PDF (nhiều file, mỗi file 1 ingest job) / nhập tay, tiến độ 4 bước, hàng đợi cảnh báo.
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { AppShell } from "@/components/AppShell";
import {
  ackIntakeWarning,
  ApiError,
  createTicket,
  getIngestJob,
  listIntakeWarnings,
  uploadTicket,
} from "@/lib/api";
import {
  afterUploadPath,
  FLAG_LABEL,
  fieldLabel,
  formatVN,
  type IngestJob,
  type IngestStep,
  type IntakeWarning,
  JOB_ERROR,
  type JobWorkOrder,
  pickPdfFiles,
  pollDelay,
  REVIEW_LABEL,
  REVIEW_TONE,
  shortId,
  STATE_LABEL,
  stepStates,
  STEPS,
} from "@/lib/intake";

const MAX_MB = 10;
const MAX_PAGES = 20;
// Không có Order Agent (chưa cấu hình GEMINI_API_KEY) → job đứng ở UPLOADED
const STUCK_MS = 15000;

/** Hỏi trạng thái job tới khi xong / lỗi, hoặc dừng sớm khi `alive()` false (đã rời trang). */
async function pollJob(jobId: string, update: (p: Partial<Item>) => void, alive: () => boolean): Promise<IngestJob> {
  const started = Date.now();
  for (let attempt = 0; ; attempt++) {
    const j = await getIngestJob(jobId);
    update({ job: j, ...(j.step !== "FAILED" && { lastStep: j.step }) });
    if (j.status === "SUCCEEDED" || j.status === "FAILED" || !alive()) return j;
    update({ stuck: j.status === "QUEUED" && Date.now() - started > STUCK_MS });
    await new Promise((r) => setTimeout(r, pollDelay(attempt)));
  }
}

function uploadError(e: unknown): string {
  if (!(e instanceof ApiError)) return "Không tải được file. Kiểm tra kết nối rồi thử lại.";
  if (e.status === 413) return `File vượt ${MAX_MB} MB.`;
  if (e.status === 415) return "Chỉ nhận file PDF.";
  if (e.status === 422) return `PDF không đọc được: ${e.message} (có mật khẩu, bị hỏng hoặc quá ${MAX_PAGES} trang).`;
  if (e.status === 403) return "Bạn không có quyền tải ticket.";
  return e.message;
}

function Progress({ job, lastStep }: { job: IngestJob; lastStep: IngestStep }) {
  const states = stepStates(job, lastStep);
  return (
    <div>
      <div
        className="progress"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={job.progress}
        aria-label="Tiến độ xử lý file"
      >
        <div className={`progress-bar${job.status === "FAILED" ? " failed" : ""}`} style={{ width: `${job.progress}%` }} />
      </div>
      <ol className="steps">
        {STEPS.map((s, i) => (
          <li key={s.step} className={`step step-${states[i]}`} aria-current={states[i] === "active" ? "step" : undefined}>
            <span className="step-dot" aria-hidden="true">
              {states[i] === "done" ? "✓" : states[i] === "failed" ? "!" : i + 1}
            </span>
            {s.label}
            <span className="sr-only">
              {states[i] === "done" ? " — xong" : states[i] === "active" ? " — đang chạy" : states[i] === "failed" ? " — lỗi" : ""}
            </span>
          </li>
        ))}
      </ol>
    </div>
  );
}

function OrderList({ orders }: { orders: JobWorkOrder[] }) {
  return (
    <ul className="order-list">
      {orders.map((wo) => (
        <li key={wo.id}>
          <span className="mono">{shortId(wo.id)}</span>
          <span className="badge">{STATE_LABEL[wo.state] ?? wo.state}</span>
          {wo.review_status && <span className={REVIEW_TONE[wo.review_status]}>{REVIEW_LABEL[wo.review_status]}</span>}
          <Link className="btn btn-sm" href={`/intake/${wo.id}`}>
            Mở lệnh
          </Link>
        </li>
      ))}
    </ul>
  );
}

type Item = {
  key: string;
  file: File;
  job: IngestJob | null;
  lastStep: IngestStep;
  error: string | null;
  stuck: boolean;
  running: boolean;
};

// Gemini hay 503 khi quá tải → chạy song song ít job
const CONCURRENCY = 2;

function CloseIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
      <path d="M6 6l12 12M18 6L6 18" strokeLinecap="round" />
    </svg>
  );
}

function FileRow({ item, onRemove, onRetry }: { item: Item; onRemove: () => void; onRetry: () => void }) {
  const { file, job, error, stuck, running } = item;
  const failed = !!error || job?.status === "FAILED";
  const done = job?.status === "SUCCEEDED";
  return (
    <li className="stack" style={{ gap: 8, paddingBottom: 12, borderBottom: "1px solid var(--border)" }}>
      <div className="row" style={{ justifyContent: "space-between", gap: 8, flexWrap: "wrap" }}>
        <span>
          <strong>{file.name}</strong> <span className="small muted">· {(file.size / 1024).toFixed(0)} KB</span>
        </span>
        <span className="row" style={{ gap: 6 }}>
          {done && <span className="badge badge-success">{job.work_orders.length} lệnh</span>}
          {failed && (
            <button className="btn btn-sm" onClick={onRetry}>
              Thử lại
            </button>
          )}
          {!running && !done && (
            <button className="btn btn-sm btn-icon" onClick={onRemove} aria-label={`Bỏ ${file.name}`} title="Bỏ file">
              <CloseIcon />
            </button>
          )}
        </span>
      </div>
      {job && <Progress job={job} lastStep={item.lastStep} />}
      {stuck && !failed && (
        <div className="notice notice-warn">
          File đã lưu nhưng chưa được xử lý — có thể Order Agent chưa được cấu hình. Bạn có thể nhập tay.
        </div>
      )}
      {failed && (
        <div className="notice notice-error" role="alert">
          {error ?? JOB_ERROR[job?.error_code ?? ""] ?? "Xử lý file thất bại."}
        </div>
      )}
      {done && job.work_orders.length > 0 && <OrderList orders={job.work_orders} />}
    </li>
  );
}

function IntakeCard() {
  const router = useRouter();
  const [items, setItems] = useState<Item[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  // Rời trang → dừng hỏi trạng thái job (job vẫn chạy ở backend)
  const alive = useRef(true);
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);

  const patch = (key: string, p: Partial<Item>) =>
    setItems((list) => list.map((it) => (it.key === key ? { ...it, ...p } : it)));

  const poll = (key: string, jobId: string) =>
    pollJob(jobId, (p) => patch(key, p), () => alive.current);

  async function process(it: Item): Promise<IngestJob | null> {
    patch(it.key, { running: true, error: null, job: null, stuck: false, lastStep: "UPLOADED" });
    try {
      const { job_id } = await uploadTicket(it.file);
      return await poll(it.key, job_id);
    } catch (e) {
      patch(it.key, { error: uploadError(e) });
      return null;
    } finally {
      patch(it.key, { running: false });
    }
  }

  async function run(queue: Item[]) {
    if (!queue.length) return;
    setBusy(true);
    setError(null);
    const jobs: (IngestJob | null)[] = [];
    let next = 0;
    const worker = async () => {
      while (next < queue.length) {
        const i = next++;
        jobs[i] = await process(queue[i]);
      }
    };
    await Promise.all(Array.from({ length: Math.min(CONCURRENCY, queue.length) }, worker));
    setBusy(false);
    // 1 file → 1 lệnh: cần xử lý → màn xác nhận; tự tạo lệnh thành công → Kanban
    const orders = jobs.flatMap((j) => (j?.status === "SUCCEEDED" ? j.work_orders : []));
    if (alive.current && items.length === 1 && queue.length === 1 && orders.length === 1)
      router.push(afterUploadPath(orders[0]));
  }

  const pending = items.filter((it) => !it.job && !it.error && !it.running);
  const upload = () => run(pending);

  async function manual() {
    setBusy(true);
    try {
      const { work_orders } = await createTicket("MANUAL");
      router.push(`/intake/${work_orders[0].id}`);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Không tạo được lệnh nhập tay.");
      setBusy(false);
    }
  }

  function pick(list: FileList | null | undefined) {
    setError(null);
    if (!list?.length) return;
    const { accepted, rejected } = pickPdfFiles(Array.from(list), items.map((it) => it.file), MAX_MB);
    if (rejected.length) setError(`Bỏ qua: ${rejected.map((r) => `${r.name} (${r.reason})`).join(", ")}.`);
    const stamp = Date.now();
    setItems((cur) => [
      ...cur,
      ...accepted.map((file, i) => ({
        key: `${stamp}-${i}-${file.name}`,
        file,
        job: null,
        lastStep: "UPLOADED" as IngestStep,
        error: null,
        stuck: false,
        running: false,
      })),
    ]);
    if (inputRef.current) inputRef.current.value = "";
  }

  const finished = items.length > 0 && !busy && pending.length === 0;
  const totalOrders = items.reduce((n, it) => n + (it.job?.status === "SUCCEEDED" ? it.job.work_orders.length : 0), 0);

  return (
    <section className="card span-all" aria-labelledby="intake-title">
      <h2 className="card-title" id="intake-title">
        Tiếp nhận ticket
      </h2>
      <div className="stack">
        <div
          className={`dropzone${dragging ? " dragging" : ""}`}
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            pick(e.dataTransfer.files);
          }}
        >
          <p style={{ margin: 0, fontWeight: 600 }}>Kéo thả một hoặc nhiều file PDF ticket vào đây</p>
          <p className="small muted" style={{ margin: 0 }}>
            PDF văn bản hoặc bản scan · mỗi file tối đa {MAX_MB} MB, {MAX_PAGES} trang · 1 file có thể chứa nhiều ticket
          </p>
          <input
            ref={inputRef}
            id="ticket-file"
            type="file"
            accept="application/pdf,.pdf"
            multiple
            className="sr-only"
            onChange={(e) => pick(e.target.files)}
          />
          <button className="btn" type="button" onClick={() => inputRef.current?.click()}>
            Chọn file từ máy
          </button>
        </div>
        {error && (
          <div className="notice notice-error" role="alert">
            {error}
          </div>
        )}
        {items.length > 0 && (
          <ul className="stack" aria-live="polite" style={{ listStyle: "none", padding: 0, margin: 0 }}>
            {items.map((it) => (
              <FileRow
                key={it.key}
                item={it}
                onRemove={() => setItems((list) => list.filter((x) => x.key !== it.key))}
                onRetry={() => run([it])}
              />
            ))}
          </ul>
        )}
        <div className="row" style={{ gap: 8 }}>
          <button className="btn btn-primary" disabled={!pending.length || busy} onClick={upload}>
            {busy ? "Đang xử lý…" : pending.length > 1 ? `Tải lên & trích xuất ${pending.length} file` : "Tải lên & trích xuất"}
          </button>
          {finished && (
            <button className="btn" onClick={() => setItems([])}>
              Xóa danh sách
            </button>
          )}
        </div>
        {finished && items.length > 1 && (
          <p className="small muted" style={{ margin: 0 }}>
            Xong {items.length} file · tạo {totalOrders} lệnh.
          </p>
        )}
      </div>
      <div className="divider-row">
        <span className="muted">Không có file hoặc AI không đọc được?</span>
        <button className="btn-link" onClick={manual} disabled={busy}>
          Nhập tay 8 trường
        </button>
      </div>
    </section>
  );
}

function WarningsCard() {
  const [items, setItems] = useState<IntakeWarning[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    listIntakeWarnings()
      .then(setItems)
      .catch((e) => setError(e instanceof ApiError ? e.message : "Không tải được cảnh báo."));
  }, []);
  useEffect(load, [load]);

  async function ack(id: number) {
    try {
      await ackIntakeWarning(id);
      load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Không xác nhận được.");
    }
  }

  return (
    <section className="card span-all" aria-labelledby="warn-title">
      <div className="row" style={{ justifyContent: "space-between" }}>
        <h2 className="card-title" id="warn-title">
          Cảnh báo tiếp nhận
        </h2>
        {items && <span className={items.length ? "badge badge-warn" : "badge"}>{items.length} đang mở</span>}
      </div>
      <p className="card-sub">Lệnh đã tự tạo nhưng có điểm chưa rõ — xem lại và đánh dấu đã xem.</p>
      {error && (
        <div className="notice notice-error" role="alert">
          {error}
        </div>
      )}
      {items && items.length === 0 && <p className="muted small">Không có cảnh báo nào đang mở.</p>}
      {items && items.length > 0 && (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th scope="col">Lệnh</th>
                <th scope="col">Trường</th>
                <th scope="col">Lý do</th>
                <th scope="col">Lúc</th>
                <th scope="col">
                  <span className="sr-only">Thao tác</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {items.map((w) => (
                <tr key={w.id}>
                  <td className="mono">
                    <Link href={`/intake/${w.work_order_id}`}>{shortId(w.work_order_id)}</Link>
                  </td>
                  <td>{fieldLabel(w.field)}</td>
                  <td>{FLAG_LABEL[w.code]}</td>
                  <td className="small">{formatVN(w.created_at)}</td>
                  <td style={{ textAlign: "right" }}>
                    <button className="btn btn-sm" onClick={() => ack(w.id)}>
                      Đã xem
                    </button>
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

export default function IntakePage() {
  return (
    <AppShell
      allow={["SALES"]}
      crumb="Vận hành / Tiếp nhận đơn"
      title="Tiếp nhận đơn"
      subtitle="Tải file PDF ticket của khách, AI trích xuất dữ liệu; chỉ cần bạn xác nhận khi dữ liệu chưa chắc chắn."
    >
      {() => (
        <>
          <IntakeCard />
          <WarningsCard />
        </>
      )}
    </AppShell>
  );
}
