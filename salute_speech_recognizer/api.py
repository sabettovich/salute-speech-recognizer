from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from .grpc_async import grpc_recognize_to_objects, grpc_async_transcribe


@dataclass
class RecognitionResult:
    raw: Dict[str, Any]
    norm: Dict[str, Any]
    markdown: str


class SaluteSpeechRecognizer:
    def __init__(self, language: str = "ru-RU", diarization: bool = True) -> None:
        self.language = language
        self.diarization = diarization

    def recognize(self, input_path: str) -> RecognitionResult:
        raw, norm, md = grpc_recognize_to_objects(
            input_path,
            language=self.language,
            diarization=self.diarization,
        )
        return RecognitionResult(raw=raw, norm=norm, markdown=md)

    def recognize_to_file(self, input_path: str, output_md_path: str) -> RecognitionResult:
        raw, norm, md = grpc_recognize_to_objects(
            input_path,
            language=self.language,
            diarization=self.diarization,
        )
        with open(output_md_path, "w", encoding="utf-8") as f:
            f.write(md)
        base = output_md_path.rsplit(".", 1)[0]
        import json
        with open(base + ".grpc.raw.json", "w", encoding="utf-8") as jf:
            json.dump(raw, jf, ensure_ascii=False, indent=2)
        with open(base + ".grpc.norm.json", "w", encoding="utf-8") as jf:
            json.dump(norm, jf, ensure_ascii=False, indent=2)
        return RecognitionResult(raw=raw, norm=norm, markdown=md)
