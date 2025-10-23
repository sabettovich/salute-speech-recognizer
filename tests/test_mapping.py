from salute_speech_recognizer.mapping import apply_speaker_mapping


def test_mapping_regex_and_propagation():
    norm = {
        "segments": [
            {"start": 0.0, "end": 1.0, "text": "это было не 9 событие", "speaker_id": 2},
            {"start": 1.1, "end": 2.0, "text": "продолжение речи", "speaker_id": 2},
        ]
    }
    phrase_map = {
        "re:это\s*было\s*не\s*9(\s*сентябр[ья])?": "Судья",
        "re:не\s*9\s*событ(ия|ий|е)": "Судья",
    }
    out = apply_speaker_mapping(norm, phrase_map)
    segs = out["segments"]
    assert segs[0].get("speaker_name") == "Судья"
    # имя распространяется на все сегменты того же speaker_id
    assert segs[1].get("speaker_name") == "Судья"
