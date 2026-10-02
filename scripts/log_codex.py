#!/usr/bin/env python3
"""Collect prompts from local Codex Desktop/CLI session transcripts."""
import argparse
import hashlib
import json
import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path


def git(command: str) -> str:
    try:
        return subprocess.check_output(command, shell=True, text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return ""


def normalize_path(path: str) -> str:
    try:
        return os.path.normcase(os.path.normpath(str(Path(path).resolve())))
    except OSError:
        return os.path.normcase(os.path.normpath(path))


def codex_home() -> Path:
    return Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))


def session_files(hours: int | None) -> list[Path]:
    directory = codex_home() / "sessions"
    if not directory.exists():
        return []
    cutoff = None if hours is None else datetime.now(timezone.utc) - timedelta(hours=hours)
    return sorted(
        (path for path in directory.rglob("rollout-*.jsonl")
         if not cutoff or datetime.fromtimestamp(path.stat().st_mtime, timezone.utc) >= cutoff),
        key=lambda path: path.stat().st_mtime,
    )


def read_json_lines(path: Path):
    try:
        with path.open(encoding="utf-8") as file:
            for line_number, line in enumerate(file, start=1):
                try:
                    yield line_number, json.loads(line)
                except json.JSONDecodeError:
                    continue
    except OSError:
        return


def session_matches_repo(path: Path, repo_root: Path) -> bool:
    target = normalize_path(str(repo_root))
    for _, record in read_json_lines(path):
        if record.get("type") == "session_meta":
            cwd = record.get("payload", {}).get("cwd", "")
            return bool(cwd) and normalize_path(cwd) == target
    return False


def extract_prompt(content: list[dict]) -> str:
    text = "\n".join(
        item.get("text", "") for item in content
        if item.get("type") in {"input_text", "text"} and item.get("text")
    ).strip()
    marker = "## My request:"
    if marker in text:
        text = text.split(marker, 1)[1].strip()
    return text[:1000]


def prompts_from_session(path: Path, repo_root: Path) -> list[dict]:
    if not session_matches_repo(path, repo_root):
        return []
    prompts = []
    for line_number, record in read_json_lines(path):
        payload = record.get("payload", {})
        if (record.get("type") != "response_item" or payload.get("type") != "message"
                or payload.get("role") != "user"):
            continue
        prompt = extract_prompt(payload.get("content", []))
        if not prompt:
            continue
        prompts.append({
            "entry_id": hashlib.sha256(f"{path}:{line_number}".encode()).hexdigest(),
            "ts": record.get("timestamp") or datetime.now(timezone.utc).isoformat(),
            "prompt": prompt,
            "session_id": path.stem.removeprefix("rollout-"),
        })
    return prompts


def logged_entry_ids(log_file: Path) -> set[str]:
    if not log_file.exists():
        return set()
    ids = set()
    with log_file.open(encoding="utf-8-sig") as file:
        for line in file:
            try:
                entry_id = json.loads(line).get("entry_id")
                if entry_id:
                    ids.add(entry_id)
            except json.JSONDecodeError:
                continue
    return ids


def make_entry(prompt: dict) -> dict:
    origin = git("git remote get-url origin")
    return {
        "entry_id": prompt["entry_id"], "ts": prompt["ts"], "tool": "codex",
        "event": "UserPromptSubmit", "session_id": prompt["session_id"], "model": "",
        "repo": origin.rstrip("/").split("/")[-1].removesuffix(".git"),
        "branch": git("git rev-parse --abbrev-ref HEAD"),
        "commit": git("git rev-parse --short HEAD"), "student": git("git config user.email"),
        "prompt": prompt["prompt"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Sweep Codex session prompts into .ai-log")
    scope = parser.add_mutually_exclusive_group()
    scope.add_argument("--all", action="store_true", help="Scan every local Codex session")
    scope.add_argument("--hours", type=int, default=24, help="Scan sessions updated in this window")
    parser.add_argument("--dry-run", action="store_true", help="Show count without writing")
    args = parser.parse_args()
    repo_root = Path(git("git rev-parse --show-toplevel") or Path.cwd()).resolve()
    log_dir = Path(os.environ.get("AI_LOG_DIR", ".ai-log"))
    if not log_dir.is_absolute():
        log_dir = repo_root / log_dir
    log_file = log_dir / "session.jsonl"
    hours = None if args.all else args.hours
    prompts = [prompt for path in session_files(hours) for prompt in prompts_from_session(path, repo_root)]
    seen = logged_entry_ids(log_file)
    new_prompts = [prompt for prompt in prompts if prompt["entry_id"] not in seen]
    if args.dry_run:
        print(f"[codex-log] DRY RUN — would log {len(new_prompts)} prompt(s).")
        return 0
    if not new_prompts:
        print("[codex-log] No new Codex prompts.")
        return 0
    log_dir.mkdir(parents=True, exist_ok=True)
    with log_file.open("a", encoding="utf-8") as file:
        for prompt in new_prompts:
            file.write(json.dumps(make_entry(prompt), ensure_ascii=False) + "\n")
    print(f"[codex-log] Logged {len(new_prompts)} prompt(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
