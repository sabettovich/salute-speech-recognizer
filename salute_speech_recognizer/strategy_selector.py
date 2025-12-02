from __future__ import annotations
import glob
import json
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import yaml  # type: ignore

from .audio_prep import probe


@dataclass
class Case:
    id: str
    match: Dict[str, Any]
    strategy: Dict[str, Any]
    scoring: Dict[str, Any]


def _load_yaml(path: str) -> Optional[dict]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except Exception:
        return None


def load_cases(root: Optional[str] = None) -> List[Case]:
    root = root or os.path.join(os.getcwd(), "docs", "KB", "cases")
    out: List[Case] = []
    for fp in sorted(glob.glob(os.path.join(root, "*.yml"))):
        data = _load_yaml(fp)
        if not isinstance(data, dict):
            continue
        cid = str(data.get("id") or os.path.splitext(os.path.basename(fp))[0])
        match = data.get("match") or {}
        strategy = data.get("strategy") or {}
        scoring = data.get("scoring") or {}
        out.append(Case(id=cid, match=match, strategy=strategy, scoring=scoring))
    return out


def _in_list_or_any(value: Any, allowed: Optional[List[Any]]) -> bool:
    if allowed is None:
        return True
    return value in allowed


def _match_case(meta: dict, c: Case) -> Tuple[bool, int, List[str]]:
    reasons: List[str] = []
    matched_fields = 0
    m = c.match or {}
    # codec
    codec = (meta.get("codec_name") or "").lower()
    allowed_codec = m.get("codec")
    if allowed_codec is not None:
        allowed_codec = [str(x).lower() for x in allowed_codec]
        if codec in allowed_codec:
            matched_fields += 1
            reasons.append(f"codec={codec}")
        else:
            return False, 0, []
    # sample_rate
    sr = meta.get("sample_rate")
    allowed_sr = m.get("sample_rate")
    if allowed_sr is not None:
        if sr in allowed_sr:
            matched_fields += 1
            reasons.append(f"sr={sr}")
        else:
            return False, 0, []
    # channels
    ch = meta.get("channels")
    allowed_ch = m.get("channels")
    if allowed_ch is not None:
        if ch in allowed_ch:
            matched_fields += 1
            reasons.append(f"ch={ch}")
        else:
            return False, 0, []
    # duration range (support both 'duration_sec' and legacy 'duration')
    dur = meta.get("duration")
    dur_cfg = {}
    if isinstance(m.get("duration_sec"), dict):
        dur_cfg = m.get("duration_sec") or {}
    elif isinstance(m.get("duration"), dict):
        dur_cfg = m.get("duration") or {}
    dmin = dur_cfg.get('min')
    dmax = dur_cfg.get('max')
    if dmin is not None and (dur is None or float(dur) < float(dmin)):
        return False, 0, []
    if dmax is not None and (dur is None or float(dur) > float(dmax)):
        return False, 0, []
    if dur_cfg:
        matched_fields += 1
        reasons.append(f"dur~{dmin}-{dmax}")
    return True, matched_fields, reasons


def match_and_plan(input_path: str, *, cases_dir: Optional[str] = None, verbose: bool = False) -> Tuple[dict, dict]:
    """
    Returns (plan, explain)
    plan example:
    {
      "prep_mode": "canonical",
      "transport": {"primary": "grpc_async", "fallback": "http_async_per_chunk"},
      "chunk": {"seconds": 120},
      "audio": {"encoding": "PCM_S16LE", "sample_rate": 16000, "channels_count": 1},
      "diarization": "service_only",
      "hints": {"enable": True}
    }
    explain example: {"meta": {...}, "chosen_case": "id", "reasons": [...], "priority": 80}
    """
    meta = probe(input_path)
    all_cases = load_cases(cases_dir)
    best: Optional[Tuple[Case, int, List[str]]] = None
    for c in all_cases:
        ok, spec, reasons = _match_case(meta, c)
        if not ok:
            continue
        prio = int((c.scoring or {}).get("priority", 0))
        score = (prio, spec)
        if best is None:
            best = (c, spec, reasons)
            best_score = score
        else:
            if score > best_score:  # type: ignore
                best = (c, spec, reasons)
                best_score = score
    if best is None:
        # default plan
        plan = {
            "prep_mode": "canonical",
            "transport": {"primary": "grpc_async", "fallback": "http_async_per_chunk"},
            "chunk": {"seconds": 300},
            "audio": {"encoding": "PCM_S16LE", "sample_rate": 16000, "channels_count": 1},
            "diarization": "service_only",
            "hints": {"enable": True},
            "dedup": {"enable": True, "overlap": 0.6, "sim": 0.85},
        }
        explain = {"meta": meta, "chosen_case": None, "reasons": ["default"], "priority": 0}
        return plan, explain
    case, spec, reasons = best
    plan = case.strategy or {}
    explain = {"meta": meta, "chosen_case": case.id, "reasons": reasons, "priority": int((case.scoring or {}).get("priority", 0))}
    return plan, explain
