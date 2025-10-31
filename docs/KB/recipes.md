# Рецепты

- Длинный файл, нестабильная сеть
  venv/bin/ssr --prep-mode canonical --verbose --input <in> --output <out> --language ru-RU
  (внутри: chunked 120 c, gRPC→HTTP per-chunk)

- Короткий файл (<5 мин)
  venv/bin/ssr --prep-mode vendor --input <in> --output <out>

- Беречь исходный формат (если поддержан)
  venv/bin/ssr --prep-mode vendor --verbose --input <in> --output <out>
