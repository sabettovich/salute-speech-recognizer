from __future__ import annotations
import os
import sys
import argparse
import json
from typing import Optional
from importlib.metadata import version as _pkg_version, PackageNotFoundError

from .grpc_async import grpc_async_transcribe, grpc_recognize_to_objects
from .http_async import http_recognize_to_objects
from .audio_prep import prepare
from .strategy_selector import match_and_plan
from .chunked import transcribe_canonical_chunked
from .kb_log import log_success
from .audio_prep import probe


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
    # Resolve package version for --version flag
    try:
        _ver = _pkg_version("salute-speech-recognizer")
    except PackageNotFoundError:
        _ver = os.getenv("SSR_VERSION") or "0.0.0-dev"
    p = argparse.ArgumentParser(description="Salute Speech Recognizer CLI")
    p.add_argument('--version', action='version', version=f"%(prog)s {_ver}")
    p.add_argument('--input', required=True, help='Путь к аудиофайлу')
    p.add_argument('--output', default='Result/audio.md', help='Путь к Markdown-выводу')
    p.add_argument('--api', default='grpc', choices=['grpc','http'], help='API backend')
    p.add_argument('--language', default='ru-RU', help='Язык распознавания')
    p.add_argument('--hints', default=os.getenv('HINTS_PATH') or 'Source/hints.txt', help='Путь к hints.txt')
    p.add_argument('--speakers-map', dest='speakers_map', default=os.getenv('SPEAKERS_MAP_PATH') or 'Source/speakers_map.json', help='Путь к speakers_map.json')
    p.add_argument('--hypotheses', type=int, default=3, help='Количество гипотез (n-best)')
    p.add_argument('--timeouts', default='no_speech=2,eou=0.6,max_speech=20', help='Таймауты: no_speech=,eou=,max_speech=')
    p.add_argument('--prep-mode', default='canonical', choices=['canonical','vendor'], help='Режим подготовки аудио (canonical/vendor)')
    p.add_argument('--verbose', action='store_true', help='Подробные сообщения')
    p.add_argument('--smart', action='store_true', help='Включить адаптивный выбор стратегии (селектор кейсов)')
    p.add_argument('--no-dedup', action='store_true', help='Отключить дедупликацию сегментов (SSR_DEDUP=0)')
    args = p.parse_args()

    # Передаем пути к hints/speakers_map через ENV, т.к. модуль grpc_async их читает
    if args.hints:
        os.environ['HINTS_PATH'] = args.hints
    if args.speakers_map:
        os.environ['SPEAKERS_MAP_PATH'] = args.speakers_map
    if args.no_dedup:
        os.environ['SSR_DEDUP'] = '0'

    if args.smart:
        plan, explain = match_and_plan(args.input, verbose=args.verbose)
        if args.verbose:
            print("[smart] plan:", plan)
            print("[smart] explain:", json.dumps(explain, ensure_ascii=False, indent=2))
        prep_mode = str(plan.get('prep_mode') or 'canonical')
        # Apply dedup settings from plan to ENV
        dcfg = plan.get('dedup') or {}
        if isinstance(dcfg, dict):
            en = dcfg.get('enable')
            if en is not None:
                os.environ['SSR_DEDUP'] = '1' if en else '0'
            ov = dcfg.get('overlap')
            if ov is not None:
                os.environ['SSR_DEDUP_OVERLAP'] = str(ov)
            sm = dcfg.get('sim') or dcfg.get('similarity')
            if sm is not None:
                os.environ['SSR_DEDUP_SIM'] = str(sm)
            ms = dcfg.get('max_shift') or dcfg.get('max_time_shift')
            if ms is not None:
                os.environ['SSR_DEDUP_MAX_SHIFT'] = str(ms)
            sso = dcfg.get('same_speaker_only')
            if sso is not None:
                os.environ['SSR_DEDUP_SAME_SPEAKER_ONLY'] = '1' if sso else '0'
            cont = dcfg.get('contain') or dcfg.get('containment')
            if cont is not None:
                os.environ['SSR_DEDUP_CONTAIN'] = str(cont)
            soft = dcfg.get('soft')
            if soft is not None:
                os.environ['SSR_DEDUP_SOFT'] = '1' if soft else '0'
        chunk_cfg = plan.get('chunk') or {}
        chunk_seconds = int(chunk_cfg.get('seconds') or 0)
        # Apply HTTP vendor body toggle if requested by plan
        tcfg = plan.get('transport') or {}
        if bool(tcfg.get('http_body_vendor')):
            os.environ['SSR_HTTP_BODY_VENDOR'] = '1'
        # Если план подразумевает чанки — используем канонический chunked пайплайн
        if chunk_seconds > 0:
            transcribe_canonical_chunked(args.input, args.output, language=args.language, chunk_seconds=chunk_seconds, verbose=args.verbose)
            # log success of smart-chunked plan
            try:
                log_success(args.input, args.output, plan, explain)
            except Exception:
                pass
            return
        # Иначе — обычный путь через выбранный API с подготовкой
        pa = prepare(args.input, mode=prep_mode, allow_vendor_fallback=True, verbose=args.verbose)
        if args.api == 'grpc':
            grpc_async_transcribe(pa.normalized_path, args.output, language=args.language, diarization=True)
        elif args.api == 'http':
            raw, norm, md = http_recognize_to_objects(pa.normalized_path, language=args.language, diarization=True)
            os.makedirs(os.path.dirname(args.output), exist_ok=True)
            with open(args.output, 'w', encoding='utf-8') as f:
                f.write(md)
        else:
            print(f"API {args.api} не поддержан", file=sys.stderr)
            sys.exit(2)
        # log success of smart non-chunked plan
        try:
            log_success(args.input, args.output, plan, explain)
        except Exception:
            pass
        return
    else:
        # Подготовка аудио (канонический или vendor режим) с возможным fallback
        pa = prepare(args.input, mode=args.prep_mode, allow_vendor_fallback=True, verbose=args.verbose)
        if args.verbose:
            print(f"[cli] using file: {pa.normalized_path}")
        # Особая стратегия для vendor: сначала gRPC, при ошибке — HTTP
        if args.prep_mode == 'vendor':
            try:
                grpc_async_transcribe(pa.normalized_path, args.output, language=args.language, diarization=True)
                # success via grpc
                plan = {
                    "prep_mode": "vendor",
                    "transport": {"primary": "grpc_async", "fallback": "http_async"},
                    "chunk": {"seconds": 0},
                }
                explain = {"meta": probe(args.input), "chosen_case": None, "priority": None}
                try:
                    log_success(args.input, args.output, plan, explain)
                except Exception:
                    pass
            except Exception as e:
                if args.verbose:
                    print(f"[vendor] gRPC failed, fallback to HTTP: {e}")
                raw, norm, md = http_recognize_to_objects(pa.normalized_path, language=args.language, diarization=True)
                os.makedirs(os.path.dirname(args.output), exist_ok=True)
                with open(args.output, 'w', encoding='utf-8') as f:
                    f.write(md)
                # success via http fallback
                plan = {
                    "prep_mode": "vendor",
                    "transport": {"primary": "grpc_async", "fallback": "http_async"},
                    "chunk": {"seconds": 0},
                }
                explain = {"meta": probe(args.input), "chosen_case": None, "priority": None}
                try:
                    log_success(args.input, args.output, plan, explain)
                except Exception:
                    pass
        else:
            if args.api == 'grpc':
                grpc_async_transcribe(pa.normalized_path, args.output, language=args.language, diarization=True)
                plan = {"prep_mode": args.prep_mode, "transport": {"primary": "grpc_async", "fallback": None}, "chunk": {"seconds": 0}}
                explain = {"meta": probe(args.input), "chosen_case": None, "priority": None}
                try:
                    log_success(args.input, args.output, plan, explain)
                except Exception:
                    pass
            elif args.api == 'http':
                raw, norm, md = http_recognize_to_objects(pa.normalized_path, language=args.language, diarization=True)
                os.makedirs(os.path.dirname(args.output), exist_ok=True)
                with open(args.output, 'w', encoding='utf-8') as f:
                    f.write(md)
                plan = {"prep_mode": args.prep_mode, "transport": {"primary": "http_async", "fallback": None}, "chunk": {"seconds": 0}}
                explain = {"meta": probe(args.input), "chosen_case": None, "priority": None}
                try:
                    log_success(args.input, args.output, plan, explain)
                except Exception:
                    pass
            else:
                print(f"API {args.api} не поддержан", file=sys.stderr)
                sys.exit(2)


if __name__ == '__main__':
    main()
