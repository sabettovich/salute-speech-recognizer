#!/usr/bin/env python3
# coding: utf-8

import re
import sys
import json
import argparse
from typing import Dict, Tuple

# Safe domain-specific replacements for court/utility transcripts
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
    # Normalize amounts like "395 463 89" / "395 4636 рублей 89 копеек" -> "395 463,89 ₽"
    (r"(\d{1,3}(?:[ \u00A0]?\d{3})+)[^\d]{1,3}(\d{2})\s*(?:руб\w*|₽)?\s*(?:коп\w*)?", r"\1,\2 ₽"),
]

PROFILES = {
    "court": DEFAULT_RULES,
}


def apply_rules(text: str, profile: str = "court") -> Tuple[str, Dict[str, int]]:
    rules = PROFILES.get(profile, [])
    stats: Dict[str, int] = {pat: 0 for pat, _ in rules}
    out = text
    for pat, rep in rules:
        new = re.sub(pat, rep, out, flags=re.IGNORECASE)
        if new != out:
            stats[pat] += 1
            out = new
    return out, {k: v for k, v in stats.items() if v > 0}


def main():
    ap = argparse.ArgumentParser(description="Apply safe postprocess rules to text.")
    ap.add_argument("--in", dest="inp", help="Input file (default: stdin)")
    ap.add_argument("--out", dest="out", help="Output file (default: stdout)")
    ap.add_argument("--profile", default="court", help="Profile name (default: court)")
    ap.add_argument("--report", help="Optional JSON report path with rule hit counts")
    args = ap.parse_args()

    data = sys.stdin.read() if not args.inp else open(args.inp, "r", encoding="utf-8", errors="ignore").read()
    result, stats = apply_rules(data, profile=args.profile)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(result)
    else:
        sys.stdout.write(result)

    if args.report:
        with open(args.report, "w", encoding="utf-8") as f:
            json.dump({"profile": args.profile, "rules_applied": stats}, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
