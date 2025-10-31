from __future__ import annotations
import hashlib
import json
import os
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional, Tuple


@dataclass
class PreparedAudio:
    normalized_path: str
    duration_sec: Optional[float]
    original_meta: dict
    grpc_options: dict
    http_options: dict
    prep_mode: Literal["canonical", "vendor"]
    changed: bool


def _tmp_dir() -> Path:
    d = os.getenv("SSR_TMP_DIR") or os.path.join(os.getcwd(), "tmp")
    p = Path(d)
    p.mkdir(parents=True, exist_ok=True)
    return p


def _run(cmd: str) -> Tuple[int, str, str]:
    proc = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return proc.returncode, proc.stdout.decode("utf-8", "ignore"), proc.stderr.decode("utf-8", "ignore")


def probe(path: str) -> dict:
    cmd = (
        f"ffprobe -hide_banner -loglevel error -print_format json "
        f"-show_format -show_streams {shlex.quote(path)}"
    )
    code, out, err = _run(cmd)
    if code != 0:
        return {"error": err.strip(), "path": path}
    try:
        data = json.loads(out)
    except Exception:
        data = {"raw": out}
    # Extract primary audio stream fields
    meta = {
        "path": path,
        "format": (data.get("format") or {}).get("format_name"),
        "duration": float((data.get("format") or {}).get("duration") or 0.0) or None,
        "bit_rate": (data.get("format") or {}).get("bit_rate"),
        "codec_name": None,
        "sample_rate": None,
        "channels": None,
    }
    streams = data.get("streams") or []
    for s in streams:
        if s.get("codec_type") == "audio":
            meta["codec_name"] = s.get("codec_name")
            try:
                meta["sample_rate"] = int(s.get("sample_rate")) if s.get("sample_rate") else None
            except Exception:
                meta["sample_rate"] = None
            meta["channels"] = s.get("channels")
            break
    return meta


# Simplified vendor table gates. We don't re-encode if these are matched; else fallback.
# The exact mapping of codec/container to audio_encoding must follow vendor docs.
# We intentionally keep it conservative: only clear, common cases stay passthrough.
VENDOR_ENCODINGS = {
    # codec_name: (audio_encoding, allowed_sample_rates or None, allowed_channels or None)
    "mp3": ("MP3", None, None),
    "flac": ("FLAC", None, None),
    "opus": ("OPUS", None, None),
    "pcm_s16le": ("PCM_S16LE", None, None),
}


def _vendor_validate(meta: dict) -> Optional[Tuple[str, int, int]]:
    codec = (meta.get("codec_name") or "").lower()
    sr = meta.get("sample_rate")
    ch = meta.get("channels")
    if codec in VENDOR_ENCODINGS:
        enc, allowed_sr, allowed_ch = VENDOR_ENCODINGS[codec]
        # If vendor allows any, skip checks; else enforce
        if (allowed_sr is not None and sr not in allowed_sr):
            return None
        if (allowed_ch is not None and ch not in allowed_ch):
            return None
        return enc, (int(sr) if sr else None), (int(ch) if ch else None)
    return None


def _hash_key(path: str, target_sig: str) -> str:
    st = os.stat(path)
    h = hashlib.sha256()
    h.update(os.path.abspath(path).encode())
    h.update(str(st.st_mtime_ns).encode())
    h.update(str(st.st_size).encode())
    h.update(target_sig.encode())
    return h.hexdigest()[:16]


def _normalize_to_wav_16k_mono(src: str) -> Tuple[str, dict]:
    tmp = _tmp_dir()
    sig = "wav_pcm_s16le_16000_mono"
    key = _hash_key(src, sig)
    dst = tmp / f"{key}.wav"
    if dst.exists():
        return str(dst), {"audio_encoding": "PCM_S16LE", "sample_rate": 16000, "channels_count": 1}
    cmd = (
        f"ffmpeg -hide_banner -loglevel error -y -i {shlex.quote(src)} "
        f"-ac 1 -ar 16000 -sample_fmt s16 -c:a pcm_s16le {shlex.quote(str(dst))}"
    )
    code, out, err = _run(cmd)
    if code != 0:
        raise RuntimeError(f"ffmpeg failed: {err.strip() or out}")
    return str(dst), {"audio_encoding": "PCM_S16LE", "sample_rate": 16000, "channels_count": 1}


def build_options_vendor(meta: dict) -> Tuple[dict, dict]:
    v = _vendor_validate(meta)
    if not v:
        raise ValueError("Input doesn't match vendor-supported profiles")
    enc, sr, ch = v
    grpc = {
        "audio_encoding": enc,
        "sample_rate": sr,
        "channels_count": ch,
    }
    http = grpc.copy()
    return grpc, http


def prepare(path: str, mode: Literal["canonical", "vendor"] = "canonical", *, allow_vendor_fallback: bool = True, verbose: bool = False) -> PreparedAudio:
    meta = probe(path)
    duration = meta.get("duration")
    if verbose:
        print(f"[prep] probe: codec={meta.get('codec_name')} sr={meta.get('sample_rate')} ch={meta.get('channels')} dur={duration}")
    if mode == "vendor":
        try:
            grpc_opts, http_opts = build_options_vendor(meta)
            if verbose:
                print(f"[prep] vendor passthrough: encoding={grpc_opts['audio_encoding']} sr={grpc_opts['sample_rate']} ch={grpc_opts['channels_count']}")
            return PreparedAudio(
                normalized_path=path,
                duration_sec=duration,
                original_meta=meta,
                grpc_options=grpc_opts,
                http_options=http_opts,
                prep_mode=mode,
                changed=False,
            )
        except Exception as e:
            if not allow_vendor_fallback:
                raise
            if verbose:
                print(f"[prep] vendor unsupported, fallback to canonical: {e}")
            # Fall through to canonical
    # canonical path
    norm_path, http_opts = _normalize_to_wav_16k_mono(path)
    grpc_opts = http_opts.copy()
    if verbose:
        print(f"[prep] canonical: -> {norm_path} encoding={grpc_opts['audio_encoding']} sr={grpc_opts['sample_rate']} ch={grpc_opts['channels_count']}")
    return PreparedAudio(
        normalized_path=norm_path,
        duration_sec=duration,
        original_meta=meta,
        grpc_options=grpc_opts,
        http_options=http_opts,
        prep_mode="canonical" if mode != "vendor" else mode,
        changed=(norm_path != path),
    )
