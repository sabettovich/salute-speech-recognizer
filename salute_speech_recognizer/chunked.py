from __future__ import annotations
import math
import os
import shlex
import subprocess
from pathlib import Path
from typing import List, Tuple

from .audio_prep import prepare, _tmp_dir, probe
from .grpc_async import grpc_recognize_to_objects
from .http_async import http_recognize_to_objects
from .render import build_markdown_from_json
from .dedup import apply_dedup, env_enabled


def _run(cmd: str) -> Tuple[int, str, str]:
    proc = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return proc.returncode, proc.stdout.decode("utf-8", "ignore"), proc.stderr.decode("utf-8", "ignore")


def _sec_to_ts(sec: float) -> str:
    m = int(sec // 60)
    s = sec - m * 60
    return f"{m:02d}:{s:05.2f}"


def transcribe_canonical_chunked(
    input_path: str,
    output_md_path: str,
    *,
    language: str = "ru-RU",
    chunk_seconds: int = 300,
    verbose: bool = False,
) -> None:
    # 1) Prepare canonical WAV 16k mono
    pa = prepare(input_path, mode="canonical", allow_vendor_fallback=True, verbose=verbose)
    wav_path = pa.normalized_path
    meta = probe(wav_path)
    duration = float(meta.get("duration") or 0.0)
    if verbose:
        print(f"[chunked] source={wav_path} dur={duration:.2f}s, chunk={chunk_seconds}s")

    # 2) Split with ffmpeg into temp WAV chunks
    tmp = _tmp_dir()
    n_chunks = max(1, math.ceil(duration / max(1, chunk_seconds)))
    merged_segments: List[dict] = []

    for i in range(n_chunks):
        start = i * chunk_seconds
        end = min(duration, (i + 1) * chunk_seconds)
        dur = max(0.0, end - start)
        if dur <= 0.25:  # skip tiny tail
            continue
        chunk_file = tmp / f"chunk_{Path(wav_path).stem}_{i:04d}.wav"
        if not chunk_file.exists():
            cmd = (
                f"ffmpeg -hide_banner -loglevel error -y -ss {start:.3f} -t {dur:.3f} "
                f"-i {shlex.quote(wav_path)} -ac 1 -ar 16000 -sample_fmt s16 -c:a pcm_s16le {shlex.quote(str(chunk_file))}"
            )
            code, out, err = _run(cmd)
            if code != 0:
                raise RuntimeError(f"ffmpeg split failed at chunk {i}: {err or out}")
        if verbose:
            print(f"[chunked] recognize chunk {i+1}/{n_chunks} [{_sec_to_ts(start)} - {_sec_to_ts(end)}] -> {chunk_file}")

        # 3) Recognize chunk via gRPC, fallback to HTTP async on failure
        try:
            raw, norm, md = grpc_recognize_to_objects(
                input_path=str(chunk_file),
                language=language,
                diarization=True,
            )
        except Exception as e:
            if verbose:
                print(f"[chunked] gRPC failed on chunk {i+1}, fallback HTTP: {e}")
            raw, norm, md = http_recognize_to_objects(
                input_path=str(chunk_file),
                language=language,
                diarization=True,
            )
        segs = norm.get("segments") or []
        for s in segs:
            st = s.get("start")
            en = s.get("end")
            if isinstance(st, (int, float)):
                s["start"] = float(st) + start
            if isinstance(en, (int, float)):
                s["end"] = float(en) + start
            merged_segments.append(s)

    # 4) Merge and render
    merged_segments.sort(key=lambda s: (float(s.get("start") or 0.0), float(s.get("end") or 0.0)))
    norm_all = {
        "duration": duration,
        "language": language,
        "segments": merged_segments,
    }
    if env_enabled():
        norm_all = apply_dedup(norm_all)
    md_out = build_markdown_from_json(norm_all)

    out_path = Path(output_md_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(md_out, encoding="utf-8")

    # Save norm/debug sidecars
    base = out_path.with_suffix("")
    (base.with_suffix(".grpc.chunked.norm.json")).write_text(__import__('json').dumps(norm_all, ensure_ascii=False, indent=2), encoding="utf-8")
