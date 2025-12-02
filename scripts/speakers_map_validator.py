#!/usr/bin/env python3
# coding: utf-8

import re
import json
import argparse
from pathlib import Path
from typing import Dict, Tuple, List

TS_SPEAKER_RE = re.compile(r'^- \[\d+:\d+\.\d+ - \d+:\d+\.\d+\] \*\*([^*]+)\*\*:')


def normalize_key(k: str) -> str:
    k = k.strip()
    m = re.match(r'(?i)^speaker\s*(\d+)$', k)
    if m:
        return f"Speaker {int(m.group(1))}"
    # try extract number anywhere
    m = re.search(r'(\d+)', k)
    if m:
        return f"Speaker {int(m.group(1))}"
    return k


def scan_md_speakers(md_path: Path) -> List[str]:
    speakers = []
    for line in md_path.read_text(encoding='utf-8', errors='ignore').splitlines():
        m = TS_SPEAKER_RE.match(line)
        if m:
            speakers.append(m.group(1).strip())
    return speakers


def main():
    ap = argparse.ArgumentParser(description='Validate and normalize speakers_map.json')
    ap.add_argument('--map', required=True, help='Path to speakers_map.json')
    ap.add_argument('--md', help='Optional MD file to validate presence of keys')
    ap.add_argument('--autofix', action='store_true', help='Rewrite JSON with normalized keys')
    ap.add_argument('--report', help='Optional JSON report output')
    args = ap.parse_args()

    p = Path(args.map)
    data = json.loads(p.read_text(encoding='utf-8'))
    if not isinstance(data, dict):
        raise SystemExit('speakers_map must be a JSON object')

    norm_map: Dict[str, str] = {}
    key_changes: Dict[str, str] = {}
    dup_conflicts: Dict[str, List[str]] = {}

    for k, v in data.items():
        nk = normalize_key(k)
        key_changes[k] = nk
        if nk in norm_map and norm_map[nk] != v:
            dup_conflicts.setdefault(nk, []).extend([norm_map[nk], v])
        norm_map[nk] = v

    md_speakers = []
    missing_in_map = []
    extra_in_map = []

    if args.md:
        for sp in scan_md_speakers(Path(args.md)):
            if sp.startswith('Speaker '):
                if sp not in norm_map:
                    missing_in_map.append(sp)
            # if already names (e.g., Судья, Лазарев) — не валидируем на карту
        # extras: keys like Speaker N not present in MD
        md_speaker_set = set(s for s in scan_md_speakers(Path(args.md)) if s.startswith('Speaker '))
        extra_in_map = [k for k in norm_map.keys() if k.startswith('Speaker ') and k not in md_speaker_set]

    report = {
        'original_count': len(data),
        'normalized_count': len(norm_map),
        'key_changes': key_changes,
        'dup_conflicts': dup_conflicts,
        'missing_in_map': missing_in_map,
        'extra_in_map': extra_in_map,
    }

    if dup_conflicts:
        # do not fail hard; just report
        pass

    if args.autofix:
        p.write_text(json.dumps(norm_map, ensure_ascii=False, indent=2), encoding='utf-8')

    if args.report:
        Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
