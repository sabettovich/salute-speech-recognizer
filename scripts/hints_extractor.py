#!/usr/bin/env python3
# coding: utf-8
from __future__ import annotations
import re
import argparse
from pathlib import Path
from typing import Iterable, List

# Russian stop-words to avoid weak n-grams
STOP = {
 'и','в','во','на','по','с','со','к','о','об','от','до','за','для','что','это','тот','этот','как','где','когда','ли','же','но','а','ну','пожалуйста','из','над','под','у','при','не','нет','да','ни','или','то','уж','бы','были','был','есть','будет','было','быть','там','тут','здесь','вот','той','тот','этом','данный','данная','данные','номер','вопрос','ответ','скажите','подскажите','прошу','присаживаться'
}

# Regexes
TS = re.compile(r"^\+-?\s*\[[^]]+\]\s*")  # strip timestamps after leading +
BOLD = re.compile(r"^\*\*[^*]+\*\*:?\s*")   # strip bold speaker name prefix (leading)
BOLD_ANY = re.compile(r"\*\*[^*]+\*\*:?\s*")  # strip bold speaker name anywhere
BR_TS_ANY = re.compile(r"\[[0-9:\.\s\-]+\]")  # strip any inline [hh:mm.xx - hh:mm.xx]
SPLIT_SENT = re.compile(r"[.!?…]+\s+")         # sentence splitter
PUNCT = re.compile(r"[\t,;:!\?\(\)\[\]\"'»«“”]+")
WS = re.compile(r"\s+")

KEY_SUBSTR = [
  'суд', 'прокур', 'прист', 'исполн', 'уголов', 'административ', 'повест', 'заседан', 'мчс',
  'управляющ', 'слесар', 'сантех', 'теплов', 'узел', 'подвал', 'коридор', 'вскрыт', 'поисков',
  'спасател', 'владивост', 'океанск', 'район', 'приморск'
]

CAP_RE = re.compile(r"^[А-ЯЁ][а-яё-]+$")


def norm_line(raw: str) -> str:
    s = raw.lstrip('+').lstrip()
    s = TS.sub("", s)
    s = BOLD.sub("", s)
    s = BR_TS_ANY.sub(" ", s)
    s = BOLD_ANY.sub(" ", s)
    s = s.replace('<...>', ' ').replace('…', ' ')
    s = re.sub(r"[<>]", " ", s)
    s = PUNCT.sub(' ', s)
    s = WS.sub(' ', s).strip()
    return s


def split_sentences(s: str) -> List[str]:
    # split by sentence delimiters while keeping only non-empty parts
    parts = SPLIT_SENT.split(s)
    return [p.strip() for p in parts if p.strip()]


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
    # at least one token length>=4 to avoid very weak n-grams
    if not any(len(t) >= 4 for t in ng):
        return False
    j = ' '.join(ng)
    jl = j.lower()
    if any(sub in jl for sub in KEY_SUBSTR):
        return True
    if any(CAP_RE.match(t) for t in ng):
        return True
    return False


def _key(s: str) -> str:
    s = WS.sub(' ', s).strip()
    return s.casefold()


def extract_from_truth(truth_md: Path, nmin: int, nmax: int, stride: int = 1, per_sent: int = 2) -> List[str]:
    result: List[str] = []
    seen_keys: set[str] = set()
    txt = truth_md.read_text(encoding='utf-8', errors='ignore')
    for raw in txt.splitlines():
        if not raw.startswith('+'):
            continue
        line = norm_line(raw)
        if not line:
            continue
        # work strictly within sentence bounds
        for sent in split_sentences(line):
            # fully strip punctuation inside sentence again (safety)
            s = PUNCT.sub(' ', sent)
            s = WS.sub(' ', s).strip()
            if not s:
                continue
            def is_num_like(tok: str) -> bool:
                return bool(re.match(r"^[0-9]+([\.:][0-9]+)*$", tok))
            toks_raw = tokens(s)
            toks = [t for t in toks_raw if (t.lower() not in STOP and not is_num_like(t))]
            if len(toks) < nmin:
                continue
            # collect candidates for this sentence locally
            sent_cands: List[str] = []
            # collect multi-capitalized names (FIO etc.)
            caps: List[str] = []
            def flush_caps_local():
                if len(caps) >= 2:
                    cand = ' '.join(caps)
                    sent_cands.append(cand)
            for t in tokens(s):
                if CAP_RE.match(t):
                    caps.append(t)
                else:
                    flush_caps_local(); caps = []  # type: ignore
            flush_caps_local()
            # collect domain n-grams within the same sentence
            for ng in ngrams(toks, nmin, nmax, stride=stride):
                if not useful(ng):
                    continue
                cand = ' '.join(ng)
                sent_cands.append(cand)
            # reduce overlaps inside sentence
            if sent_cands:
                sent_cands = reduce_containment(sent_cands)
                # prefer longer phrases first
                sent_cands.sort(key=lambda x: (-len(x.split()), x))
                # keep up to per_sent unique by global seen_keys
                kept_local = 0
                for c in sent_cands:
                    k = _key(c)
                    if k in seen_keys:
                        continue
                    seen_keys.add(k)
                    result.append(c)
                    kept_local += 1
                    if kept_local >= max(1, per_sent):
                        break
    return result


def reduce_containment(items: List[str]) -> List[str]:
    # remove phrases that are contained inside longer ones
    norm = [(_key(s), s, len(s.split())) for s in items]
    # sort by descending length to prefer longer phrases first
    norm.sort(key=lambda x: (-x[2], x[0]))
    kept_keys: List[str] = []
    kept_out: List[str] = []
    for k, orig, _ in norm:
        padk = f" {k} "
        if any(padk in f" {kk} " for kk in kept_keys):
            continue
        kept_keys.append(k)
        kept_out.append(orig)
    # restore original order as in input list
    order = {s: i for i, s in enumerate(items)}
    kept_out.sort(key=lambda s: order.get(s, 10**9))
    return kept_out


def main() -> None:
    ap = argparse.ArgumentParser(description='Extract useful ASR hints from "+" lines of truth MD')
    ap.add_argument('--truth', required=True, help='Path to _истина_.md')
    ap.add_argument('--output', required=True, help='Path to hints.txt to write (replace)')
    ap.add_argument('--min', dest='nmin', type=int, default=2)
    ap.add_argument('--max', dest='nmax', type=int, default=4)
    ap.add_argument('--limit', type=int, default=180, help='Max number of hints to keep (top by order)')
    ap.add_argument('--stride', type=int, default=2, help='Stride for sliding n-grams (>=1)')
    ap.add_argument('--no-contain', action='store_true', help='Disable containment reduction')
    ap.add_argument('--per-sent', type=int, default=2, help='Max hints to keep per sentence after reduction')
    args = ap.parse_args()

    truth = Path(args.truth)
    out = Path(args.output)

    cands = extract_from_truth(truth, args.nmin, args.nmax, stride=max(1, args.stride), per_sent=max(1, args.per_sent))
    if not args.no_contain:
        cands = reduce_containment(cands)
    # cap to limit while preserving order
    if args.limit and len(cands) > args.limit:
        cands = cands[:args.limit]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text('\n'.join(cands) + '\n', encoding='utf-8')
    print({"written": len(cands), "path": str(out)})


if __name__ == '__main__':
    main()
