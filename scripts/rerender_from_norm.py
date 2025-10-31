#!/usr/bin/env python3
from __future__ import annotations
import os
import sys
import json
from pathlib import Path

# Usage: python scripts/rerender_from_norm.py <norm_json_path> <out_md_path>

def main():
    if len(sys.argv) < 3:
        print("Usage: rerender_from_norm.py <norm_json_path> <out_md_path>")
        sys.exit(2)
    norm_path = Path(sys.argv[1])
    out_md = Path(sys.argv[2])
    data = json.loads(norm_path.read_text(encoding="utf-8"))
    # Apply improved dedup with env overrides if present
    from salute_speech_recognizer.dedup import apply_dedup
    from salute_speech_recognizer.render import build_markdown_from_json

    before = len(data.get("segments") or [])
    # Tight thresholds can be set via env SSR_DEDUP_OVERLAP / SSR_DEDUP_SIM
    data2 = apply_dedup(data)
    after = len(data2.get("segments") or [])
    md = build_markdown_from_json(data2)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text(md, encoding="utf-8")
    print(json.dumps({"segments_before": before, "segments_after": after, "out": str(out_md)}, ensure_ascii=False))

if __name__ == "__main__":
    main()
