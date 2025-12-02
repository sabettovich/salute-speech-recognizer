#!/usr/bin/env python3
# coding: utf-8
import argparse
from pathlib import Path
import re

def load(path: Path):
    return [re.sub(r"\s+"," ",x.strip()) for x in path.read_text(encoding='utf-8', errors='ignore').splitlines() if x.strip()]

def main():
    ap = argparse.ArgumentParser(description='Merge two hints lists with dedup (casefold), preserving order: A then B')
    ap.add_argument('--a', required=True, help='First list (base)')
    ap.add_argument('--b', required=True, help='Second list (append)')
    ap.add_argument('--out', required=True, help='Output file')
    args = ap.parse_args()
    A = Path(args.a); B = Path(args.b); O = Path(args.out)
    la = load(A); lb = load(B)
    seen=set(); out=[]
    for lst in (la, lb):
        for s in lst:
            k=s.casefold()
            if k in seen:
                continue
            seen.add(k); out.append(s)
    O.write_text('\n'.join(out)+'\n', encoding='utf-8')
    print({'a': len(la), 'b': len(lb), 'out': len(out), 'path': str(O)})

if __name__ == '__main__':
    main()
