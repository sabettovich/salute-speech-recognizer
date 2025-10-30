# Salute Speech Recognizer (v1.0.0)

CLI-инструмент для транскрибации аудио через Салют Спич (gRPC) с поддержкой hints, маппинга спикеров и Markdown-вывода.

## Быстрый старт

- Установите зависимости (рекомендуется venv Python 3.12):
```bash
pip install -e .[dev]
```

- Укажите ключ доступа:
```bash
export SBER_SPEECH_AUTH_KEY="<ваш ключ>"
```

- Положите аудио в `Source/audio.mp3` (короткий тестовый файл уже используется в проекте).

- Запустите распознавание (дефолт: SDK с авто‑нарезкой для устойчивости на длинных файлах):
```bash
venv/bin/python ss_recognize.py --input Source/audio.mp3 --api sdk --auto-chunk --chunk-seconds 300
```
Результат (в каталоге Result/):
- Markdown: `Result/audio.md`
- Сырый JSON: `Result/audio.grpc.raw.json`
- Нормализованный JSON: `Result/audio.grpc.norm.json`

## Примеры команд

- Одиночный файл с кастомными конфигами:
```bash
venv/bin/python ss_recognize.py \
  --input Source/my_record.wav \
  --api grpc \
  --language ru-RU \
  --hints Source/hints.txt \
  --speakers-map Source/speakers_map.json
```

- Пакетная обработка нескольких файлов (bash):
```bash
for f in Source/*.mp3; do \
  out="Result/$(basename "${f%.*}").md"; \
  venv/bin/python ss_recognize.py --input "$f" --output "$out" --api grpc \
    --hints Source/hints.txt --speakers-map Source/speakers_map.json; \
done
```

- Пакетная обработка со смешанными форматами (gRPC без нарезки):
```bash
for f in Source/*.{mp3,wav,ogg,opus,flac}; do \
  [ -e "$f" ] || continue; \
  out="Result/$(basename "${f%.*}").md"; \
  venv/bin/python ss_recognize.py --input "$f" --output "$out" --api grpc; \
done
```

### Длинные файлы (рекомендуется)

- Авто‑режим (сначала целиком, при ошибке — нарезка/склейка):
```bash
venv/bin/python ss_recognize.py --input Source/long.flac --api sdk --auto-chunk --chunk-seconds 300
```

- Принудительная нарезка:
```bash
venv/bin/python ss_recognize.py --input Source/long.flac --api sdk --force-chunked --chunk-seconds 300
```

Примечание: режим `cli.py` (gRPC) не режет на части; для длинных записей используйте `ss_recognize.py` с API=`sdk`.

## Python API

Можно использовать библиотеку напрямую, без CLI.

- Класс высокого уровня `SaluteSpeechRecognizer` из `salute_speech_recognizer`:
```python
from salute_speech_recognizer import SaluteSpeechRecognizer

rec = SaluteSpeechRecognizer(language="ru-RU", diarization=True)
res = rec.recognize("Source/audio.mp3")

print(res.markdown)
print(res.norm["segments"][0])
```

- Запись результатов в файлы:
```python
rec = SaluteSpeechRecognizer()
res = rec.recognize_to_file("Source/audio.mp3", "Result/audio.md")
# Будут созданы также Result/audio.grpc.raw.json и Result/audio.grpc.norm.json
```

- Низкоуровневая функция `grpc_recognize_to_objects`:
```python
from salute_speech_recognizer import grpc_recognize_to_objects

raw, norm, md = grpc_recognize_to_objects("Source/audio.mp3", language="ru-RU", diarization=True)
```

### Передача версионированных hints/speakers_map

Можно явно прокинуть пути к версиям файлов или сами объекты.

- Через пути:
```python
raw, norm, md = grpc_recognize_to_objects(
    "Source/audio.mp3",
    hints_path="Source/hints.v5.txt",
    speakers_map_path="Source/speakers_map.v7.json",
)
```

- Через объекты (если вы сами читаете их из хранилища):
```python
with open("Source/hints.v5.txt", "r", encoding="utf-8") as f:
    hints = [line.strip() for line in f if line.strip()]

import json
with open("Source/speakers_map.v7.json", "r", encoding="utf-8") as f:
    speakers_map = json.load(f)

raw, norm, md = grpc_recognize_to_objects(
    "Source/audio.mp3",
    hints=hints,
    speakers_map=speakers_map,
)
```

Прецеденты (приоритеты) выбора конфигураций:

- **hints**: аргумент `hints (list)` > `hints_path` > `HINTS_PATH` > `Source/hints.txt`.
- **speakers_map**: аргумент `speakers_map (dict)` > `speakers_map_path` > `SPEAKERS_MAP_PATH` > `Source/speakers_map.json`.

## Настройка качества

- Hints (`Source/hints.txt`): по одному слову/фразе на строку. Помогают модели распознавать термины/имена.
- SpeakerMap (`Source/speakers_map.json`): фраза → имя спикера. Поддерживает `re:` (регулярные выражения). Имена распространяются на все сегменты с тем же `speaker_id`.
- Гипотезы: используется `hypotheses_count=3`, n-best выбирается по покрытию hints.
- Таймауты (eou/no_speech/max_speech) настроены для стабильной сегментации.

Подробнее см. `USAGE.md` и `CONFIG.md`.

## Тесты

- Юнит:
```bash
pytest -q
```
- Интеграция (реальный вызов gRPC):
```bash
pytest -q -m integration
```
Требуется `SBER_SPEECH_AUTH_KEY` в окружении. 

## Лицензия

Unlicense. См. `LICENSE`.
