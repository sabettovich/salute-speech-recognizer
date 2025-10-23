import json
from salute_speech_recognizer.normalize import normalize_grpc_result


def test_normalize_picks_best_hypothesis_by_hints():
    data = {
        "segments": [
            {
                "results": [
                    {
                        "text": "абра кадабра",
                        "normalized_text": "абра кадабра",
                        "start": "0s",
                        "end": "1s",
                    },
                    {
                        "text": "у вас есть вопросы",
                        "normalized_text": "у вас есть вопросы",
                        "start": "0s",
                        "end": "1s",
                    },
                ],
                "speaker_info": {"speaker_id": 1},
                "processed_audio_start": "0s",
                "processed_audio_end": "1s",
            }
        ]
    }
    hints = ["у вас есть вопросы"]
    norm = normalize_grpc_result(data, hints=hints)
    segs = norm.get("segments")
    assert isinstance(segs, list)
    assert segs and segs[0]["text"].startswith("у вас есть вопросы")
