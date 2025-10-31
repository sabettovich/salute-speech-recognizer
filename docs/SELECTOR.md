# Селектор стратегий (адаптивный)

- Источник знаний: docs/KB/cases/*.yml
- Логика:
  - Загрузка кейсов → матч по метаданным (codec, sr, ch, duration, size, env).
  - Скоринг: priority → специфичность → дефолт.
  - Выход: план (prep_mode, audio, transport, chunk, fallbacks, diarization, hints) + explain.
- Конфликты: берём с max priority; при равенстве — больше совпавших полей.
- Override: флаги CLI.
- Логи: tmp/selector_runs/*.json (анонимизация путей).
