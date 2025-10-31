# Схема кейса (YAML)

id: string
match:
  codec: [mp3, flac, opus, pcm_s16le]
  sample_rate: [16000, 44100]
  channels: [1, 2]
  duration_sec:
    min: 0
    max: 7200
  size_mb:
    max: 2000
  env:
    network: [any, stable, unstable]
strategy:
  prep_mode: canonical | vendor
  audio:
    encoding: PCM_S16LE | MP3 | FLAC | OPUS
    sample_rate: 16000
    channels_count: 1
  transport:
    primary: grpc_async | http_async
    fallback: http_async_per_chunk | none
  chunk:
    seconds: 120
    max_retries_per_chunk: 1
  diarization: service_only
  hints:
    enable: true
scoring:
  priority: 50
  rationale: "краткое объяснение выбора"
notes: "опционально"
