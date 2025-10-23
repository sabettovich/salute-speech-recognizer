from __future__ import annotations
import os
import sys
import argparse
from typing import Optional

from .grpc_async import grpc_async_transcribe


def _parse_timeouts(s: Optional[str]) -> tuple[Optional[float], Optional[float], Optional[float]]:
    if not s:
        return None, None, None
    parts = dict()
    for item in s.split(','):
        if not item.strip():
            continue
        if '=' in item:
            k, v = item.split('=', 1)
            try:
                parts[k.strip()] = float(v.strip())
            except Exception:
                pass
    return parts.get('no_speech'), parts.get('eou'), parts.get('max_speech')


def main() -> None:
    p = argparse.ArgumentParser(description="Salute Speech Recognizer CLI")
    p.add_argument('--input', required=True, help='Путь к аудиофайлу')
    p.add_argument('--output', default='Result/audio.md', help='Путь к Markdown-выводу')
    p.add_argument('--api', default='grpc', choices=['grpc'], help='API backend')
    p.add_argument('--language', default='ru-RU', help='Язык распознавания')
    p.add_argument('--hints', default=os.getenv('HINTS_PATH') or 'Source/hints.txt', help='Путь к hints.txt')
    p.add_argument('--speakers-map', dest='speakers_map', default=os.getenv('SPEAKERS_MAP_PATH') or 'Source/speakers_map.json', help='Путь к speakers_map.json')
    p.add_argument('--hypotheses', type=int, default=3, help='Количество гипотез (n-best)')
    p.add_argument('--timeouts', default='no_speech=2,eou=0.6,max_speech=20', help='Таймауты: no_speech=,eou=,max_speech=')
    args = p.parse_args()

    # Передаем пути к hints/speakers_map через ENV, т.к. модуль grpc_async их читает
    if args.hints:
        os.environ['HINTS_PATH'] = args.hints
    if args.speakers_map:
        os.environ['SPEAKERS_MAP_PATH'] = args.speakers_map

    # Прямо сейчас таймауты/гипотезы настраиваются в grpc_async.py, здесь оставляем для будущего API
    # Вызов трансформации
    if args.api == 'grpc':
        grpc_async_transcribe(args.input, args.output, language=args.language, diarization=True)
    else:
        print(f"API {args.api} не поддержан", file=sys.stderr)
        sys.exit(2)


if __name__ == '__main__':
    main()
