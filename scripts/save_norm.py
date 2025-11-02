#!/usr/bin/env python3
from __future__ import annotations
import os
import sys
from pathlib import Path
from salute_speech_recognizer.strategy_selector import match_and_plan
from salute_speech_recognizer.audio_prep import prepare
from salute_speech_recognizer.grpc_async import grpc_recognize_to_objects
from salute_speech_recognizer.http_async import http_recognize_to_objects
import json

def main():
    if len(sys.argv) < 3:
        print("Usage: save_norm.py <input_audio> <out_norm_json> [language]", file=sys.stderr)
        sys.exit(2)
    inp = Path(sys.argv[1])
    out = Path(sys.argv[2])
    lang = sys.argv[3] if len(sys.argv) > 3 else "ru-RU"

    plan, _ = match_and_plan(str(inp))
    pa = prepare(str(inp), mode=str(plan.get('prep_mode') or 'canonical'), allow_vendor_fallback=True)
    primary = (plan.get('transport') or {}).get('primary', 'grpc_async')

    if 'grpc' in primary:
        raw, norm, md = grpc_recognize_to_objects(pa.normalized_path, language=lang, diarization=True)
    else:
        raw, norm, md = http_recognize_to_objects(pa.normalized_path, language=lang, diarization=True)

    out.parent.mkdir(parents=True, exist_ok=True)
    # norm is a dict; persist as JSON text
    out.write_text(json.dumps(norm, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"Saved norm: {out}")

if __name__ == "__main__":
    main()
