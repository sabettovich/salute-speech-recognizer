import os
import asyncio
from datetime import timedelta
from typing import Optional, List, Any, Tuple
from types import SimpleNamespace
from pydub import AudioSegment
import tempfile
import json

from dotenv import load_dotenv
from salute_speech.speech_recognition import SaluteSpeechClient, SpeechRecognitionConfig


def _sec_to_ts(sec: float) -> str:
    # Format seconds to mm:ss.ms
    td = timedelta(seconds=max(0.0, float(sec)))
    total_seconds = td.total_seconds()
    minutes = int(total_seconds // 60)
    seconds = total_seconds % 60
    return f"{minutes:02d}:{seconds:05.2f}"


def _ensure_dirs(path: str) -> None:
    d = os.path.dirname(os.path.abspath(path))
    if d and not os.path.exists(d):
        os.makedirs(d, exist_ok=True)


async def _transcribe_async(input_path: str, language: str, diarization: bool) -> object:
    load_dotenv()
    auth_key = os.getenv("SBER_SPEECH_AUTH_KEY") or os.getenv("SBER_SPEECH_API_KEY")
    if not auth_key:
        raise RuntimeError("Не найден SBER_SPEECH_AUTH_KEY (или SBER_SPEECH_API_KEY) в .env или окружении")

    client = SaluteSpeechClient(client_credentials=auth_key)

    config: Optional[SpeechRecognitionConfig] = None
    # Попытка включить диаризацию, если доступна на аккаунте
    if diarization:
        try:
            config = SpeechRecognitionConfig(
                # Прочие настройки можно добавить по мере необходимости
                hypotheses_count=1,
                speaker_separation_options={"enable": True}  # явная попытка включить диаризацию
            )
        except Exception:
            # Если конструктор/поле недоступно в текущей версии, оставим без конфига
            config = None

    with open(input_path, "rb") as f:
        try:
            result = await client.audio.transcriptions.create(
                file=f,
                language=language,
                config=config,
            )
        except Exception as e:
            # Повтор без конфига на случай, если сервис не принимает опции диаризации
            if config is not None:
                result = await client.audio.transcriptions.create(
                    file=f,
                    language=language,
                    config=None,
                )
            else:
                raise e

    return result


def _result_to_dict(result: object) -> dict:
    # Try best-effort conversion to dict for raw dump
    if hasattr(result, 'to_dict') and callable(getattr(result, 'to_dict')):
        try:
            return result.to_dict()  # type: ignore
        except Exception:
            pass
    d = {}
    for key in ('duration', 'language', 'text', 'status', 'task_id'):
        d[key] = getattr(result, key, None)
    segs = []
    for seg in getattr(result, 'segments', None) or []:
        segs.append({
            'id': getattr(seg, 'id', None),
            'start': getattr(seg, 'start', None),
            'end': getattr(seg, 'end', None),
            'text': getattr(seg, 'text', None),
            'speaker': getattr(seg, 'speaker', getattr(seg, 'speaker_id', None))
        })
    d['segments'] = segs
    return d


def _dedupe_segments(segments: List[Any]) -> List[Any]:
    # Deduplicate by rounded times and normalized text
    seen: set[Tuple[str, str, str]] = set()
    out: List[Any] = []
    for seg in segments:
        start = getattr(seg, 'start', None)
        end = getattr(seg, 'end', None)
        text = (getattr(seg, 'text', '') or '').strip()
        rs = f"{float(start):.2f}" if start is not None else ""
        re = f"{float(end):.2f}" if end is not None else ""
        key = (rs, re, text)
        if key in seen:
            continue
        seen.add(key)
        out.append(seg)
    return out


def _build_markdown(result: object) -> str:
    lines = []
    lines.append("# Транскрипт")
    try:
        duration = getattr(result, "duration", None)
        language = getattr(result, "language", None)
        if duration is not None:
            lines.append(f"\n- **Длительность**: {float(duration):.2f} c")
        if language:
            lines.append(f"- **Язык**: {language}")
    except Exception:
        pass

    segments = getattr(result, "segments", None) or []
    try:
        segments = _dedupe_segments(list(segments))
    except Exception:
        pass
    lines.append("")
    for seg in segments:
        start = getattr(seg, "start", None)
        end = getattr(seg, "end", None)
        text = getattr(seg, "text", "")
        speaker = getattr(seg, "speaker", None)
        if speaker is None:
            speaker = getattr(seg, "speaker_id", None)

        start_ts = _sec_to_ts(start) if start is not None else "--:--.--"
        end_ts = _sec_to_ts(end) if end is not None else "--:--.--"
        if speaker is not None:
            lines.append(f"- [{start_ts} - {end_ts}] **Speaker {speaker}**: {text}")
        else:
            lines.append(f"- [{start_ts} - {end_ts}] {text}")

    if not segments:
        # Фолбек: плоский текст
        text = getattr(result, "text", "")
        if text:
            lines.append(text)

    return "\n".join(lines) + "\n"


def transcribe_file(input_path: str, output_md_path: str, language: str = "ru-RU", diarization: bool = True) -> None:
    """
    Распознать речь из файла и сохранить результат в Markdown.
    """
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Аудиофайл не найден: {input_path}")

    result = asyncio.run(_transcribe_async(input_path, language, diarization))
    md = _build_markdown(result)

    _ensure_dirs(output_md_path)
    with open(output_md_path, "w", encoding="utf-8") as f:
        f.write(md)

    # Dump raw JSON for inspection
    try:
        raw_dict = _result_to_dict(result)
        raw_path = os.path.splitext(output_md_path)[0] + ".raw.json"
        with open(raw_path, "w", encoding="utf-8") as jf:
            json.dump(raw_dict, jf, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _dict_to_obj(d: dict) -> Any:
    seg_objs = [SimpleNamespace(**s) for s in d.get('segments', [])]
    return SimpleNamespace(
        duration=d.get('duration'),
        language=d.get('language'),
        text=d.get('text'),
        status=d.get('status'),
        task_id=d.get('task_id'),
        segments=seg_objs,
    )


def transcribe_stereo_as_speakers(input_path: str, output_md_path: str, language: str = "ru-RU") -> None:
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Аудиофайл не найден: {input_path}")

    audio = AudioSegment.from_file(input_path)
    if audio.channels < 2:
        # Один канал — обычная транскрипция
        return transcribe_file(input_path, output_md_path, language=language, diarization=False)

    left, right = audio.split_to_mono()
    left = left.set_channels(1).set_frame_rate(16000)
    right = right.set_channels(1).set_frame_rate(16000)

    with tempfile.TemporaryDirectory() as tmpd:
        left_path = os.path.join(tmpd, "left.wav")
        right_path = os.path.join(tmpd, "right.wav")
        left.export(left_path, format="wav")
        right.export(right_path, format="wav")

        # Распознаём отдельно без диаризации
        left_res = asyncio.run(_transcribe_async(left_path, language, diarization=False))
        right_res = asyncio.run(_transcribe_async(right_path, language, diarization=False))

    # Собираем объединённый результат
    left_dict = _result_to_dict(left_res)
    right_dict = _result_to_dict(right_res)

    segments = []
    for s in left_dict.get('segments', []) or []:
        s = dict(s)
        s['speaker'] = 1
        segments.append(s)
    for s in right_dict.get('segments', []) or []:
        s = dict(s)
        s['speaker'] = 2
        segments.append(s)

    # Сортируем по началу
    segments.sort(key=lambda s: (float(s.get('start') or 0.0), float(s.get('end') or 0.0)))

    combined = {
        'duration': max(left_dict.get('duration') or 0.0, right_dict.get('duration') or 0.0),
        'language': left_dict.get('language') or right_dict.get('language'),
        'text': None,
        'status': 'DONE',
        'task_id': None,
        'segments': segments,
    }

    # Markdown и JSON
    md = _build_markdown(_dict_to_obj(combined))
    _ensure_dirs(output_md_path)
    with open(output_md_path, "w", encoding="utf-8") as f:
        f.write(md)

    try:
        raw_path = os.path.splitext(output_md_path)[0] + ".raw.json"
        with open(raw_path, "w", encoding="utf-8") as jf:
            json.dump(combined, jf, ensure_ascii=False, indent=2)
    except Exception:
        pass


__all__ = ["transcribe_file", "transcribe_stereo_as_speakers"]
