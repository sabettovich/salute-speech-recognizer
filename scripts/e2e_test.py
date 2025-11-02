#!/usr/bin/env python3
from __future__ import annotations
import os
import subprocess
import shlex
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
FIX = ROOT / "tests" / "fixtures"
GOLD = ROOT / "tests" / "golden"
RES = ROOT / "Result"
BIN = ROOT / "venv" / "bin" / "ssr"
NORMS = ROOT / "tests" / "norms"

CASES = [
    {
        "name": "short_smart",
        "input": FIX / "short.wav",
        "output": RES / "test_short_smart.md",
        "gold": GOLD / "short_smart.head.md",
        "args": ["--smart"],
        "mode": "cli",
        "norm": NORMS / "short.norm.json",
    },
    {
        "name": "aac_clip_smart",
        "input": FIX / "aac_clip90.aac",
        "output": RES / "test_aac_clip_smart.md",
        "gold": GOLD / "aac_clip_smart.head.md",
        "args": ["--smart"],
        "mode": "cli",
        "norm": NORMS / "aac_clip90.norm.json",
    },
    {
        "name": "h2n_pair_merged",
        "input": FIX / "SR_MS.wav",
        "input2": FIX / "SR_XY.wav",
        "output": RES / "test_h2n_merged.md",
        "gold": GOLD / "h2n_merged.head.md",
        "mode": "h2n",
        "norm": NORMS / "h2n_MS.norm.json",
        "norm2": NORMS / "h2n_XY.norm.json",
    },
    {
        "name": "aac_48000Hz_ch1_br63836_20s_smart",
        "input": FIX / "aac_48000Hz_ch1_br63836_20s.m4a",
        "output": RES / "test_aac_48000Hz_ch1_br63836_20s.md",
        "gold": GOLD / "aac_48000Hz_ch1_br63836_20s.head.md",
        "args": ["--smart"],
        "mode": "cli",
        "norm": NORMS / "aac_48000Hz_ch1_br63836_20s.norm.json",
    },
    {
        "name": "pcm_s24le_48000Hz_ch2_br2304000_20s_smart",
        "input": FIX / "pcm_s24le_48000Hz_ch2_br2304000_20s.wav",
        "output": RES / "test_pcm_s24le_48000Hz_ch2_br2304000_20s.md",
        "gold": GOLD / "pcm_s24le_48000Hz_ch2_br2304000_20s.head.md",
        "args": ["--smart"],
        "mode": "cli",
        "norm": NORMS / "pcm_s24le_48000Hz_ch2_br2304000_20s.norm.json",
    },
]


def head_text(p: Path, lines: int = 30) -> str:
    if not p.exists():
        return ""
    txt = p.read_text(encoding="utf-8", errors="ignore").splitlines()
    return "\n".join(txt[:lines]) + ("\n" if txt else "")


def run_case(case: dict, update: bool = False) -> tuple[str, bool, str]:
    name = case["name"]
    out = Path(case["output"]) 
    gold = Path(case["gold"]) 

    run_mode = os.getenv("E2E_MODE") or "online"
    mode = case.get("mode", "cli")
    if run_mode == "offline":
        # offline: rerender from pre-saved norm jsons
        norm = Path(case.get("norm") or "")
        norm2 = Path(case.get("norm2") or "")
        if mode == "h2n":
            if not (norm.exists() and norm2.exists()):
                return name, True, f"SKIP (offline norms missing: {norm} or {norm2})"
            # merge two norms via existing script
            cmd = [str(Path(sys.executable)), str(ROOT/"scripts"/"merge_norms_dedup.py"), str(norm), str(norm2), str(out)]
            subprocess.check_call(cmd, cwd=str(ROOT))
        else:
            if not norm.exists():
                return name, True, f"SKIP (offline norm missing: {norm})"
            # rerender from norm
            cmd = [str(Path(sys.executable)), str(ROOT/"scripts"/"rerender_from_norm.py"), str(norm), str(out)]
            subprocess.check_call(cmd, cwd=str(ROOT))
    elif mode == "cli":
        inp = Path(case["input"]) 
        if not inp.exists():
            return name, False, f"missing fixture: {inp}"
        out.parent.mkdir(parents=True, exist_ok=True)
        cmd = [str(BIN), *case.get("args", []), "--input", str(inp), "--output", str(out), "--language", "ru-RU"]
        subprocess.check_call(cmd, cwd=str(ROOT))
    elif mode == "h2n":
        inp1 = Path(case["input"]) 
        inp2 = Path(case["input2"]) 
        if not inp1.exists() or not inp2.exists():
            return name, False, f"missing fixture: {inp1} or {inp2}"
        out.parent.mkdir(parents=True, exist_ok=True)
        cmd = [str(Path(sys.executable)), str(ROOT/"scripts"/"h2n_pair_process.py"), str(inp1), str(inp2), str(out)]
        subprocess.check_call(cmd, cwd=str(ROOT))
    else:
        return name, False, f"unknown mode: {mode}"

    head = head_text(out, 30)
    if update or not gold.exists():
        gold.parent.mkdir(parents=True, exist_ok=True)
        gold.write_text(head, encoding="utf-8")
        return name, True, "updated golden"

    ok = (head == gold.read_text(encoding="utf-8"))
    return name, ok, ("ok" if ok else "mismatch with golden")


def main():
    update = os.getenv("E2E_UPDATE_GOLDEN") == "1"
    skip_online_fail = os.getenv("E2E_SKIP_ONLINE_FAIL") == "1"
    results = []
    for c in CASES:
        try:
            results.append(run_case(c, update))
        except subprocess.CalledProcessError as e:
            if skip_online_fail:
                results.append((c["name"], True, f"SKIP (online failed): {e}"))
            else:
                results.append((c["name"], False, f"subprocess failed: {e}"))
        except Exception as e:
            if skip_online_fail:
                results.append((c["name"], True, f"SKIP (error): {e}"))
            else:
                results.append((c["name"], False, f"error: {e}"))

    failed = [r for r in results if not r[1]]
    for name, ok, msg in results:
        print(f"[{name}] {'OK' if ok else 'FAIL'} - {msg}")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
