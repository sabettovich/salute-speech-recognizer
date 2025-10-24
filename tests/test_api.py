import json
import os
from pathlib import Path

from salute_speech_recognizer import SaluteSpeechRecognizer
import salute_speech_recognizer.api as api_mod


def test_api_recognize_returns_result(monkeypatch):
    def fake_grpc(path, language="ru-RU", diarization=True):
        return {"ok": 1}, {"segments": [{"start": 0.0, "end": 1.0, "text": "hi"}]}, "# md\n- [00:00.00 - 00:01.00] hi\n"

    monkeypatch.setattr(api_mod, "grpc_recognize_to_objects", fake_grpc)

    rec = SaluteSpeechRecognizer()
    res = rec.recognize("Source/fake.mp3")

    assert isinstance(res.markdown, str) and res.markdown.startswith("#")
    assert "segments" in res.norm and isinstance(res.norm["segments"], list)
    assert res.raw.get("ok") == 1


def test_api_recognize_to_file_writes_outputs(monkeypatch, tmp_path: Path):
    def fake_grpc(path, language="ru-RU", diarization=True):
        return {"ok": 1}, {"segments": []}, "# md\n"

    monkeypatch.setattr(api_mod, "grpc_recognize_to_objects", fake_grpc)

    out_md = tmp_path / "out.md"
    rec = SaluteSpeechRecognizer()
    res = rec.recognize_to_file("Source/fake.mp3", str(out_md))

    assert out_md.exists() and out_md.read_text(encoding="utf-8").startswith("# md")

    raw = tmp_path / "out.grpc.raw.json"
    norm = tmp_path / "out.grpc.norm.json"
    assert raw.exists() and norm.exists()

    with open(raw, "r", encoding="utf-8") as f:
        d = json.load(f)
        assert d.get("ok") == 1
    with open(norm, "r", encoding="utf-8") as f:
        d = json.load(f)
        assert "segments" in d
