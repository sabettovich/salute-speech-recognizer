# Архитектура salute-speech-recognizer

- Модули
  - cli: CLI и аргументы, запуск стратегий.
  - audio_prep: probe(ffprobe) → выбор цели → нормализация (ffmpeg).
  - grpc_async: загрузка файла, создание async-задачи, скачивание результата.
  - http_async: upload → asyncRecognize → polling → download, нормализация.
  - chunked: резка канонического WAV на чанки и распознавание с fallback.
  - render: сборка Markdown из нормализованного JSON.
  - strategy_selector: (планируется) выбор стратегии по кейсам.

- Поток данных
  1) probe → selector (план) → audio_prep.prepare()
  2) recognize (gRPC/HTTP, возможно per-chunk)
  3) normalize → render → Markdown (+ sidecar JSON).

- Контракты
  - PreparedAudio: normalized_path, duration_sec, original_meta, grpc_options, http_options, prep_mode, changed.
  - Нормализованный JSON: { duration?, language?, segments: [{start,end,text,speaker_id?,speaker_name?}] }.

- Временные и артефакты
  - tmp/: кэш WAV/чанков, логи, отладка.
  - Result/: Markdown и *.raw.json/*.norm.json.

- Правила
  - Диризация только на стороне сервиса.
  - Маппинг имён — опционально, постобработка.
