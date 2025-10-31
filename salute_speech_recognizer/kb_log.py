from __future__ import annotations
import os
import csv
import time
import yaml
from pathlib import Path
from typing import Any, Dict

KB_DIR = Path("docs/KB")
CASES_DIR = KB_DIR / "cases"
CASE_STATS = KB_DIR / "case_stats.yml"
SUCCESS_LOG = KB_DIR / "success_log.csv"


def _ensure_files() -> None:
    KB_DIR.mkdir(parents=True, exist_ok=True)
    CASES_DIR.mkdir(parents=True, exist_ok=True)
    if not CASE_STATS.exists():
        CASE_STATS.write_text("{}\n", encoding="utf-8")
    if not SUCCESS_LOG.exists():
        SUCCESS_LOG.write_text("timestamp,input,output,case_id,priority,prep_mode,transport,chunk_seconds,duration,codec,sample_rate,channels\n", encoding="utf-8")


def _safe_load_yaml(p: Path) -> Dict[str, Any]:
    if not p.exists():
        return {}
    try:
        return yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def _safe_dump_yaml(p: Path, data: Dict[str, Any]) -> None:
    p.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")


def _suggest_case_filename(explain: Dict[str, Any]) -> Path:
    meta = explain.get("meta", {})
    fmt = str(meta.get("format") or "audio").lower()
    dur = float(meta.get("duration") or 0.0)
    # bucket duration to nearest minutes range
    if dur < 600:
        bucket = "lt10min"
    elif dur < 1200:
        bucket = "10to20min"
    else:
        bucket = "ge20min"
    return CASES_DIR / f"{fmt}_{bucket}_auto.yml"


def inc_case_stat(case_id: str) -> None:
    _ensure_files()
    stats = _safe_load_yaml(CASE_STATS)
    cur = int(stats.get(case_id) or 0)
    stats[case_id] = cur + 1
    _safe_dump_yaml(CASE_STATS, stats)


def append_success_log(input_path: str, output_path: str, plan: Dict[str, Any], explain: Dict[str, Any]) -> None:
    _ensure_files()
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    meta = explain.get("meta", {})
    row = [
        ts,
        os.path.abspath(input_path),
        os.path.abspath(output_path),
        explain.get("chosen_case") or "<unknown>",
        explain.get("priority") or "",
        plan.get("prep_mode") or "",
        f"{(plan.get('transport') or {}).get('primary','')}->{(plan.get('transport') or {}).get('fallback','')}",
        (plan.get("chunk") or {}).get("seconds", 0),
        meta.get("duration", ""),
        meta.get("codec_name", meta.get("codec", "")),
        meta.get("sample_rate", ""),
        meta.get("channels", ""),
    ]
    with SUCCESS_LOG.open("a", encoding="utf-8", newline="") as f:
        csv.writer(f).writerow(row)


def create_case_draft_if_missing(plan: Dict[str, Any], explain: Dict[str, Any]) -> Path | None:
    """If chosen_case is absent in KB, create a minimal draft from meta/plan."""
    _ensure_files()
    cid = explain.get("chosen_case")
    if cid:
        candidate = CASES_DIR / f"{cid}.yml"
        if candidate.exists():
            return None
    out = _suggest_case_filename(explain)
    meta = explain.get("meta", {})
    draft = {
        "id": cid or out.stem,
        "version": 1,
        "priority": explain.get("priority", 50),
        "match": {
            "codec": [meta.get("codec_name") or meta.get("codec") or "*"],
            "sample_rate": [meta.get("sample_rate")] if meta.get("sample_rate") else ["*"],
            "channels": [meta.get("channels")] if meta.get("channels") else ["*"],
            "duration": {"min": max(0, float(meta.get("duration") or 0.0) - 120), "max": float(meta.get("duration") or 0.0) + 120},
        },
        "strategy": plan,
        "explain": {
            "rationale": ["auto-generated from successful run"],
            "expected_outcome": {"quality": "readable_markdown"},
        },
        "notes": {"owner": "auto", "source": "auto-log"},
    }
    _safe_dump_yaml(out, draft)
    return out


def log_success(input_path: str, output_path: str, plan: Dict[str, Any], explain: Dict[str, Any]) -> None:
    try:
        cid = explain.get("chosen_case")
        if cid:
            inc_case_stat(cid)
        else:
            create_case_draft_if_missing(plan, explain)
        append_success_log(input_path, output_path, plan, explain)
    except Exception:
        # Never break main flow due to logging issues
        pass
