# Автологирование успешных запусков

- **Файлы учета**
  - docs/KB/case_stats.yml — счётчики применений кейсов (`case_id: uses`).
  - docs/KB/success_log.csv — журнал успешных запусков (timestamp,input,output,case_id,priority,prep_mode,transport,chunk_seconds,duration,codec,sample_rate,channels).

- **Где реализовано**
  - Модуль `salute_speech_recognizer/kb_log.py`.
  - Вызов `log_success(...)` интегрирован в CLI:
    - smart + chunked
    - smart без чанков (grpc/http)
    - обычный режим (canonical/vendor, grpc/http, включая vendor fallback)

- **Поведение**
  - Если `selector` вернул `chosen_case` — инкрементируется счётчик в `case_stats.yml`.
  - Если кейс отсутствует — создаётся черновик в `docs/KB/cases/*_auto.yml` на основе meta+plan.
  - Всегда добавляется строка в `success_log.csv`.

- **Как отключить**
  - Автологирование не отключается: оно не влияет на основной поток и молча игнорирует ошибки записи.

- **Дальнейшее использование**
  - `case_stats.yml` помогает поднимать приоритет кейсов с высокой успешностью.
  - По `success_log.csv` можно строить отчёты/графики качества и стабильности.
