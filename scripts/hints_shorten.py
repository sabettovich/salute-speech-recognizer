#!/usr/bin/env python3
from __future__ import annotations
import re
import sys
import argparse
from pathlib import Path

STOP = {
 'и','в','во','на','по','с','со','к','о','об','от','до','за','для','что','это','тот','этот','как','где','когда','ли','же','но','а','ну','пожалуйста','из','над','под','у','при','не','нет','да','ни','или','то','уж','бы','были','был','есть','будет','было','быть','там','тут','здесь','вот','той','тот','этом','данный','данная','данные','номер','вопрос','ответ','скажите','подскажите','прошу','присаживаться'
}

PUNCT = re.compile(r"[\t,;:!\?\(\)\[\]\"'»«“”]+")
WS = re.compile(r"\s+")
TS = re.compile(r"^\+-? \[[^]]+\] ")
BOLD = re.compile(r"^\*\*[^*]+\*\*:?\s*")
ELL = re.compile(r"[<>]\.\.\.[<>]?")
ANG = re.compile(r"[<>]")

KEY_SUBSTR = [
  'суд', 'прокур', 'прист', 'исполн', 'уголов', 'административ', 'повест', 'заседан', 'мчс',
  'управляющ', 'слесар', 'сантех', 'теплов', 'узел', 'подвал', 'коридор', 'вскрыт', 'поисково',
  'спасател', 'владивост', 'океанск', 'район', 'приморск'
]

def norm_line(s: str) -> str:
    s = TS.sub("", s)
    s = s.lstrip('+').lstrip()
    s = BOLD.sub("", s)
    s = ELL.sub(" ", s)
    s = ANG.sub("", s)
    s = PUNCT.sub(" ", s)
    s = WS.sub(" ", s).strip()
    return s

def tokens(s: str) -> list[str]:
    if not s:
        return []
    return [t for t in s.split(' ') if t]

def is_cap(s: str) -> bool:
    return bool(re.match(r"^[А-ЯЁ][а-яё-]+$", s))

def ngrams(seq: list[str], nmin: int, nmax: int) -> list[list[str]]:
    out = []
    L = len(seq)
    for n in range(nmin, nmax+1):
        for i in range(0, max(0, L-n)+1):
            out.append(seq[i:i+n])
    return out

def useful(ng: list[str]) -> bool:
    j = " ".join(ng)
    jl = j.lower()
    if any(len(t) >= 4 for t in ng):
        pass
    else:
        return False
    if any(sub in jl for sub in KEY_SUBSTR):
        return True
    if any(is_cap(t) for t in ng):
        return True
    return False

def extract_from_truth(truth_md: Path, nmin: int = 2, nmax: int = 5) -> list[str]:
    res: list[str] = []
    seen: set[str] = set()
    for raw in truth_md.read_text(encoding='utf-8', errors='ignore').splitlines():
        if not raw.startswith('+'):
            continue
        line = norm_line(raw)
        if not line:
            continue
        toks = [t for t in tokens(line) if t.lower() not in STOP]
        if len(toks) < nmin:
            continue
        # capitalized multiword names
        caps: list[str] = []
        for t in tokens(line):
            if is_cap(t):
                caps.append(t)
            else:
                if len(caps) >= 2:
                    cand = " ".join(caps)
                    if cand not in seen:
                        seen.add(cand); res.append(cand)
                caps = []
        if len(caps) >= 2:
            cand = " ".join(caps)
            if cand not in seen:
                seen.add(cand); res.append(cand)
        for ng in ngrams(toks, nmin, min(nmax, len(toks))):
            if not useful(ng):
                continue
            cand = " ".join(ng)
            if cand not in seen:
                seen.add(cand)
                res.append(cand)
    return res

def load_set(p: Path) -> tuple[list[str], set[str]]:
    lines = [WS.sub(' ', l.strip()) for l in p.read_text(encoding='utf-8', errors='ignore').splitlines() if l.strip()]
    s = set(lines)
    return lines, s

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--truth', required=True)
    ap.add_argument('--hints', required=True)
    ap.add_argument('--min', dest='nmin', type=int, default=2)
    ap.add_argument('--max', dest='nmax', type=int, default=5)
    args = ap.parse_args()

    truth = Path(args.truth)
    hints = Path(args.hints)
    exist_list, exist_set = load_set(hints)
    cands = extract_from_truth(truth, args.nmin, args.nmax)
    added: list[str] = []
    for c in cands:
        if c not in exist_set:
            exist_set.add(c)
            added.append(c)
            exist_list.append(c)
    hints.write_text("\n".join(exist_list) + "\n", encoding='utf-8')
    print({"added": len(added), "total": len(exist_list)})

if __name__ == '__main__':
    main()
