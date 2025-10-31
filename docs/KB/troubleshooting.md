# Troubleshooting

- gRPC DEADLINE_EXCEEDED при загрузке
  - Уменьшить chunk.seconds до 120/60; включить HTTP fallback per-chunk.

- HTTP 400 Bad Request при создании задачи
  - Передать явные параметры аудио (encoding, sample_rate, channels). Пробовать snake/camel и nested audio_format/audioFormat.

- Пустой Markdown вывод
  - Нормализовать сегменты; фильтровать пустые тексты; проверять .http.raw.json/.grpc.raw.json.
