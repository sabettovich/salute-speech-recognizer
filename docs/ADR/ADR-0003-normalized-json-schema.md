# ADR-0003: Схема нормализованного JSON

- segments: [{start,end,text,speaker_id?,speaker_name?}]
- duration, language — опционально.
- Причина: единый рендер и обработка независимо от бэкенда.
