#!/usr/bin/env python3
from __future__ import annotations
import os
import sys
import subprocess
import time
from pathlib import Path
import glob

# Usage: python scripts/h2n_pair_process.py <in_ms> <in_xy> <out_md>
# Runs smart recognition on both files, finds their norm JSONs, merges with safe soft-dedup and renders MD.

SALUTE_BIN = str(Path("venv/bin/ssr").resolve())
ROOT = Path.cwd()
RESULT_DIR = ROOT / "Result"


def find_norm_for(stem: str) -> Path | None:
    pats = [str(RESULT_DIR / f"{stem}*.norm.json")]
    cands: list[Path] = []
    for pat in pats:
        for p in glob.glob(pat):
            cands.append(Path(p))
    if not cands:
        return None
    cands.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return cands[0]


def run_ssr(inp: Path, out_md: Path) -> None:
    out_md.parent.mkdir(parents=True, exist_ok=True)
    # Use smart selector (will pick chunked/fallback strategy per KB case)
    cmd = [SALUTE_BIN, "--smart", "--input", str(inp), "--output", str(out_md), "--language", "ru-RU"]
    subprocess.check_call(cmd, cwd=str(ROOT))


def main():
    if len(sys.argv) < 4:
        print("Usage: h2n_pair_process.py <in_ms> <in_xy> <out_md>")
        sys.exit(2)
    in_ms = Path(sys.argv[1])
    in_xy = Path(sys.argv[2])
    out_md = Path(sys.argv[3])

    # 1) run recognition for both
    ms_md = RESULT_DIR / f"{in_ms.stem}.md"
    xy_md = RESULT_DIR / f"{in_xy.stem}.md"
    run_ssr(in_ms, ms_md)
    run_ssr(in_xy, xy_md)

    # 2) find norm jsons
    ms_norm = find_norm_for(in_ms.stem)
    xy_norm = find_norm_for(in_xy.stem)
    if not ms_norm or not xy_norm:
        print(f"Could not locate norm jsons for {in_ms} or {in_xy}", file=sys.stderr)
        sys.exit(3)

    # 3) merge with safe soft-dedup profile
    env = os.environ.copy()
    env.setdefault("SSR_DEDUP_SIM", "0.9")
    env.setdefault("SSR_DEDUP_OVERLAP", "0.7")
    env.setdefault("SSR_DEDUP_MAX_SHIFT", "2.0")
    env.setdefault("SSR_DEDUP_SAME_SPEAKER_ONLY", "1")
    env.setdefault("SSR_DEDUP_CONTAIN", "0.9")
    env.setdefault("SSR_DEDUP_SOFT", "1")

    out_norm = out_md.with_suffix("")
    out_norm = Path(str(out_norm) + ".norm.json")

    merge_cmd = [sys.executable, str(ROOT / "scripts/merge_norms_dedup.py"), str(ms_norm), str(xy_norm), str(out_md), str(out_norm)]
    subprocess.check_call(merge_cmd, cwd=str(ROOT), env=env)

    print(f"Merged MD: {out_md}")
    print(f"Merged norm: {out_norm}")


if __name__ == "__main__":
    main()
