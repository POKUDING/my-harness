#!/usr/bin/env python3
"""Code review 보류/미해결 findings의 중앙 백로그 관리 도구.

Usage:
  backlog_tool.py add --review-json PATH [--only-major-plus]
  backlog_tool.py add-manual --file F --title T --severity S --category C [--note N] [--source-review R]
  backlog_tool.py list [--status X] [--severity X] [--file X] [--json]
  backlog_tool.py resolve BL_ID [--commit SHA] [--approach TEXT]
  backlog_tool.py dismiss BL_ID --reason TEXT
  backlog_tool.py stale-check
  backlog_tool.py import-all [--reviews-dir DIR]
  backlog_tool.py render-md
  backlog_tool.py stats

데이터는 .harness/review-backlog/ 하위에 저장:
  backlog.json   — 기계가 읽는 정본 (dedup_key 포함)
  backlog.md     — 사람이 읽는 버전 (자동 생성)
  resolved.json  — 해결된 항목 이력
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

BACKLOG_DIR = Path(".harness/review-backlog")
BACKLOG_JSON = BACKLOG_DIR / "backlog.json"
BACKLOG_MD = BACKLOG_DIR / "backlog.md"
RESOLVED_JSON = BACKLOG_DIR / "resolved.json"

SEVERITY_ORDER = {"critical": 0, "major": 1, "minor": 2, "nit": 3}
MAJOR_PLUS = {"critical", "major"}

# ---------- 기본 입출력 ----------

def _ensure_dir() -> None:
    BACKLOG_DIR.mkdir(parents=True, exist_ok=True)


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _today() -> str:
    return datetime.now().date().isoformat()


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"[backlog] WARN: {path} 파싱 실패 — 백업 후 초기화: {e}", file=sys.stderr)
        path.rename(path.with_suffix(path.suffix + f".broken.{int(datetime.now().timestamp())}"))
        return default


def _write_json(path: Path, data: Any) -> None:
    _ensure_dir()
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_backlog() -> dict:
    data = _read_json(BACKLOG_JSON, {"version": 1, "entries": []})
    data.setdefault("entries", [])
    return data


def save_backlog(data: dict) -> None:
    _write_json(BACKLOG_JSON, data)
    render_md(data)


def load_resolved() -> dict:
    return _read_json(RESOLVED_JSON, {"version": 1, "entries": []})


def save_resolved(data: dict) -> None:
    _write_json(RESOLVED_JSON, data)


# ---------- dedup key ----------

_KEYWORD_STOP = {
    "the", "a", "an", "of", "in", "on", "to", "for", "with", "by",
    "은", "는", "이", "가", "을", "를", "의", "에", "와", "과", "및",
    "하다", "되다", "있다", "없다",
}

def _norm_path(path: str) -> str:
    p = (path or "").strip().lower()
    # 절대 경로 → 상대 경로 정규화 시도
    if "/" in p:
        parts = p.split("/")
        # src/, app/, lib/ 등에서 끊기
        for anchor in ("src", "app", "lib", "server", "client", "frontend", "backend"):
            if anchor in parts:
                i = parts.index(anchor)
                p = "/".join(parts[i:])
                break
    return p


def _keywords(text: str, top: int = 6) -> list[str]:
    if not text:
        return []
    tokens = re.findall(r"[A-Za-z_][A-Za-z_0-9]{2,}|[가-힣]{2,}", text.lower())
    filtered = [t for t in tokens if t not in _KEYWORD_STOP]
    seen: list[str] = []
    for t in filtered:
        if t not in seen:
            seen.append(t)
        if len(seen) >= top:
            break
    return sorted(seen)


def compute_dedup_key(finding: dict) -> str:
    parts = [
        _norm_path(finding.get("file", "")),
        (finding.get("symbol") or "").strip(),
        (finding.get("category") or "").strip().lower(),
        " ".join(_keywords(finding.get("title", ""))),
    ]
    h = hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:12]
    return h


# ---------- ID 발급 ----------

def _next_id(data: dict) -> str:
    used = set()
    for e in data["entries"]:
        m = re.match(r"BL-(\d+)", e.get("id", ""))
        if m:
            used.add(int(m.group(1)))
    for e in load_resolved()["entries"]:
        m = re.match(r"BL-(\d+)", e.get("id", ""))
        if m:
            used.add(int(m.group(1)))
    n = 1
    while n in used:
        n += 1
    return f"BL-{n:03d}"


# ---------- add ----------

def _make_entry_from_finding(
    finding: dict,
    source_review: str | None,
    data: dict,
) -> dict:
    dedup = compute_dedup_key(finding)
    # 기존 엔트리 확인
    for e in data["entries"]:
        if e.get("dedup_key") == dedup and e.get("status") == "open":
            # 재발견 — occurrence_count 증가, last_seen·source_reviews 업데이트
            e["occurrence_count"] = e.get("occurrence_count", 1) + 1
            e["last_seen"] = _today()
            sources: list = e.setdefault("source_reviews", [])
            if source_review and source_review not in sources:
                sources.append(source_review)
            # severity가 올라간 경우 반영 (보수)
            old_sev = e.get("severity", "minor")
            new_sev = finding.get("severity", old_sev)
            if SEVERITY_ORDER.get(new_sev, 9) < SEVERITY_ORDER.get(old_sev, 9):
                e["severity"] = new_sev
            return e

    # 신규 엔트리
    entry = {
        "id": _next_id(data),
        "dedup_key": dedup,
        "status": "open",
        "first_seen": _today(),
        "last_seen": _today(),
        "occurrence_count": 1,
        "source_reviews": [source_review] if source_review else [],
        "severity": finding.get("severity", "minor"),
        "category": finding.get("category", ""),
        "scope": finding.get("scope", "followup"),
        "file": finding.get("file", ""),
        "symbol": finding.get("symbol"),
        "lines": finding.get("lines"),
        "title": finding.get("title", ""),
        "problem": finding.get("problem", ""),
        "why": finding.get("why"),
        "impact": finding.get("impact"),
        "recommendation": finding.get("recommendation", ""),
        "axis": finding.get("axis"),
        "note": None,
        "original_id": finding.get("id"),
    }
    data["entries"].append(entry)
    return entry


def cmd_add(args) -> int:
    review_path = Path(args.review_json)
    if not review_path.exists():
        print(f"[backlog] ERROR: {review_path} not found", file=sys.stderr)
        return 1
    review = _read_json(review_path, {})
    findings = review.get("findings", [])
    data = load_backlog()
    added = 0
    updated = 0
    for f in findings:
        if f.get("scope") != "followup":
            continue
        if args.only_major_plus and f.get("severity") not in MAJOR_PLUS:
            continue
        before_count = len(data["entries"])
        before_counts = {e["id"]: e.get("occurrence_count", 1) for e in data["entries"]}
        entry = _make_entry_from_finding(f, str(review_path), data)
        if len(data["entries"]) > before_count:
            added += 1
        elif entry["occurrence_count"] != before_counts.get(entry["id"], 1):
            updated += 1
    save_backlog(data)
    print(f"[backlog] added={added} updated={updated} total_open={_count_open(data)}")
    return 0


def cmd_add_manual(args) -> int:
    data = load_backlog()
    finding = {
        "file": args.file,
        "title": args.title,
        "severity": args.severity,
        "category": args.category,
        "scope": "followup",
        "problem": args.problem or args.title,
        "recommendation": args.recommendation or "",
        "symbol": args.symbol,
        "lines": args.lines,
    }
    entry = _make_entry_from_finding(finding, args.source_review, data)
    if args.note:
        entry["note"] = args.note
    save_backlog(data)
    print(f"[backlog] {entry['id']} added/updated (occurrence={entry['occurrence_count']})")
    return 0


# ---------- list ----------

def _match_filters(e: dict, args) -> bool:
    if args.status and e.get("status") != args.status:
        return False
    if args.severity and e.get("severity") != args.severity:
        return False
    if args.file and args.file not in (e.get("file") or ""):
        return False
    if args.category and e.get("category") != args.category:
        return False
    return True


def cmd_list(args) -> int:
    data = load_backlog()
    entries = [e for e in data["entries"] if _match_filters(e, args)]
    entries.sort(key=lambda e: (SEVERITY_ORDER.get(e.get("severity", "minor"), 9),
                                 -e.get("occurrence_count", 1),
                                 e.get("first_seen", "")))
    if args.json:
        print(json.dumps(entries, ensure_ascii=False, indent=2))
        return 0
    if not entries:
        print("[backlog] 조건에 맞는 항목이 없습니다.")
        return 0
    print(f"## 백로그 ({len(entries)}건)\n")
    for e in entries:
        occ = e.get("occurrence_count", 1)
        occ_flag = f" [재발견 {occ}회]" if occ > 1 else ""
        print(f"- **{e['id']}** [{e.get('severity')}/{e.get('category')}/{e.get('status')}]{occ_flag}")
        print(f"  `{e.get('file')}`" + (f" > `{e['symbol']}`" if e.get("symbol") else "")
              + (f" (lines {e['lines']})" if e.get("lines") else ""))
        print(f"  {e.get('title')}")
        if e.get("note"):
            print(f"  note: {e['note']}")
        print()
    return 0


# ---------- resolve / dismiss ----------

def _find_entry(data: dict, bl_id: str) -> dict | None:
    for e in data["entries"]:
        if e.get("id") == bl_id:
            return e
    return None


def cmd_resolve(args) -> int:
    data = load_backlog()
    entry = _find_entry(data, args.id)
    if not entry:
        print(f"[backlog] ERROR: {args.id} not found", file=sys.stderr)
        return 1
    entry["status"] = "resolved"
    entry["resolution"] = {
        "date": _today(),
        "commit": args.commit,
        "approach": args.approach,
    }
    resolved = load_resolved()
    resolved["entries"].append(entry)
    data["entries"] = [e for e in data["entries"] if e.get("id") != args.id]
    save_backlog(data)
    save_resolved(resolved)
    print(f"[backlog] {args.id} resolved")
    return 0


def cmd_dismiss(args) -> int:
    data = load_backlog()
    entry = _find_entry(data, args.id)
    if not entry:
        print(f"[backlog] ERROR: {args.id} not found", file=sys.stderr)
        return 1
    entry["status"] = "dismissed"
    entry["dismissal"] = {
        "date": _today(),
        "reason": args.reason,
    }
    save_backlog(data)
    print(f"[backlog] {args.id} dismissed — {args.reason}")
    return 0


# ---------- stale-check ----------

def cmd_stale_check(_args) -> int:
    data = load_backlog()
    changed = 0
    for e in data["entries"]:
        if e.get("status") != "open":
            continue
        file_path = Path(e.get("file", ""))
        if not file_path.exists():
            e["status"] = "stale"
            e["stale_reason"] = "file missing"
            e["stale_date"] = _today()
            changed += 1
            continue
        # symbol이 있으면 파일에서 존재 확인 (느슨한 grep)
        sym = e.get("symbol")
        if sym:
            try:
                text = file_path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            if sym not in text:
                e["stale_reason"] = f"symbol '{sym}' not found"
                e["stale_candidate"] = True
    save_backlog(data)
    print(f"[backlog] stale-check: marked_stale={changed}")
    return 0


# ---------- import-all ----------

def cmd_import_all(args) -> int:
    reviews_dir = Path(args.reviews_dir or ".harness/reviews")
    if not reviews_dir.exists():
        print(f"[backlog] ERROR: {reviews_dir} not found", file=sys.stderr)
        return 1
    data = load_backlog()
    total_added = 0
    total_updated = 0
    review_files = sorted(reviews_dir.glob("*/*review.json"))
    for rf in review_files:
        review = _read_json(rf, {})
        for f in review.get("findings", []):
            if f.get("scope") != "followup":
                continue
            if f.get("severity") not in MAJOR_PLUS:
                continue
            before_count = len(data["entries"])
            before_counts = {e["id"]: e.get("occurrence_count", 1) for e in data["entries"]}
            entry = _make_entry_from_finding(f, str(rf), data)
            if len(data["entries"]) > before_count:
                total_added += 1
            elif entry["occurrence_count"] != before_counts.get(entry["id"], 1):
                total_updated += 1
    save_backlog(data)
    print(f"[backlog] import-all: scanned={len(review_files)} added={total_added} updated={total_updated}")
    return 0


# ---------- render-md ----------

def _count_open(data: dict) -> int:
    return sum(1 for e in data["entries"] if e.get("status") == "open")


def render_md(data: dict | None = None) -> None:
    if data is None:
        data = load_backlog()
    resolved = load_resolved()
    open_items = [e for e in data["entries"] if e.get("status") == "open"]
    stale_items = [e for e in data["entries"] if e.get("status") == "stale"]
    dismissed_items = [e for e in data["entries"] if e.get("status") == "dismissed"]

    open_items.sort(key=lambda e: (SEVERITY_ORDER.get(e.get("severity", "minor"), 9),
                                    -e.get("occurrence_count", 1),
                                    e.get("first_seen", "")))

    lines: list[str] = []
    lines.append("# Code Review 보류 항목 트래커")
    lines.append("")
    lines.append(f"**최종 업데이트:** {_today()}")
    lines.append("")
    lines.append(f"**요약:** open {len(open_items)} · stale {len(stale_items)} · dismissed {len(dismissed_items)} · resolved {len(resolved['entries'])}")
    lines.append("")

    # 통계 (severity)
    from collections import Counter
    sev_count = Counter(e.get("severity", "minor") for e in open_items)
    cat_count = Counter(e.get("category", "") for e in open_items)
    lines.append("## 통계")
    lines.append("")
    lines.append("| Severity | 건수 |")
    lines.append("|----------|------|")
    for sev in ["critical", "major", "minor", "nit"]:
        lines.append(f"| {sev} | {sev_count.get(sev, 0)} |")
    lines.append("")
    lines.append("| Category | 건수 |")
    lines.append("|----------|------|")
    for cat, n in cat_count.most_common():
        lines.append(f"| {cat or '(미지정)'} | {n} |")
    lines.append("")

    if open_items:
        lines.append("## 미해결 (Open)")
        lines.append("")
        lines.append("| ID | Sev | Category | 재발견 | 파일 | 제목 | 첫 발견 |")
        lines.append("|----|-----|----------|--------|------|------|---------|")
        for e in open_items:
            occ = e.get("occurrence_count", 1)
            occ_disp = f"**{occ}x**" if occ > 1 else ""
            file_disp = e.get("file", "") + (f" > `{e['symbol']}`" if e.get("symbol") else "")
            note_suffix = f" · _{e['note']}_" if e.get("note") else ""
            lines.append(f"| {e['id']} | {e.get('severity')} | {e.get('category')} | {occ_disp} | `{file_disp}` | {e.get('title')}{note_suffix} | {e.get('first_seen')} |")
        lines.append("")

    if stale_items:
        lines.append("## Stale (코드 변경으로 더 이상 유효하지 않음)")
        lines.append("")
        for e in stale_items:
            lines.append(f"- **{e['id']}** `{e.get('file')}` — {e.get('title')} (사유: {e.get('stale_reason', 'unknown')}, {e.get('stale_date', '')})")
        lines.append("")

    if dismissed_items:
        lines.append("## Dismissed")
        lines.append("")
        for e in dismissed_items:
            r = (e.get("dismissal") or {}).get("reason", "")
            d = (e.get("dismissal") or {}).get("date", "")
            lines.append(f"- **{e['id']}** `{e.get('file')}` — {e.get('title')} (사유: {r}, {d})")
        lines.append("")

    if resolved["entries"]:
        lines.append("## 최근 해결 (Resolved, 최근 10건)")
        lines.append("")
        lines.append("| ID | Sev | 파일 | 제목 | 해결일 | 커밋 |")
        lines.append("|----|-----|------|------|--------|------|")
        recent = sorted(resolved["entries"],
                        key=lambda e: (e.get("resolution") or {}).get("date", ""),
                        reverse=True)[:10]
        for e in recent:
            res = e.get("resolution") or {}
            commit = res.get("commit") or ""
            commit_disp = commit[:8] if commit else "-"
            lines.append(f"| {e['id']} | {e.get('severity')} | `{e.get('file')}` | {e.get('title')} | {res.get('date', '')} | {commit_disp} |")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("관리 명령: `/review-backlog list` · `/review-backlog resolve BL-XXX` · `/review-backlog stale-check`")

    _ensure_dir()
    BACKLOG_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def cmd_render_md(_args) -> int:
    render_md()
    print(f"[backlog] rendered: {BACKLOG_MD}")
    return 0


# ---------- stats ----------

def cmd_stats(_args) -> int:
    data = load_backlog()
    resolved = load_resolved()
    open_items = [e for e in data["entries"] if e.get("status") == "open"]
    print(f"open={len(open_items)}")
    print(f"stale={sum(1 for e in data['entries'] if e.get('status') == 'stale')}")
    print(f"dismissed={sum(1 for e in data['entries'] if e.get('status') == 'dismissed')}")
    print(f"resolved_total={len(resolved['entries'])}")
    from collections import Counter
    sev = Counter(e.get("severity", "minor") for e in open_items)
    for s in ["critical", "major", "minor", "nit"]:
        print(f"open_{s}={sev.get(s, 0)}")
    return 0


# ---------- main ----------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    p_add = sub.add_parser("add", help="리뷰 JSON에서 followup 항목 append")
    p_add.add_argument("--review-json", required=True)
    p_add.add_argument("--only-major-plus", action="store_true", default=True)
    p_add.add_argument("--all-severity", dest="only_major_plus", action="store_false")
    p_add.set_defaults(func=cmd_add)

    p_man = sub.add_parser("add-manual", help="walk 등에서 수동으로 백로그 추가")
    p_man.add_argument("--file", required=True)
    p_man.add_argument("--title", required=True)
    p_man.add_argument("--severity", required=True, choices=list(SEVERITY_ORDER))
    p_man.add_argument("--category", required=True)
    p_man.add_argument("--problem", default="")
    p_man.add_argument("--recommendation", default="")
    p_man.add_argument("--symbol", default=None)
    p_man.add_argument("--lines", default=None)
    p_man.add_argument("--note", default=None)
    p_man.add_argument("--source-review", default=None)
    p_man.set_defaults(func=cmd_add_manual)

    p_list = sub.add_parser("list", help="백로그 조회")
    p_list.add_argument("--status", default=None)
    p_list.add_argument("--severity", default=None)
    p_list.add_argument("--file", default=None)
    p_list.add_argument("--category", default=None)
    p_list.add_argument("--json", action="store_true")
    p_list.set_defaults(func=cmd_list)

    p_res = sub.add_parser("resolve", help="항목 해결 처리")
    p_res.add_argument("id")
    p_res.add_argument("--commit", default=None)
    p_res.add_argument("--approach", default=None)
    p_res.set_defaults(func=cmd_resolve)

    p_dis = sub.add_parser("dismiss", help="항목 dismiss (won't fix)")
    p_dis.add_argument("id")
    p_dis.add_argument("--reason", required=True)
    p_dis.set_defaults(func=cmd_dismiss)

    p_st = sub.add_parser("stale-check", help="파일/심볼 존재 확인 후 stale 마킹")
    p_st.set_defaults(func=cmd_stale_check)

    p_imp = sub.add_parser("import-all", help="기존 .harness/reviews/ 전체 followup 수집")
    p_imp.add_argument("--reviews-dir", default=None)
    p_imp.set_defaults(func=cmd_import_all)

    p_md = sub.add_parser("render-md", help="backlog.md 재생성")
    p_md.set_defaults(func=cmd_render_md)

    p_sta = sub.add_parser("stats", help="요약 통계")
    p_sta.set_defaults(func=cmd_stats)

    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
