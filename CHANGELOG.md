# Changelog

## 1.0.0 - Initial Release

- gRPC-клиент распознавания (Салют Спич) с:
  - hints (`Source/hints.txt`), `enable_letters=True`.
  - выбор n-best (hypotheses_count=3) по покрытию hints.
  - SpeakerMap (`Source/speakers_map.json`) с нормализацией и поддержкой `regex` (`re:`).
  - строгая дедупликация при рендере Markdown.
  - управление тайм-аутами распознавания (no_speech/eou/max_speech).
- CLI и документация (`README.md`, `USAGE.md`, `CONFIG.md`, `DEVDOCS.md`).
- Лицензия: Unlicense.
