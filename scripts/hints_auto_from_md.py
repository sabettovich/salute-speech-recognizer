#!/usr/bin/env python3
# coding: utf-8
from __future__ import annotations
import re
import argparse
from pathlib import Path
from typing import List, Iterable

STOP = {
 'и','в','во','на','по','с','со','к','о','об','от','до','за','для','что','это','тот','этот','как','где','когда','ли','же','но','а','ну','пожалуйста','из','над','под','у','при','не','нет','да','ни','или','то','уж','бы','были','был','есть','будет','было','быть','там','тут','здесь','вот','той','тот','этом','данный','данная','данные','номер','вопрос','ответ','скажите','подскажите','прошу','присаживаться'
}

# Regex utilities (borrowed from hints_extractor)
TS_LINE = re.compile(r"^- \[[0-9:\.]+\s-\s[0-9:\.]+\] ")
BOLD_ANY = re.compile(r"\*\*[^*]+\*\*:?\s*")
BR_TS_ANY = re.compile(r"\[[0-9:\.\s\-]+\]")
SPLIT_SENT = re.compile(r"[.!?…]+\s+")
PUNCT = re.compile(r"[\t,;:!\?\(\)\[\]\"'»«“”]+")
WS = re.compile(r"\s+")
CAP_RE = re.compile(r"^[А-ЯЁ][а-яё-]+$")

KEY_SUBSTR = [
  'суд', 'прокур', 'прист', 'исполн', 'уголов', 'административ', 'повест', 'заседан', 'мчс',
  'управляющ', 'слесар', 'сантех', 'теплов', 'узел', 'подвал', 'коридор', 'вскрыт', 'поисков',
  'спасател', 'владивост', 'океанск', 'район', 'приморск'
]


def _key(s: str) -> str:
    s = WS.sub(' ', s).strip()
    return s.casefold()


def norm_line(raw: str) -> str:
    s = TS_LINE.sub("", raw)
    s = BR_TS_ANY.sub(" ", s)
    s = BOLD_ANY.sub(" ", s)
    s = s.replace('<...>', ' ').replace('…', ' ')
    s = re.sub(r"[<>]", " ", s)
    s = PUNCT.sub(' ', s)
    s = WS.sub(' ', s).strip()
    return s


def tokens(s: str) -> List[str]:
    return [t for t in s.split(' ') if t]


def ngrams(seq: List[str], nmin: int, nmax: int, stride: int = 1) -> Iterable[List[str]]:
    L = len(seq)
    for n in range(nmin, min(nmax, L) + 1):
        i = 0
        while i <= L - n:
            yield seq[i:i+n]
            i += max(1, stride)


def useful(ng: List[str]) -> bool:
    if not any(len(t) >= 4 for t in ng):
        return False
    j = ' '.join(ng).lower()
    if any(sub in j for sub in KEY_SUBSTR):
        return True
    if any(CAP_RE.match(t) for t in ng):
        return True
    return False


def reduce_containment(items: List[str]) -> List[str]:
    norm = [(_key(s), s, len(s.split())) for s in items]
    norm.sort(key=lambda x: (-x[2], x[0]))
    kept_keys: List[str] = []
    kept_out: List[str] = []
    for k, orig, _ in norm:
        padk = f" {k} "
        if any(padk in f" {kk} " for kk in kept_keys):
            continue
        kept_keys.append(k)
        kept_out.append(orig)
    order = {s: i for i, s in enumerate(items)}
    kept_out.sort(key=lambda s: order.get(s, 10**9))
    return kept_out


def main() -> None:
    ap = argparse.ArgumentParser(description='Auto-extract ASR hints from machine MD (no "+" required)')
    ap.add_argument('--md', required=True)
    ap.add_argument('--output', required=True)
    ap.add_argument('--min', dest='nmin', type=int, default=2)
    ap.add_argument('--max', dest='nmax', type=int, default=4)
    ap.add_argument('--limit', type=int, default=100)
    ap.add_argument('--stride', type=int, default=2)
    ap.add_argument('--per-sent', type=int, default=2)
    args = ap.parse_args()

    txt = Path(args.md).read_text(encoding='utf-8', errors='ignore')
    items: List[str] = []
    seen: set[str] = set()
    for raw in txt.splitlines():
        line = norm_line(raw)
        if not line:
            continue
        # only process actual content lines (start with dash or letter)
        if not (line.startswith('- ') or line[:1].isalpha()):
            continue
        # split by sentences
        for sent in SPLIT_SENT.split(line):
            s = PUNCT.sub(' ', sent)
            s = WS.sub(' ', s).strip()
            if not s:
                continue
            toks_raw = tokens(s)
            # filter tokens
            toks = [t for t in toks_raw if (t.lower() not in STOP and not re.match(r"^[0-9]+([\.:][0-9]+)*$", t))]
            if len(toks) < args.nmin:
                continue
            # candidates for this sentence
            sent_cands: List[str] = []
            for ng in ngrams(toks, args.nmin, args.nmax, stride=max(1, args.stride)):
                if not useful(ng):
                    continue
                cand = ' '.join(ng)
                sent_cands.append(cand)
            if not sent_cands:
                continue
            sent_cands = reduce_containment(sent_cands)
            sent_cands.sort(key=lambda x: (-len(x.split()), x))
            kept = 0
            for c in sent_cands:
                k = _key(c)
                if k in seen:
                    continue
                seen.add(k)
                items.append(c)
                kept += 1
                if kept >= max(1, args.per_sent):
                    break
    # cap limit
    if args.limit and len(items) > args.limit:
        items = items[:args.limit]
    Path(args.output).write_text('\n'.join(items) + '\n', encoding='utf-8')
    print({"written": len(items), "path": args.output})


if __name__ == '__main__':
    main()
