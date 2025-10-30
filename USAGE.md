# Использование (CLI)

Базовая команда:
```bash
venv/bin/python ss_recognize.py --input <путь_к_аудио> --api grpc \
  --language ru-RU \
  --hints Source/hints.txt \
  --speakers-map Source/speakers_map.json \
  --output Result/out.md
```

## Аргументы

- `--input` — путь к аудиофайлу (`.mp3`, `.wav`, `.ogg/.opus`, `.flac`).
- `--api` — сейчас поддержан `grpc`.
- `--language` — язык распознавания (по умолчанию `ru-RU`).
- `--hints` — путь к `hints.txt` (один hint на строку).
- `--speakers-map` — путь к `speakers_map.json` (ключ → имя спикера, поддержка `re:`).
- `--output` — путь к результату Markdown (по умолчанию `Result/<имя>.md`).

Дополнительно (если поддерживаются в вашей сборке):
- `--hypotheses` — кол-во n-best гипотез (рекомендуется `3`).
- `--timeouts` — `no_speech=<сек>,eou=<сек>,max_speech=<сек>` (например, `no_speech=2,eou=0.6,max_speech=20`).

## Примеры

- Одиночный файл:
```bash
venv/bin/python ss_recognize.py --input Source/audio.mp3 --api grpc
```

- Пакетная обработка каталога `Source/`:
```bash
for f in Source/*.{mp3,wav,ogg,opus,flac}; do \
  [ -e "$f" ] || continue; \
  out="Result/$(basename "${f%.*}").md"; \
  venv/bin/python ss_recognize.py --input "$f" --output "$out" --api grpc \
    --hints Source/hints.txt --speakers-map Source/speakers_map.json; \
done
```

## Переменные окружения

- `SBER_SPEECH_AUTH_KEY` — ключ доступа к Салют Спич (обязательно).
- `SBER_CA_BUNDLE` — путь к кастомному CA (опционально).

## Длинные файлы и авто‑нарезка (рекомендуемый дефолт)

Для устойчивой обработки длинных записей используйте скрипт `ss_recognize.py` с режимом API=`sdk` и авто‑нарезкой.

- Авто‑фолбэк (сначала целиком, при ошибке — порезка и склейка):
```bash
venv/bin/python ss_recognize.py \
  --input <путь_к_аудио> \
  --api sdk \
  --auto-chunk \
  --chunk-seconds 300
```

- Принудительная нарезка:
```bash
venv/bin/python ss_recognize.py \
  --input <путь_к_аудио> \
  --api sdk \
  --force-chunked \
  --chunk-seconds 300
```

- Стерео как два спикера в chunked‑режиме:
```bash
venv/bin/python ss_recognize.py \
  --input <путь_к_аудио> \
  --api sdk \
  --force-chunked \
  --chunk-stereo-as-speakers
```

Примечания:

- Параметр `--chunk-seconds` задаёт длину части (по умолчанию 300 секунд).
- Режимы `sdk/http` поддерживают нарезку; `grpc` — нет.
