# DevDocs

## Структура (целевая для v1.0)

- `salute_speech_recognizer/`
  - `grpc_async.py` — gRPC-клиент (пока содержит основную логику, будет разнесён)
  - `normalize.py` — выбор лучшей гипотезы по hints (n-best)
  - `mapping.py` — SpeakerMap (нормализация текста, regex, распространение по speaker_id)
  - `render.py` — дедуп и вывод Markdown
  - `io.py` — ввод/вывод, загрузка конфигов (hints/map)
  - `cli.py` — CLI-обертка, парсинг аргументов
- `ss_recognize.py` — текущий CLI-скрипт (будет вызывать `cli.py`)
- `Source/` — входы и конфиги (hints/map)
- `Result/` — артефакты результата (md/raw/norm)

## Среда разработки

- Python 3.12
- Установка:
```bash
pip install -e .[dev]
pre-commit install
```

## Линтеры/формат

- Black, isort, flake8, mypy.
- Запуск:
```bash
black . && isort . && flake8 && mypy
```

## Тестирование

- Юнит-тесты:
```bash
pytest -q
```
- Интеграция (реальный gRPC):
```bash
export SBER_SPEECH_AUTH_KEY="<ключ>"
pytest -q -m integration
```

## Переменные окружения

- `SBER_SPEECH_AUTH_KEY` — ключ для доступа к API.
- `SBER_CA_BUNDLE` — кастомный root CA (опционально).

## Релизы

- Версионирование SemVer.
- Обновлять `CHANGELOG.md`.
