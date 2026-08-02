import json
import os
import sys
import httpx

MS_URL = os.environ.get("MODEL_SERVING_URL", "http://lakemind-model-serving:10824")
MS_KEY = os.environ.get("MODELSERVING_API_KEY", "lakemind-modelserving-key")
SERVER_URL = os.environ.get("SERVER_API_URL", "http://lakemind-server-api:10823")
SERVER_KEY = os.environ.get("SERVER_API_KEY", "lakemind-internal-api-key")


def download_from_s3(uri: str) -> bytes:
    from urllib.parse import urlparse
    p = urlparse(uri)
    url = f"{SERVER_URL}/api/v1/storage/objects/{p.netloc}/{p.path.lstrip('/')}"
    resp = httpx.get(url, headers={"Authorization": f"Bearer {SERVER_KEY}"}, timeout=60)
    resp.raise_for_status()
    return resp.content


def upload_to_s3(uri: str, data: bytes | str):
    from urllib.parse import urlparse
    if isinstance(data, str):
        data = data.encode()
    p = urlparse(uri)
    url = f"{SERVER_URL}/api/v1/storage/objects/{p.netloc}/{p.path.lstrip('/')}"
    resp = httpx.put(url, content=data, headers={"Authorization": f"Bearer {SERVER_KEY}"}, timeout=60)
    resp.raise_for_status()


_asr_handle = None


def _get_asr_handle():
    global _asr_handle
    if _asr_handle is None:
        import ray
        from ray import serve
        ray.init(address=os.environ.get("LAKEMIND_RAY_ADDRESS", "auto"), ignore_reinit_error=True)
        _asr_handle = serve.get_deployment_handle("asr", "asr-app")
    return _asr_handle


def asr(audio: bytes, filename: str = "audio.wav") -> dict:
    handle = _get_asr_handle()
    return handle.transcribe.remote(audio, filename).result()


def llm_chat(system_prompt: str, user_content: str, profile: str = "meeting-minutes") -> str:
    import time
    last_err = None
    for attempt in range(6):
        try:
            resp = httpx.post(
                f"{MS_URL}/v1/chat/completions",
                headers={"Authorization": f"Bearer {MS_KEY}"},
                json={
                    "model": profile,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_content},
                    ],
                },
                timeout=120,
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        except Exception as e:
            last_err = e
            time.sleep(5 * (attempt + 1))
    raise last_err
