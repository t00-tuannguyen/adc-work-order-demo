"""Đánh giá Order Agent trên bộ PDF mẫu (T-022, ADC-001 §Thiết kế AI/ML).

    .venv/bin/python -m eval.intake.run_eval [--only 01_phieu_giavi] [--delay 5] [--refresh]

Gọi provider thật theo ORDER_AGENT_PROVIDER (ADR-0013): gemini (GEMINI_API_KEY) hoặc openai (OPENAI_API_KEY). Kết quả thô được cache ở eval/intake/cache/<model>/ để chạy lại
không tốn quota; `--refresh` gọi lại. Kết quả: eval/results/intake-extraction.{json,md} (openai: intake-extraction-openai.{json,md}).
"""

import argparse
import json
import time
from datetime import datetime
from pathlib import Path

from eval.intake.scoring import FIELDS, SampleScore, comparable, score_ticket, summarize
from src.agents.graph import get_throughput_config
from src.agents.order_agent import GeminiOrderAgent, OpenAIOrderAgent, PdfExtractor, normalize
from src.agents.schemas import DocumentExtraction
from src.modules.intake import ReviewDecision, ReviewThresholds, TicketSignal, inspect_pdf, run_gate
from src.services.gemini import get_gemini_client
from src.services.llm import get_llm
from src.settings import get_settings

PDFS = Path("src/seed/pdfs")
CACHE = Path("eval/intake/cache")
RESULTS = Path("eval/results")


def extract(agent: PdfExtractor, model: str, sample_id: str, received_at: datetime, refresh: bool) -> dict:
    """{doc, latency_s} hoặc {error}; ghi cache."""
    cached = CACHE / model / f"{sample_id}.json"
    if cached.exists() and not refresh:
        return json.loads(cached.read_text())
    path = PDFS / f"{sample_id}.pdf"
    info = inspect_pdf(path, max_pages=get_settings().max_pdf_pages)
    t0 = time.perf_counter()
    try:
        doc = agent.extract_pdf(path.read_bytes(), page_count=info.page_count, received_at=received_at)
        out = {"doc": doc.model_dump(mode="json"), "latency_s": round(time.perf_counter() - t0, 1)}
    except Exception as e:  # noqa: BLE001 — ghi lại lỗi để báo cáo, không dừng cả bộ
        out = {"error": f"{type(e).__name__}: {e.__cause__ or e}"[:300]}
    if "doc" in out:  # chỉ cache kết quả thành công (lỗi quota/quá tải → lần sau gọi lại)
        cached.parent.mkdir(parents=True, exist_ok=True)
        cached.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n")
    return out


def score_sample(sample_id: str, answer: dict, result: dict, thresholds, allowed_doses) -> SampleScore:
    expected = answer["tickets"]
    if "error" in result:
        s = SampleScore(sample_id, answer["kind"], len(expected), 0, error=result["error"])
        s.tickets = [score_ticket(t, None, {}, None) for t in expected]
        return s
    doc = DocumentExtraction.model_validate(result["doc"])
    predicted = sorted(doc.tickets, key=lambda t: t.page_from)
    s = SampleScore(sample_id, answer["kind"], len(expected), len(predicted), latency_s=result.get("latency_s"))
    for i, exp in enumerate(expected):
        if i >= len(predicted):
            s.tickets.append(score_ticket(exp, None, {}, None))
            continue
        t = predicted[i]
        n = normalize(t, thresholds)
        pages = {src.field: src.page for src in n.sources}
        ts = score_ticket(exp, comparable(n.fields), pages, (t.page_from, t.page_to))
        gate = run_gate(
            n.fields,
            n.signals,
            thresholds,
            ticket=TicketSignal(boundary_uncertain=t.boundary_uncertain),
            allowed_doses=allowed_doses,
        )
        ts.decision = "CLARIFY" if gate.errors else gate.assessment.decision.value
        s.tickets.append(ts)
    return s


def report_md(model: str, provider: str, summary: dict, scores: list[SampleScore], answers: dict) -> str:
    def pct(v):
        return "—" if v is None else f"{v * 100:.1f}%"

    lines = [
        "# Đánh giá trích xuất ticket — ADC-001 (T-022)",
        "",
        f"- Model: `{model}` · chạy lúc {datetime.now().astimezone():%d/%m/%Y %H:%M}",
        f"- Bộ mẫu: `src/seed/pdfs/` — {summary['all']['samples']} PDF giả lập "
        f"({summary['text']['samples']} văn bản số, {summary['scan']['samples']} scan), "
        f"{summary['all']['tickets_expected']} ticket, đáp án `answers.json`",
        f"- Chấm trên kết quả **sau chuẩn hóa** (như lưu vào work order). Độ tin cậy do {provider} tự chấm (ADR-0010, ADR-0013).",
        "",
        "| Chỉ số | Văn bản số | Scan | Tất cả | Mục tiêu |",
        "|---|---|---|---|---|",
    ]
    t, s, a = summary["text"], summary["scan"], summary["all"]
    rows = [
        ("Độ chính xác trường", "field_accuracy", "≥ 95% (số) · ≥ 85% (scan)"),
        ("Phát hiện đúng trường thiếu", "missing_detection", "100%"),
        ("Trang nguồn đúng", "page_accuracy", "—"),
        ("Khoảng trang ticket đúng", "page_range_accuracy", "—"),
        ("Tỷ lệ AUTO sai", "auto_wrong_rate", "≈ 0"),
    ]
    for label, key, target in rows:
        lines.append(f"| {label} | {pct(t[key])} | {pct(s[key])} | {pct(a[key])} | {target} |")
    lines += [
        f"| Số ticket nhận đúng (file) | {t['ticket_count_ok']}/{t['samples']} | {s['ticket_count_ok']}/{s['samples']} "
        f"| {a['ticket_count_ok']}/{a['samples']} | 100% |",
        f"| Lời gọi lỗi | {t['failed_calls']} | {s['failed_calls']} | {a['failed_calls']} | 0 |",
        f"| Độ trễ TB / max (s) | {t['latency_s_avg']} / {t['latency_s_max']} | {s['latency_s_avg']} / "
        f"{s['latency_s_max']} | {a['latency_s_avg']} / {a['latency_s_max']} | < 10 s (PDF 1 trang) |",
        "",
        "Quyết định cổng (tất cả ticket): "
        + ", ".join(f"{k} {v}" for k, v in a["decisions"].items())
        + f" · AUTO sai {a['auto_wrong']}/{a['auto_tickets']}",
        "",
        "## Độ chính xác theo trường",
        "",
        "| Trường | Văn bản số | Scan |",
        "|---|---|---|",
    ]
    lines += [f"| {f} | {pct(t['per_field'][f])} | {pct(s['per_field'][f])} |" for f in FIELDS]
    lines += [
        "",
        "## Từng mẫu",
        "",
        "| Mẫu | Loại | Ticket (đáp án/nhận) | Trường sai | Quyết định | Ghi chú |",
        "|---|---|---|---|---|---|",
    ]
    for sc in scores:
        wrong = [f"t{i + 1}.{f}" for i, tk in enumerate(sc.tickets) for f, ok in tk.fields_ok.items() if not ok]
        decisions = ", ".join(tk.decision or "—" for tk in sc.tickets)
        note = sc.error or answers[sc.sample_id]["about"]
        lines.append(
            f"| {sc.sample_id} | {sc.kind} | {sc.expected_tickets}/{sc.predicted_tickets} | "
            f"{', '.join(wrong) or '—'} | {decisions} | {note} |"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", help="chỉ chạy các mẫu này")
    ap.add_argument("--delay", type=float, default=5.0, help="giây nghỉ giữa 2 lời gọi (giới hạn tần suất)")
    ap.add_argument("--refresh", action="store_true", help="bỏ qua cache, gọi lại provider")
    args = ap.parse_args()

    settings = get_settings()
    answers_file = json.loads((PDFS / "answers.json").read_text())
    answers = answers_file["samples"]
    received_at = datetime.fromisoformat(answers_file["received_at"])
    if settings.order_agent_provider == "openai":
        model, out = settings.openai_order_model or settings.model_name, "intake-extraction-openai"
        agent: PdfExtractor = OpenAIOrderAgent(get_llm(model, settings.openai_order_timeout_s))
    else:
        model, out = settings.gemini_model, "intake-extraction"
        agent = GeminiOrderAgent(get_gemini_client(), model)
    config = get_throughput_config()
    thresholds = ReviewThresholds.from_config(config.raw)
    allowed = [k for k, v in config.dose_factor.items() if v is not None]

    scores = []
    for sample_id in sorted(answers):
        if args.only and sample_id not in args.only:
            continue
        cached = (CACHE / model / f"{sample_id}.json").exists()
        result = extract(agent, model, sample_id, received_at, args.refresh)
        sc = score_sample(sample_id, answers[sample_id], result, thresholds, allowed)
        scores.append(sc)
        print(
            f"{sample_id}: {'cache' if cached and not args.refresh else 'gọi'} · "
            f"{sc.error or f'{sum(sum(t.fields_ok.values()) for t in sc.tickets)}/{len(sc.tickets) * 8} trường đúng'}"
        )
        if not (cached and not args.refresh):
            time.sleep(args.delay)

    summary = summarize(scores)
    RESULTS.mkdir(parents=True, exist_ok=True)
    payload = {
        "model": model,
        "provider": settings.order_agent_provider,
        "run_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "decision_values": [d.value for d in ReviewDecision],
        "summary": summary,
        "samples": [
            {
                "id": s.sample_id,
                "kind": s.kind,
                "expected_tickets": s.expected_tickets,
                "predicted_tickets": s.predicted_tickets,
                "error": s.error,
                "latency_s": s.latency_s,
                "tickets": [{"fields_ok": t.fields_ok, "decision": t.decision} for t in s.tickets],
            }
            for s in scores
        ],
    }
    (RESULTS / f"{out}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n")
    (RESULTS / f"{out}.md").write_text(report_md(model, settings.order_agent_provider, summary, scores, answers))
    print(json.dumps(summary["all"], ensure_ascii=False))


if __name__ == "__main__":
    main()
