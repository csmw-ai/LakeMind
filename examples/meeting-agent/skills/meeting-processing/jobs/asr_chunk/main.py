import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lakemind_utils import download_from_s3, upload_to_s3, asr


def main():
    params = json.loads(os.environ["RAY_JOB_PARAMS"])
    chunk_uri = params["chunk_uri"]
    result_key = params.get("result_key", "asr/result")

    audio = download_from_s3(chunk_uri)

    if chunk_uri.endswith(".webm"):
        filename = "audio.webm"
    elif chunk_uri.endswith(".wav"):
        filename = "audio.wav"
    elif chunk_uri.endswith(".mp3"):
        filename = "audio.mp3"
    elif chunk_uri.endswith(".m4a"):
        filename = "audio.m4a"
    else:
        filename = "audio.webm"

    result = asr(audio, filename=filename)

    output = {"text": result.get("text", ""), "segments": result.get("segments", [])}

    result_uri = chunk_uri.rsplit("/audio/chunks/", 1)[0] + "/results/" + result_key + ".json"
    upload_to_s3(result_uri, json.dumps(output, ensure_ascii=False))

    print(json.dumps(output, ensure_ascii=False))


if __name__ == "__main__":
    main()
