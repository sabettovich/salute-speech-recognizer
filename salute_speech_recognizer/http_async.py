import os
import time
import json
import typing as t
import requests
from salute_speech.speech_recognition import SaluteSpeechClient
from dotenv import load_dotenv

OAUTH_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
BASE = "https://smartspeech.sber.ru/rest/v1"
NGW_BASE = "https://ngw.devices.sberbank.ru:9443/api/v2"
UPLOAD_URL = f"{BASE}/data:upload"
NGW_UPLOAD_URL = f"{NGW_BASE}/data/upload"
CREATE_CANDIDATES = [
    f"{BASE}/speech:asyncRecognize",
    f"{BASE}/speech:recognize-async",
    f"{NGW_BASE}/recognition",
]
# Probable task status endpoints to try
STATUS_CANDIDATES = [
    f"{BASE}/tasks",                  # GET /tasks?id=<task_id>
    f"{BASE}/task",                   # GET /task?id=<task_id>
    f"{BASE}/task:get",               # POST with {"task_id": "..."}
    f"{NGW_BASE}/recognition",        # GET /recognition/{task_id}
]
# Probable download endpoints to try
DOWNLOAD_CANDIDATES = [
    f"{BASE}/data:download",          # POST with {"response_file_id": "..."} or GET ?response_file_id=
]

def _log(debug: dict, entry: dict) -> None:
    debug.setdefault("steps", []).append(entry)


def _resolve_verify() -> t.Any:
    # Prefer explicit env bundle
    ca_env = os.getenv("SBER_CA_BUNDLE")
    if ca_env and os.path.exists(ca_env):
        return ca_env
    # Try known bundle from SalutSpeechPythonLib
    candidates = [
        os.path.abspath(os.path.join(os.getcwd(), "..", "SalutSpeechPythonLib", "cacert.pem")),
        os.path.abspath(os.path.join(os.getcwd(), "SalutSpeechPythonLib", "cacert.pem")),
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    # Last resort (not recommended): disable verification
    return False


def get_access_token(auth_key: str, scope: str = "SALUTE_SPEECH_PERS", debug: dict | None = None) -> str:
    headers = {
        "Authorization": f"Basic {auth_key}",
        "RqUID": "auto-http-async",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    data = {"scope": scope}
    resp = requests.post(OAUTH_URL, headers=headers, data=data, verify=_resolve_verify())
    if debug is not None:
        _log(debug, {"action": "oauth", "status": resp.status_code, "text": _safe_text(resp)})
    resp.raise_for_status()
    return resp.json().get("access_token")


def upload_file(path: str, bearer: str, debug: dict | None = None) -> str:
    with open(path, "rb") as f:
        headers = {"Authorization": f"Bearer {bearer}", "Content-Type": "application/octet-stream"}
        # Try NGW upload first
        resp = requests.post(NGW_UPLOAD_URL, headers=headers, data=f, verify=_resolve_verify())
        if resp.status_code != 200:
            # Fallback to SmartSpeech REST upload
            f.seek(0)
            resp = requests.post(UPLOAD_URL, headers={"Authorization": f"Bearer {bearer}"}, data=f, verify=_resolve_verify())
    if debug is not None:
        _log(debug, {"action": "upload", "url": UPLOAD_URL, "status": resp.status_code, "text": _safe_text(resp)})
    resp.raise_for_status()
    j = resp.json()
    res = j.get("result", {}) if isinstance(j, dict) else {}
    req_id = (
        j.get("request_file_id")
        or j.get("requestFileId")
        or j.get("file_id")
        or res.get("request_file_id")
        or res.get("requestFileId")
        or res.get("file_id")
        or res.get("result", {}).get("request_file_id")
        or res.get("result", {}).get("requestFileId")
        or res.get("result", {}).get("file_id")
    )
    if not req_id:
        raise RuntimeError(f"Не получен request_file_id из ответа upload: {j}")
    return req_id


def create_task(request_file_id: str, bearer: str, language: str, diarization: bool, debug: dict | None = None) -> str:
    headers = {"Authorization": f"Bearer {bearer}", "Content-Type": "application/json"}
    # SmartSpeech REST body (with options)
    body_rest = {
        "request_file_id": request_file_id,
        "options": {
            "language": language,
            "model": "general",
        }
    }
    if diarization:
        body_rest["options"]["speaker_separation_options"] = {"enable": True}
        body_rest["options"]["hypotheses_count"] = 1

    # NGW v2 body (flat)
    body_ngw = {
        "file_id": request_file_id,
        "model": "general",
        "language": language,
    }
    if diarization:
        body_ngw["speaker_separation_options"] = {"enable": True}

    last_err: str | None = None
    # Try NGW first with flat body
    for url, body in [(f"{NGW_BASE}/recognition", body_ngw)] + [(u, body_rest) for u in CREATE_CANDIDATES]:
        resp = requests.post(url, headers=headers, data=json.dumps(body), verify=_resolve_verify())
        if debug is not None:
            _log(debug, {"action": "create", "url": url, "status": resp.status_code, "text": _safe_text(resp)})
        if resp.status_code == 200:
            j = safe_json(resp)
            res = j.get("result", {}) if isinstance(j, dict) else {}
            task_id = (
                j.get("id")
                or j.get("task_id")
                or res.get("id")
                or res.get("task_id")
                or res.get("result", {}).get("id")
                or res.get("result", {}).get("task_id")
            )
            if task_id:
                return task_id
        last_err = f"{resp.status_code} {resp.text[:500]}"
    raise RuntimeError(f"Не удалось создать задачу. Последняя ошибка: {last_err}")


def get_task(task_id: str, bearer: str, debug: dict | None = None) -> dict:
    headers = {"Authorization": f"Bearer {bearer}"}
    # Try direct NGW GET /recognition/{task_id}
    ngw_url = f"{NGW_BASE}/recognition/{task_id}"
    try:
        resp = requests.get(ngw_url, headers=headers, timeout=15, verify=_resolve_verify())
        if debug is not None:
            _log(debug, {"action": "status_ngw", "url": ngw_url, "status": resp.status_code, "text": _safe_text(resp)})
        if resp.status_code == 200:
            j = safe_json(resp)
            return j.get("result", j)
    except Exception as e:
        if debug is not None:
            _log(debug, {"action": "status_ngw_exc", "url": ngw_url, "error": str(e)})
    # Try GET/POST patterns on SmartSpeech REST
    for base in STATUS_CANDIDATES:
        # GET with query
        get_url = base
        try:
            resp = requests.get(get_url, headers=headers, params={"id": task_id}, timeout=15, verify=_resolve_verify())
            if debug is not None:
                _log(debug, {"action": "status_get", "url": get_url, "status": resp.status_code, "text": _safe_text(resp)})
            if resp.status_code == 200:
                j = safe_json(resp)
                return j.get("result", j)
        except Exception as e:
            if debug is not None:
                _log(debug, {"action": "status_get_exc", "url": get_url, "error": str(e)})
        # POST with JSON
        try:
            resp = requests.post(base, headers={**headers, "Content-Type": "application/json"}, data=json.dumps({"task_id": task_id}), timeout=15, verify=_resolve_verify())
            if debug is not None:
                _log(debug, {"action": "status_post", "url": base, "status": resp.status_code, "text": _safe_text(resp)})
            if resp.status_code == 200:
                j = safe_json(resp)
                return j.get("result", j)
        except Exception as e:
            if debug is not None:
                _log(debug, {"action": "status_post_exc", "url": base, "error": str(e)})
    raise RuntimeError("Не удалось получить статус задачи")


def download_result(response_file_id: str, bearer: str, debug: dict | None = None) -> bytes:
    headers = {"Authorization": f"Bearer {bearer}"}
    # Try GET with params
    for url in DOWNLOAD_CANDIDATES:
        try:
            resp = requests.get(url, headers=headers, params={"response_file_id": response_file_id}, timeout=20, verify=_resolve_verify())
            if debug is not None:
                _log(debug, {"action": "download_get", "url": url, "status": resp.status_code, "len": len(resp.content)})
            if resp.status_code == 200 and resp.content:
                return resp.content
        except Exception as e:
            if debug is not None:
                _log(debug, {"action": "download_get_exc", "url": url, "error": str(e)})
        # Try POST with JSON
        try:
            resp = requests.post(url, headers={**headers, "Content-Type": "application/json"}, data=json.dumps({"response_file_id": response_file_id}), timeout=20, verify=_resolve_verify())
            if debug is not None:
                _log(debug, {"action": "download_post", "url": url, "status": resp.status_code, "len": len(resp.content)})
            if resp.status_code == 200 and resp.content:
                return resp.content
        except Exception as e:
            if debug is not None:
                _log(debug, {"action": "download_post_exc", "url": url, "error": str(e)})
    raise RuntimeError("Не удалось скачать результат")


def http_async_transcribe(input_path: str, output_md_path: str, language: str = "ru-RU", diarization: bool = True) -> None:
    load_dotenv()
    auth_key = os.getenv("SBER_SPEECH_AUTH_KEY") or os.getenv("SBER_SPEECH_API_KEY")
    if not auth_key:
        raise RuntimeError("Не найден SBER_SPEECH_AUTH_KEY (или SBER_SPEECH_API_KEY)")

    debug: dict = {"input": input_path, "language": language, "diarization": diarization}

    # Prefer SDK's token manager to avoid OAuth nuances
    try:
        client = SaluteSpeechClient(client_credentials=auth_key)
        token = client.token_manager.get_valid_token()
        _log(debug, {"action": "oauth_sdk", "status": "OK"})
    except Exception as e:
        _log(debug, {"action": "oauth_sdk_fail", "error": str(e)})
        # Fallback to direct OAuth
        token = get_access_token(auth_key, debug=debug)
    req_id = upload_file(input_path, token, debug=debug)
    task_id = create_task(req_id, token, language, diarization, debug=debug)

    # Poll task
    status = None
    for _ in range(60):  # up to ~5 min with waits
        time.sleep(5)
        st = get_task(task_id, token, debug=debug)
        status = st.get("status") or st.get("task", {}).get("status")
        if status in ("DONE", "ERROR", "CANCELED") or str(status).upper() in ("DONE", "ERROR", "CANCELED"):
            status_upper = str(status).upper()
            if status_upper == "DONE":
                resp_id = st.get("response_file_id") or st.get("task", {}).get("response_file_id")
                if not resp_id:
                    raise RuntimeError(f"Нет response_file_id в статусе: {st}")
                raw_bytes = download_result(resp_id, token, debug=debug)
                # Try parse JSON, else save bytes
                try:
                    data = json.loads(raw_bytes.decode("utf-8"))
                except Exception:
                    data = {"raw": True, "bytes_len": len(raw_bytes)}
                # Save raw
                raw_path = os.path.splitext(output_md_path)[0] + ".http.raw.json"
                with open(raw_path, "w", encoding="utf-8") as jf:
                    json.dump(data, jf, ensure_ascii=False, indent=2)
                # Build markdown
                md = build_markdown_from_http_result(data)
                os.makedirs(os.path.dirname(os.path.abspath(output_md_path)), exist_ok=True)
                with open(output_md_path, "w", encoding="utf-8") as f:
                    f.write(md)
                # Save debug log
                with open(os.path.join(os.path.dirname(os.path.abspath(output_md_path)), "http_async_debug.json"), "w", encoding="utf-8") as df:
                    json.dump(debug, df, ensure_ascii=False, indent=2)
                return
            else:
                # Save debug and raise
                with open(os.path.join(os.path.dirname(os.path.abspath(output_md_path)), "http_async_debug.json"), "w", encoding="utf-8") as df:
                    json.dump(debug, df, ensure_ascii=False, indent=2)
                raise RuntimeError(f"Задача завершилась со статусом {status}")
    # Timeout
    with open(os.path.join(os.path.dirname(os.path.abspath(output_md_path)), "http_async_debug.json"), "w", encoding="utf-8") as df:
        json.dump(debug, df, ensure_ascii=False, indent=2)
    raise RuntimeError("Таймаут ожидания задачи HTTP async")


def build_markdown_from_http_result(data: dict) -> str:
    lines: list[str] = ["# Транскрипт", ""]
    # Try read duration/language
    duration = data.get("duration")
    language = data.get("language")
    if duration is not None:
        lines.append(f"- **Длительность**: {float(duration):.2f} c")
    if language:
        lines.append(f"- **Язык**: {language}")
    lines.append("")

    segments = data.get("segments") or []
    if isinstance(segments, list):
        for s in segments:
            start = s.get("start")
            end = s.get("end")
            text = s.get("text") or ""
            speaker = s.get("speaker_id") or s.get("speaker")
            start_ts = _sec_to_ts(start) if isinstance(start, (int, float)) else "--:--.--"
            end_ts = _sec_to_ts(end) if isinstance(end, (int, float)) else "--:--.--"
            if speaker is not None and speaker != -1:
                lines.append(f"- [{start_ts} - {end_ts}] **Speaker {speaker}**: {text}")
            else:
                lines.append(f"- [{start_ts} - {end_ts}] {text}")
    else:
        # Fallback if service returns plain text only
        text = data.get("text") or ""
        if text:
            lines.append(text)
    lines.append("")
    return "\n".join(lines)


def _sec_to_ts(sec: float) -> str:
    m = int(sec // 60)
    s = sec - m * 60
    return f"{m:02d}:{s:05.2f}"


def _safe_text(resp: requests.Response) -> str:
    try:
        t = resp.text
        return t[:500]
    except Exception:
        return "<no-text>"


def safe_json(resp: requests.Response) -> dict:
    try:
        return resp.json()
    except Exception:
        return {"text": _safe_text(resp)}
