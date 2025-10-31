#!/usr/bin/env python3
from __future__ import annotations
import sys
import json
from pathlib import Path

# Usage: python scripts/merge_norms_dedup.py <norm1.json> <norm2.json> <out_md> [<out_norm_json>]

def load_norm(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))

def save_json(p: Path, obj: dict) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")

def main():
    if len(sys.argv) < 4:
        print("Usage: merge_norms_dedup.py <norm1.json> <norm2.json> <out_md> [<out_norm_json>]")
        sys.exit(2)
    n1 = Path(sys.argv[1])
    n2 = Path(sys.argv[2])
    out_md = Path(sys.argv[3])
    out_norm = Path(sys.argv[4]) if len(sys.argv) > 4 else None

    d1 = load_norm(n1)
    d2 = load_norm(n2)

    segs = list(d1.get("segments") or []) + list(d2.get("segments") or [])
    segs = [s for s in segs if isinstance(s, dict) and s.get("text")]
    for s in segs:
        s["start"] = float(s.get("start") or 0.0)
        s["end"] = float(s.get("end") or s["start"])
    segs.sort(key=lambda s: (s["start"], s["end"]))

    merged = {
        "language": d1.get("language") or d2.get("language") or "ru-RU",
        "duration": max(float(d1.get("duration") or 0.0), float(d2.get("duration") or 0.0)),
        "segments": segs,
    }

    from salute_speech_recognizer.dedup import apply_dedup
    from salute_speech_recognizer.render import build_markdown_from_json

    before = len(merged["segments"])
    merged_dedup = apply_dedup(merged)
    after = len(merged_dedup.get("segments") or [])

    md = build_markdown_from_json(merged_dedup)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text(md, encoding="utf-8")

    if out_norm is not None:
        save_json(out_norm, merged_dedup)

    print(json.dumps({
        "segments_before": before,
        "segments_after": after,
        "out_md": str(out_md),
        "out_norm": str(out_norm) if out_norm else None,
    }, ensure_ascii=False))

if __name__ == "__main__":
    main()
