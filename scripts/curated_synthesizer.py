#!/usr/bin/env python3
# coding: utf-8

import re
import json
import argparse
from pathlib import Path
from typing import List, Optional, Tuple, Dict

# Reuse simple safe regexes inline to avoid coupling; can be extended to import postprocess_rules
DEFAULT_RULES = [
    (r"первореченск[а-я]*\s+районн[а-я]*\s+суд", "Первореченский районный суд"),
    (r"совещат[а-я]*\s+комнат[а-я]*", "совещательная комната"),
    (r"частн[а-я]*\s+жалоб[а-я]*", "частная жалоба"),
    (r"приобщ[а-я]*\s+к\s+материал[а-я]*\s+дел[а-я]*", "приобщить к материалам дела"),
    (r"истребован[а-я]*\s+доказательств[а-я]*", "истребование доказательств"),
    (r"управляющ[а-я]*\s+компан[а-я]*", "управляющая компания"),
    (r"общедомов[а-я]*\s+имуществ[а-я]*", "общедомовое имущество"),
    (r"многоквартирн[а-я]*\s+дом", "многоквартирный дом"),
    (r"теплов[а-я]*\s+узл[а-я]*", "тепловой узел"),
    (r"секущ[а-я]*\s+вентил[а-я]*", "секущие вентили"),
    (r"запорн[а-я]*\s+вентил[а-я]*", "запорные вентили"),
    (r"(\d{1,3}(?:[ \u00A0]?\d{3})+)[^\d]{1,3}(\d{2})\s*(?:руб\w*|₽)?\s*(?:коп\w*)?", r"\1,\2 ₽"),
]

TS_RE = re.compile(r'^- \[(\d+):(\d+\.\d+) - (\d+):(\d+\.\d+)\] \*\*([^*]+)\*\*: ?(.*)$')


def to_sec(m: str, s: str) -> float:
    return int(m) * 60 + float(s)


class Seg:
    __slots__ = ("start", "end", "speaker", "text", "raw")
    def __init__(self, start: float, end: float, speaker: str, text: str, raw: Optional[str] = None):
        self.start, self.end, self.speaker, self.text, self.raw = start, end, speaker, text, raw


def parse_md(md_text: str) -> List[Seg]:
    segs: List[Seg] = []
    for line in md_text.splitlines():
        m = TS_RE.match(line)
        if m:
            s = to_sec(m.group(1), m.group(2))
            e = to_sec(m.group(3), m.group(4))
            sp = m.group(5).strip()
            tx = m.group(6).strip()
            segs.append(Seg(s, e, sp, tx, line))
    return segs


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def overlap(a1: float, a2: float, b1: float, b2: float) -> float:
    return max(0.0, min(a2, b2) - max(a1, b1))


def clean_text(t: str, rules=DEFAULT_RULES, stats: Optional[Dict[str,int]] = None) -> str:
    s = t
    for pat, rep in rules:
        new = re.sub(pat, rep, s, flags=re.IGNORECASE)
        if new != s:
            if stats is not None:
                stats[pat] = stats.get(pat, 0) + 1
            s = new
    return s


def fmt_ts(t: float) -> str:
    m = int(t // 60)
    s = t - 60 * m
    return f"{m:02d}:{s:05.2f}"


def main():
    ap = argparse.ArgumentParser(description="Curated synthesizer: truth skeleton + curated overrides + draft text with safe postprocessing.")
    ap.add_argument("--truth", required=True, help="Path to manual truth MD (skeleton of segments)")
    ap.add_argument("--draft", required=True, help="Path to draft MD (text source)")
    ap.add_argument("--curated", required=True, help="Path to curated blocks (MD with same segment format)")
    ap.add_argument("--out", required=True, help="Output MD path (final)")
    ap.add_argument("--report", help="Optional JSON report path")
    ap.add_argument("--tolerance-sec", type=float, default=0.30)
    ap.add_argument("--min-overlap", type=float, default=0.40, help="Min fraction of truth segment overlapped by draft to use draft text")
    args = ap.parse_args()

    truth_text = read_text(Path(args.truth))
    draft_text = read_text(Path(args.draft))
    curated_text = read_text(Path(args.curated))

    truth_segs = parse_md(truth_text)
    draft_segs = parse_md(draft_text)
    curated_segs = parse_md(curated_text)

    # Index curated by speaker
    cur_by_speaker: Dict[str, List[Seg]] = {}
    for s in curated_segs:
        cur_by_speaker.setdefault(s.speaker, []).append(s)
    for spk in cur_by_speaker:
        cur_by_speaker[spk].sort(key=lambda s: s.start)

    def find_curated(seg: Seg, tol: float) -> Optional[Seg]:
        lst = cur_by_speaker.get(seg.speaker)
        if not lst:
            return None
        for cs in lst:
            if abs(cs.start - seg.start) <= tol and abs(cs.end - seg.end) <= tol:
                return cs
        # overlap fallback >= 60%
        best, bestov = None, 0.0
        for cs in lst:
            o = overlap(seg.start, seg.end, cs.start, cs.end)
            if o > bestov:
                bestov, best = o, cs
        if best and bestov >= 0.60 * (seg.end - seg.start):
            return best
        return None

    # Prepare output
    rules_stats: Dict[str,int] = {}
    chosen: List[Seg] = []
    cnt_cur = cnt_draft = cnt_fb_truth = 0

    # Build header from truth (lines until first timestamp)
    header_lines: List[str] = []
    for line in truth_text.splitlines():
        if TS_RE.match(line):
            break
        header_lines.append(line)

    # For each truth segment, prefer curated override; else use draft overlaps with postprocessing; else fallback to truth text
    draft_segs.sort(key=lambda s: s.start)
    for seg in truth_segs:
        cur_rep = find_curated(seg, args.tolerance_sec)
        if cur_rep:
            chosen.append(Seg(seg.start, seg.end, seg.speaker, cur_rep.text))
            cnt_cur += 1
            continue
        # collect overlapping draft pieces
        buf: List[str] = []
        for s2 in draft_segs:
            if s2.end <= seg.start:
                continue
            if s2.start >= seg.end:
                break
            buf.append(s2.text)
        if buf:
            txt = clean_text(" ".join(buf).strip(), stats=rules_stats)
            chosen.append(Seg(seg.start, seg.end, seg.speaker, txt))
            cnt_draft += 1
        else:
            chosen.append(Seg(seg.start, seg.end, seg.speaker, seg.text))
            cnt_fb_truth += 1

    # Render output
    out_lines: List[str] = []
    out_lines.extend(header_lines)
    for s in chosen:
        out_lines.append(f"- [{fmt_ts(s.start)} - {fmt_ts(s.end)}] **{s.speaker}**: {s.text}")
    final_text = "\n".join(out_lines) + "\n"
    Path(args.out).write_text(final_text, encoding="utf-8")

    report = {
        "segments_total": len(truth_segs),
        "segments_from_curated": cnt_cur,
        "segments_from_draft_clean": cnt_draft,
        "segments_fallback_truth": cnt_fb_truth,
        "rules_applied": {k:v for k,v in rules_stats.items() if v>0},
        "params": {"tolerance_sec": args.tolerance_sec, "min_overlap": args.min_overlap},
        "out": args.out,
    }
    if args.report:
        Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
