import os
import argparse
import pathlib

from salute_speech_recognizer.recognize import transcribe_file, transcribe_stereo_as_speakers
from salute_speech_recognizer.http_async import http_async_transcribe
from salute_speech_recognizer.grpc_async import grpc_async_transcribe


def main():
    parser = argparse.ArgumentParser(description="Transcribe an audio file with SaluteSpeech and output Markdown")
    parser.add_argument("--input", required=True, help="Путь к аудиофайлу (рекомендуется поместить в ./Source)")
    parser.add_argument("--output", help="Путь к .md (по умолчанию ./Result/<basename>.md)")
    parser.add_argument("--language", default="ru-RU", help="Язык (по умолчанию ru-RU)")
    parser.add_argument("--no-diarization", action="store_true", help="Отключить диаризацию")
    parser.add_argument("--stereo-as-speakers", action="store_true", help="Рассматривать левый/правый канал как отдельных спикеров")
    parser.add_argument("--api", choices=["sdk", "http", "grpc"], default="sdk", help="Режим API: sdk (по умолчанию), http (HTTP async) или grpc (gRPC async)")

    args = parser.parse_args()

    in_path = args.input
    if not os.path.isabs(in_path):
        in_path = os.path.abspath(in_path)

    base = pathlib.Path(in_path).stem
    default_out_dir = os.path.abspath(os.path.join(os.getcwd(), "Result"))
    if not os.path.exists(default_out_dir):
        os.makedirs(default_out_dir, exist_ok=True)

    out_path = args.output
    if out_path:
        if not os.path.isabs(out_path):
            out_path = os.path.abspath(out_path)
    else:
        out_path = os.path.join(default_out_dir, f"{base}.md")

    # Ensure Source directory exists as per requirement
    source_dir = os.path.abspath(os.path.join(os.getcwd(), "Source"))
    if not os.path.exists(source_dir):
        os.makedirs(source_dir, exist_ok=True)

    diarization = not args.__dict__.get("no_diarization", False)

    if args.__dict__.get("stereo_as_speakers", False):
        transcribe_stereo_as_speakers(in_path, out_path, language=args.language)
    else:
        if args.api == "http":
            http_async_transcribe(in_path, out_path, language=args.language, diarization=diarization)
        elif args.api == "grpc":
            grpc_async_transcribe(in_path, out_path, language=args.language, diarization=diarization)
        else:
            transcribe_file(in_path, out_path, language=args.language, diarization=diarization)
    print(f"Готово: {out_path}")


if __name__ == "__main__":
    main()
