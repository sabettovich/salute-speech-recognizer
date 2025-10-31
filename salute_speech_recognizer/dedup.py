from __future__ import annotations
import os
import re
from difflib import SequenceMatcher
from typing import List, Dict, Any, Tuple


def _norm_text(t: str) -> str:
    t = t.lower().strip()
    t = re.sub(r"\s+", " ", t)
    return t


def _overlap(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    a0, a1 = a
    b0, b1 = b
    inter = max(0.0, min(a1, b1) - max(a0, b0))
    den = max(1e-9, min(a1 - a0, b1 - b0))
    return inter / den


def _sim(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def _speaker_id(seg: Dict[str, Any]) -> str:
    return str(seg.get("speaker") or seg.get("spk") or seg.get("speaker_label") or "")


def _tokens(s: str) -> List[str]:
    out: List[str] = []
    cur = []
    for ch in s.lower():
        if ch.isalnum() or ch in "_":
            cur.append(ch)
        else:
            if cur:
                out.append("".join(cur))
                cur = []
    if cur:
        out.append("".join(cur))
    return out


def _containment(a: str, b: str) -> float:
    # fraction of shorter's tokens contained in longer's tokens
    ta = set(_tokens(a))
    tb = set(_tokens(b))
    if not ta or not tb:
        return 0.0
    if len(ta) <= len(tb):
        short, long = ta, tb
    else:
        short, long = tb, ta
    inter = len(short & long)
    return inter / max(1, len(short))


def _best(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    # Prefer longer normalized text; tie-breaker: longer duration
    at = _norm_text(str(a.get("text") or ""))
    bt = _norm_text(str(b.get("text") or ""))
    if len(bt) > len(at):
        winner = b
    else:
        a_dur = float(a.get("end") or 0.0) - float(a.get("start") or 0.0)
        b_dur = float(b.get("end") or 0.0) - float(b.get("start") or 0.0)
        winner = b if b_dur > a_dur else a
    return winner


def apply_dedup(norm: Dict[str, Any], *, min_overlap: float = 0.6, min_text_sim: float = 0.85) -> Dict[str, Any]:
    if not isinstance(norm, dict):
        return norm
    segs = list(norm.get("segments") or [])
    if len(segs) < 2:
        return norm
    # Allow tuning via ENV
    try:
        mo = os.getenv("SSR_DEDUP_OVERLAP")
        if mo:
            min_overlap = float(mo)
        ms = os.getenv("SSR_DEDUP_SIM")
        if ms:
            min_text_sim = float(ms)
        max_shift = float(os.getenv("SSR_DEDUP_MAX_SHIFT") or 1e9)
        same_spk_only = (os.getenv("SSR_DEDUP_SAME_SPEAKER_ONLY") == "1")
        soft_mode = (os.getenv("SSR_DEDUP_SOFT") == "1")
        contain_thr = float(os.getenv("SSR_DEDUP_CONTAIN") or 0.0)
    except Exception:
        max_shift = 1e9
        same_spk_only = False
        soft_mode = False
        contain_thr = 0.0
    kept: List[Dict[str, Any]] = []
    for s in segs:
        t = _norm_text(str(s.get("text") or ""))
        if not t:
            continue
        s0 = float(s.get("start") or 0.0)
        s1 = float(s.get("end") or s0)
        replaced = False
        for i, k in enumerate(kept):
            k_t = _norm_text(str(k.get("text") or ""))
            if not k_t:
                continue
            ov = _overlap((s0, s1), (float(k.get("start") or 0.0), float(k.get("end") or 0.0)))
            if ov >= min_overlap:
                # extra safe checks
                # time shift constraint (midpoint)
                kmid = (float(k.get("start") or 0.0) + float(k.get("end") or 0.0)) / 2.0
                smid = (s0 + s1) / 2.0
                if abs(smid - kmid) > max_shift:
                    continue
                # same speaker constraint
                if same_spk_only and _speaker_id(s) != _speaker_id(k):
                    continue
                simv = _sim(t, k_t)
                if simv < min_text_sim:
                    continue
                if contain_thr > 0.0 and _containment(t, k_t) < contain_thr:
                    continue
                if soft_mode:
                    # mark as duplicate but keep both
                    try:
                        s.setdefault("_duplicate_of", {"start": k.get("start"), "end": k.get("end")})
                    except Exception:
                        pass
                    # do not replace/remove
                    continue
                # hard dedup: Choose best to keep
                winner = _best(k, s)
                if winner is not k:
                    kept[i] = s
                replaced = True
                break
        if not replaced:
            kept.append(s)
    out = dict(norm)
    out["segments"] = kept
    return out


def env_enabled() -> bool:
    return os.getenv("SSR_DEDUP", "1") != "0"
