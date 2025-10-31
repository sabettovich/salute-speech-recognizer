import os
import wave
import sys
import time
import json
import typing as t
import grpc
from dotenv import load_dotenv
from salute_speech.speech_recognition import SaluteSpeechClient
import re
import string
from .dedup import apply_dedup, env_enabled

# Path to generated protobufs in the old repo
PROTO_DIR = "/home/sabet/myservs/myprjts/salute-speech_old/recognition/v1/python3"
if PROTO_DIR not in sys.path:
    sys.path.append(PROTO_DIR)

import recognition_pb2  # type: ignore
import recognition_pb2_grpc  # type: ignore
import storage_pb2  # type: ignore
import storage_pb2_grpc  # type: ignore
import task_pb2  # type: ignore
import task_pb2_grpc  # type: ignore


def _resolve_ca() -> t.Optional[bytes]:
    # Try env var first
    ca_path = os.getenv("SBER_CA_BUNDLE")
    if ca_path and os.path.exists(ca_path):
        with open(ca_path, "rb") as f:
            return f.read()
    # Try SalutSpeechPythonLib bundle
    candidates = [
        os.path.abspath(os.path.join(os.getcwd(), "..", "SalutSpeechPythonLib", "cacert.pem")),
        os.path.abspath(os.path.join(os.getcwd(), "SalutSpeechPythonLib", "cacert.pem")),
    ]
    for p in candidates:
        if os.path.exists(p):
            with open(p, "rb") as f:
                return f.read()
    return None


def _make_channel() -> grpc.Channel:
    # Build authenticated secure channel using SDK token
    from dotenv import load_dotenv
    load_dotenv()
    auth_key = os.getenv("SBER_SPEECH_AUTH_KEY") or os.getenv("SBER_SPEECH_API_KEY")
    if not auth_key:
        raise RuntimeError("Не найден SBER_SPEECH_AUTH_KEY (или SBER_SPEECH_API_KEY)")

    client = SaluteSpeechClient(client_credentials=auth_key)
    token = client.token_manager.get_valid_token()

    ca_bytes = _resolve_ca()
    ssl_cred = grpc.ssl_channel_credentials(root_certificates=ca_bytes)
    token_cred = grpc.access_token_call_credentials(token)
    return grpc.secure_channel(
        "smartspeech.sber.ru:443",
        grpc.composite_channel_credentials(ssl_cred, token_cred),
    )


def _sec_to_ts(sec: float) -> str:
    m = int(sec // 60)
    s = sec - m * 60
    return f"{m:02d}:{s:05.2f}"


def _build_markdown_from_json(data: dict) -> str:
    lines: list[str] = ["# Транскрипт", ""]
    duration = data.get("duration")
    language = data.get("language")
    if duration is not None:
        try:
            lines.append(f"- **Длительность**: {float(duration):.2f} c")
        except Exception:
            pass
    if language:
        lines.append(f"- **Язык**: {language}")
    lines.append("")

    segments = data.get("segments") or []
    if isinstance(segments, list):
        def _clean_text(txt: str) -> str:
            return " ".join((txt or "").lower().strip().split())

        def _token_set(s: str) -> set[str]:
            return set(_clean_text(s).split())

        def _jaccard(a: str, b: str) -> float:
            A, B = _token_set(a), _token_set(b)
            if not A or not B:
                return 0.0
            inter = len(A & B)
            union = len(A | B)
            return inter / union if union else 0.0

        def _contains_sim(a: str, b: str) -> bool:
            # true if shorter text fully contained in longer and lengths are close
            a1 = _clean_text(a)
            b1 = _clean_text(b)
            if not a1 or not b1:
                return False
            if len(a1) < len(b1):
                short, long = a1, b1
            else:
                short, long = b1, a1
            if short in long:
                ratio = len(short) / max(1, len(long))
                return ratio >= 0.75
            return False

        def _coverage(a: str, b: str) -> float:
            # min-coverage по словам, устойчива к перефразам
            A, B = _token_set(a), _token_set(b)
            if not A or not B:
                return 0.0
            inter = len(A & B)
            return min(inter / len(A), inter / len(B))

        def _overlap(a_start: float, a_end: float, b_start: float, b_end: float) -> float:
            try:
                left = max(float(a_start or 0), float(b_start or 0))
                right = min(float(a_end or 0), float(b_end or 0))
                inter = max(0.0, right - left)
                base = max(1e-6, max(float(a_end or 0) - float(a_start or 0), float(b_end or 0) - float(b_start or 0)))
                return inter / base
            except Exception:
                return 0.0

        # 1) Фильтрация пустых, speaker_id == -1
        prepared: list[dict] = []
        for s in segments:
            text = (s.get("text") or "").strip()
            if not text:
                continue
            sid = s.get("speaker_id") or s.get("speaker")
            if sid == -1:
                continue
            s2 = {
                "start": s.get("start"),
                "end": s.get("end"),
                "text": text,
                "speaker_id": s.get("speaker_id") or s.get("speaker"),
                "speaker_name": s.get("speaker_name"),
            }
            prepared.append(s2)

        # 2) Сортировка по старту и дедупликация по близости
        prepared.sort(key=lambda x: (float(x.get("start") or 0.0), float(x.get("end") or 0.0)))
        deduped: list[dict] = []
        for s in prepared:
            ctext = _clean_text(s["text"])
            sid = s.get("speaker_id")
            sname = s.get("speaker_name")
            def same_speaker(a: dict, b: dict) -> bool:
                an = a.get("speaker_name")
                bn = b.get("speaker_name")
                if an or bn:
                    return an == bn
                return a.get("speaker_id") == b.get("speaker_id")

            if deduped:
                last = deduped[-1]
                if same_speaker(last, s):
                    ov = _overlap(last.get("start"), last.get("end"), s.get("start"), s.get("end"))
                    close = abs(float(s.get("start") or 0) - float(last.get("start") or 0)) < 0.8
                    txt_same = _clean_text(last["text"]) == ctext
                    txt_contains = _contains_sim(last["text"], s["text"]) 
                    jac = _jaccard(last["text"], s["text"]) >= 0.6
                    cov = _coverage(last["text"], s["text"]) >= 0.7
                    # Считаем дублем при сильном времени (ov>0.7 или close<0.8s) и достаточной текстовой близости
                    if (ov > 0.7 or close) and (txt_same or txt_contains or jac or cov):
                        # keep более длинный
                        dur_last = float(last.get("end") or 0) - float(last.get("start") or 0)
                        dur_cur = float(s.get("end") or 0) - float(s.get("start") or 0)
                        if dur_cur > dur_last:
                            deduped[-1] = s
                        continue
            deduped.append(s)

        # 3) Рендер
        for s in deduped:
            start = s.get("start")
            end = s.get("end")
            text = s.get("text") or ""
            speaker = s.get("speaker_id")
            speaker_name = s.get("speaker_name")
            start_ts = _sec_to_ts(start) if isinstance(start, (int, float)) else "--:--.--"
            end_ts = _sec_to_ts(end) if isinstance(end, (int, float)) else "--:--.--"
            if speaker_name:
                lines.append(f"- [{start_ts} - {end_ts}] **{speaker_name}**: {text}")
            elif speaker is not None:
                lines.append(f"- [{start_ts} - {end_ts}] **Speaker {speaker}**: {text}")
            else:
                lines.append(f"- [{start_ts} - {end_ts}] {text}")
    else:
        text = data.get("text") or ""
        if text:
            lines.append(text)
    lines.append("")
    return "\n".join(lines)


def _parse_time_str(ts: t.Any) -> t.Optional[float]:
    if isinstance(ts, (int, float)):
        return float(ts)
    if isinstance(ts, str) and ts.endswith("s"):
        try:
            return float(ts[:-1])
        except Exception:
            return None
    return None


def _normalize_grpc_result(data: dict, hints: t.Optional[list[str]] = None) -> dict:
    # gRPC JSON may be a dict with key 'segments': list of entries each having 'results'[], 'speaker_info', 'processed_audio_start/end'
    segs = []
    raw_segments = data.get("segments") or []

    def _norm(s: str) -> str:
        return " ".join((s or "").lower().strip().split())

    hints_norm: list[str] = []
    if hints:
        seen = set()
        for h in hints:
            hn = _norm(h)
            if hn and hn not in seen:
                seen.add(hn)
                hints_norm.append(hn)

    def _score_by_hints(text: str) -> int:
        if not hints_norm:
            return 0
        tn = _norm(text)
        score = 0
        for h in hints_norm:
            if h and h in tn:
                score += 1
        return score

    for entry in raw_segments:
        results = entry.get("results") or []
        if not results:
            continue
        # Choose best hypothesis by hints coverage, fallback to first
        best = None
        best_score = -1
        for r in results:
            sc = _score_by_hints(r.get("normalized_text") or r.get("text") or "")
            if sc > best_score:
                best = r
                best_score = sc
        top = best or results[0]
        text = top.get("normalized_text") or top.get("text") or ""
        start = _parse_time_str(top.get("start")) or _parse_time_str(entry.get("processed_audio_start"))
        end = _parse_time_str(top.get("end")) or _parse_time_str(entry.get("processed_audio_end"))
        speaker = None
        si = entry.get("speaker_info") or {}
        if isinstance(si, dict):
            speaker = si.get("speaker_id")
        segs.append({
            "start": start,
            "end": end,
            "text": text,
            "speaker_id": speaker,
        })
    return {"segments": segs}


def _load_speaker_map(path: str) -> dict[str, str]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            m = json.load(f)
        if isinstance(m, dict):
            # keys: phrases (substrings) or regex keys starting with 're:'; values: speaker names
            return {str(k).strip(): str(v).strip() for k, v in m.items()}
    except Exception:
        pass
    return {}


def _apply_speaker_mapping(norm: dict, phrase_map: dict[str, str]) -> dict:
    if not phrase_map:
        return norm

    segs = norm.get("segments") or []
    if not isinstance(segs, list):
        return norm
    # Helpers
    tbl = str.maketrans('', '', string.punctuation + '«»—–‑“”„…')
    def norm_txt(s: str) -> str:
        s = (s or '').lower().strip()
        s = s.translate(tbl)
        s = ' '.join(s.split())
        return s

    regex_items: list[tuple[t.Pattern[str], str]] = []
    plain_items: list[tuple[str, str]] = []
    for k, v in phrase_map.items():
        if k.startswith('re:'):
            try:
                regex_items.append((re.compile(k[3:], re.IGNORECASE), v))
            except Exception:
                continue
        else:
            plain_items.append((norm_txt(k), v))

    # 1) Назначаем speaker_name по совпадению фраз (regex сперва, затем нормализованный contains)
    id_to_name: dict[int, str] = {}
    for s in segs:
        raw_text = s.get("text") or ""
        text_norm = norm_txt(raw_text)
        matched = False
        for rx, name in regex_items:
            if rx.search(raw_text):
                s["speaker_name"] = name
                sid = s.get("speaker_id")
                if isinstance(sid, int) and sid != -1 and sid not in id_to_name:
                    id_to_name[sid] = name
                matched = True
                break
        if matched:
            continue
        for phrase_norm, name in plain_items:
            if phrase_norm and phrase_norm in text_norm:
                s["speaker_name"] = name
                sid = s.get("speaker_id")
                if isinstance(sid, int) and sid != -1 and sid not in id_to_name:
                    id_to_name[sid] = name
                break
    # 2) Пропагируем имя на все сегменты с тем же speaker_id
    if id_to_name:
        for s in segs:
            sid = s.get("speaker_id")
            if isinstance(sid, int) and sid in id_to_name and not s.get("speaker_name"):
                s["speaker_name"] = id_to_name[sid]
    return norm


def _load_hints(path: str) -> list[str]:
    items: list[str] = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                w = line.strip()
                if w:
                    items.append(w)
    except Exception:
        pass
    # dedupe, preserve order
    seen: set[str] = set()
    out: list[str] = []
    for w in items:
        lw = w.lower()
        if lw in seen:
            continue
        seen.add(lw)
        out.append(w)
    return out


def grpc_async_transcribe(input_path: str, output_md_path: str, language: str = "ru-RU", diarization: bool = True) -> None:
    """Upload file via gRPC storage, create async recognition task, poll, download JSON, render MD."""
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Аудиофайл не найден: {input_path}")

    load_dotenv()
    auth_key = os.getenv("SBER_SPEECH_AUTH_KEY") or os.getenv("SBER_SPEECH_API_KEY")
    if not auth_key:
        raise RuntimeError("Не найден SBER_SPEECH_AUTH_KEY (или SBER_SPEECH_API_KEY)")

    # Get access token via SDK's token manager
    client = SaluteSpeechClient(client_credentials=auth_key)
    token = client.token_manager.get_valid_token()

    # Build channel creds
    ca_bytes = _resolve_ca()
    ssl_cred = grpc.ssl_channel_credentials(root_certificates=ca_bytes)
    token_cred = grpc.access_token_call_credentials(token)
    channel = grpc.secure_channel(
        "smartspeech.sber.ru:443",
        grpc.composite_channel_credentials(ssl_cred, token_cred),
    )

    recognition_stub = recognition_pb2_grpc.SmartSpeechStub(channel)
    storage_stub = storage_pb2_grpc.SmartSpeechStub(channel)
    task_stub = task_pb2_grpc.SmartSpeechStub(channel)

    # 1) Upload file
    CHUNK_SIZE = 8192

    def _gen_chunks():
        with open(input_path, "rb") as f:
            for data in iter(lambda: f.read(CHUNK_SIZE), b""):
                yield storage_pb2.UploadRequest(file_chunk=data)

    upload_resp = storage_stub.Upload(_gen_chunks())
    request_file_id = getattr(upload_resp, "request_file_id", None) or getattr(upload_resp, "requestFileId", None)
    if not request_file_id:
        raise RuntimeError(f"Не получен request_file_id из Upload ответа: {upload_resp}")

    # 2) Create async recognize task
    opts = recognition_pb2.RecognitionOptions()
    opts.language = language
    opts.model = "general"
    opts.hypotheses_count = 3
    # Detect encoding by extension
    ext = os.path.splitext(input_path)[1].lower()
    if ext == ".mp3":
        opts.audio_encoding = recognition_pb2.RecognitionOptions.MP3
        # crude channel guess
        opts.channels_count = 2
    elif ext in (".ogg", ".opus"):
        opts.audio_encoding = recognition_pb2.RecognitionOptions.OPUS
        opts.channels_count = 1
    elif ext == ".flac":
        opts.audio_encoding = recognition_pb2.RecognitionOptions.FLAC
    elif ext == ".wav":
        opts.audio_encoding = recognition_pb2.RecognitionOptions.PCM_S16LE
        # Try to read sample rate and channels from WAV header
        try:
            with wave.open(input_path, 'rb') as wf:
                opts.sample_rate = wf.getframerate()
                opts.channels_count = wf.getnchannels()
        except Exception:
            opts.sample_rate = 16000
            opts.channels_count = 1
    else:
        # Fallback assume MP3
        opts.audio_encoding = recognition_pb2.RecognitionOptions.MP3
    if diarization:
        opts.speaker_separation_options.enable = True
    # Recognition timeouts (best-effort, if supported by proto)
    try:
        opts.no_speech_timeout.seconds = 2
    except Exception:
        try:
            opts.no_speech_timeout = 2.0
        except Exception:
            pass
    try:
        opts.max_speech_timeout.seconds = 20
    except Exception:
        try:
            opts.max_speech_timeout = 20.0
        except Exception:
            pass
    try:
        opts.eou_timeout.seconds = 0
        opts.eou_timeout.nanos = int(0.6 * 1e9)
    except Exception:
        try:
            opts.eou_timeout = 0.6
        except Exception:
            pass
    # Load hints from file
    hints_path = os.getenv("HINTS_PATH") or os.path.join(os.getcwd(), "Source", "hints.txt")
    hints = _load_hints(hints_path)
    if hints:
        try:
            opts.hints.words.extend(hints)
            # Enable letters to help with редкие фамилии/аббревиатуры
            opts.hints.enable_letters = True
        except Exception:
            pass
    areq = recognition_pb2.AsyncRecognizeRequest(options=opts, request_file_id=request_file_id)
    task = recognition_stub.AsyncRecognize(areq)
    task_id = getattr(task, "id", None)
    if not task_id:
        raise RuntimeError(f"Не получен task id: {task}")

    # 3) Poll status
    SLEEP_TIME = 2.0
    while True:
        time.sleep(SLEEP_TIME)
        t = task_stub.GetTask(task_pb2.GetTaskRequest(task_id=task_id))
        if t.status == task_pb2.Task.NEW:
            continue
        elif t.status == task_pb2.Task.RUNNING:
            continue
        elif t.status == task_pb2.Task.CANCELED:
            raise RuntimeError("Task canceled")
        elif t.status == task_pb2.Task.ERROR:
            raise RuntimeError(f"Task failed: {t.error}")
        elif t.status == task_pb2.Task.DONE:
            response_file_id = getattr(t, "response_file_id", None)
            if not response_file_id:
                raise RuntimeError("Нет response_file_id у выполненной задачи")
            break

    # 4) Download result
    chunks = storage_stub.Download(storage_pb2.DownloadRequest(response_file_id=response_file_id))
    raw_bytes = b"".join(chunk.file_chunk for chunk in chunks)
    try:
        data = json.loads(raw_bytes.decode("utf-8"))
        if isinstance(data, list):
            data = {"segments": data}
    except Exception:
        data = {"raw": True, "bytes_len": len(raw_bytes)}

    # 5) Save raw and MD
    os.makedirs(os.path.dirname(os.path.abspath(output_md_path)), exist_ok=True)
    base = os.path.splitext(output_md_path)[0]
    raw_path = base + ".grpc.raw.json"
    with open(raw_path, "w", encoding="utf-8") as jf:
        json.dump(data, jf, ensure_ascii=False, indent=2)

    # Load hints early to use for n-best selection
    hints_path = os.path.join(os.getcwd(), "Source", "hints.txt")
    hints = _load_hints(hints_path)
    norm = _normalize_grpc_result(data, hints=hints)
    # Optional speaker mapping by phrases
    speakers_map_path = os.getenv("SPEAKERS_MAP_PATH") or os.path.join(os.getcwd(), "Source", "speakers_map.json")
    phrase_map = _load_speaker_map(speakers_map_path)
    norm = _apply_speaker_mapping(norm, phrase_map)
    norm_path = base + ".grpc.norm.json"
    with open(norm_path, "w", encoding="utf-8") as jf:
        json.dump(norm, jf, ensure_ascii=False, indent=2)

    if env_enabled():
        norm = apply_dedup(norm)
    md = _build_markdown_from_json(norm)
    with open(output_md_path, "w", encoding="utf-8") as f:
        f.write(md)
    return None


def grpc_recognize_to_objects(
    input_path: str,
    language: str = "ru-RU",
    diarization: bool = True,
    *,
    hints_path: t.Optional[str] = None,
    speakers_map_path: t.Optional[str] = None,
    hints: t.Optional[list[str]] = None,
    speakers_map: t.Optional[dict[str, str]] = None,
) -> tuple[dict, dict, str]:
    """
    Выполнить распознавание и вернуть кортеж:
    (raw_json, norm_json, markdown) — без записи на диск.
    Учитывает HINTS_PATH/SPEAKERS_MAP_PATH из окружения.
    """
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Аудиофайл не найден: {input_path}")

    # 1) Prepare stubs and upload (SmartSpeech stubs, same as grpc_async_transcribe)
    channel = _make_channel()
    recognition_stub = recognition_pb2_grpc.SmartSpeechStub(channel)
    storage_stub = storage_pb2_grpc.SmartSpeechStub(channel)
    task_stub = task_pb2_grpc.SmartSpeechStub(channel)

    CHUNK_SIZE = 8192
    def _gen_chunks():
        with open(input_path, "rb") as f:
            for data in iter(lambda: f.read(CHUNK_SIZE), b""):
                yield storage_pb2.UploadRequest(file_chunk=data)

    upload_resp = storage_stub.Upload(_gen_chunks())
    request_file_id = getattr(upload_resp, "request_file_id", None) or getattr(upload_resp, "requestFileId", None)
    if not request_file_id:
        raise RuntimeError(f"Не получен request_file_id из Upload ответа: {upload_resp}")

    # 2) Options
    opts = recognition_pb2.RecognitionOptions()
    opts.language = language
    opts.model = "general"
    opts.hypotheses_count = 3
    ext = os.path.splitext(input_path)[1].lower()
    if ext == ".mp3":
        opts.audio_encoding = recognition_pb2.RecognitionOptions.MP3
        opts.channels_count = 2
    elif ext in (".ogg", ".opus"):
        opts.audio_encoding = recognition_pb2.RecognitionOptions.OPUS
        opts.channels_count = 1
    elif ext == ".flac":
        opts.audio_encoding = recognition_pb2.RecognitionOptions.FLAC
        opts.channels_count = 1
    elif ext == ".wav":
        opts.audio_encoding = recognition_pb2.RecognitionOptions.PCM_S16LE
        try:
            import wave
            with wave.open(input_path, "rb") as wf:
                opts.sample_rate = wf.getframerate()
                opts.channels_count = wf.getnchannels()
        except Exception:
            opts.sample_rate = 16000
            opts.channels_count = 1
    else:
        opts.audio_encoding = recognition_pb2.RecognitionOptions.MP3
    if diarization:
        opts.speaker_separation_options.enable = True
    try:
        opts.no_speech_timeout.seconds = 2
    except Exception:
        try:
            opts.no_speech_timeout = 2.0
        except Exception:
            pass
    try:
        opts.max_speech_timeout.seconds = 20
    except Exception:
        try:
            opts.max_speech_timeout = 20.0
        except Exception:
            pass
    try:
        opts.eou_timeout.seconds = 0
        opts.eou_timeout.nanos = int(0.6 * 1e9)
    except Exception:
        try:
            opts.eou_timeout = 0.6
        except Exception:
            pass
    # Hints: precedence -> explicit list > explicit path > ENV > default file
    eff_hints: list[str] = []
    if hints is not None:
        eff_hints = list(hints)
    else:
        hp = hints_path or os.getenv("HINTS_PATH") or os.path.join(os.getcwd(), "Source", "hints.txt")
        eff_hints = _load_hints(hp)
    if eff_hints:
        try:
            opts.hints.words.extend(eff_hints)
            opts.hints.enable_letters = True
        except Exception:
            pass

    areq = recognition_pb2.AsyncRecognizeRequest(options=opts, request_file_id=request_file_id)
    task = recognition_stub.AsyncRecognize(areq)

    # 3) Poll via Task service
    task_id = getattr(task, "id", None)
    if not task_id:
        raise RuntimeError(f"Не получен task id: {task}")
    while True:
        time.sleep(2.0)
        t = task_stub.GetTask(task_pb2.GetTaskRequest(task_id=task_id))
        if t.status == task_pb2.Task.NEW:
            continue
        elif t.status == task_pb2.Task.RUNNING:
            continue
        elif t.status == task_pb2.Task.CANCELED:
            raise RuntimeError("Task canceled")
        elif t.status == task_pb2.Task.ERROR:
            raise RuntimeError(f"Task failed: {t.error}")
        elif t.status == task_pb2.Task.DONE:
            response_file_id = getattr(t, "response_file_id", None)
            if not response_file_id:
                raise RuntimeError("Нет response_file_id у выполненной задачи")
            break

    # 4) Download
    chunks = storage_stub.Download(storage_pb2.DownloadRequest(response_file_id=response_file_id))
    raw_bytes = b"".join(chunk.file_chunk for chunk in chunks)
    try:
        data = json.loads(raw_bytes.decode("utf-8"))
        if isinstance(data, list):
            data = {"segments": data}
    except Exception:
        data = {"raw": True, "bytes_len": len(raw_bytes)}

    # 5) Normalize/map and render
    norm = _normalize_grpc_result(data, hints=eff_hints)
    # Speakers map: precedence -> explicit dict > explicit path > ENV > default file
    if speakers_map is not None:
        phrase_map = speakers_map
    else:
        smp = speakers_map_path or os.getenv("SPEAKERS_MAP_PATH") or os.path.join(os.getcwd(), "Source", "speakers_map.json")
        phrase_map = _load_speaker_map(smp)
    norm = _apply_speaker_mapping(norm, phrase_map)
    if env_enabled():
        norm = apply_dedup(norm)
    md = _build_markdown_from_json(norm)
    return data, norm, md
