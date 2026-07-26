import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import json
from lakemind_utils import download_from_s3, upload_to_s3, asr


def main():
    params = json.loads(os.environ["RAY_JOB_PARAMS"])
    chunk_uri = params["chunk_uri"]
    result_uri = params["result_uri"]

    audio = download_from_s3(chunk_uri)
    result = asr(audio)

    output = {"text": result.get("text", ""), "segments": result.get("segments", [])}
    upload_to_s3(result_uri, json.dumps(output, ensure_ascii=False))
    print(json.dumps(output, ensure_ascii=False))


if __name__ == "__main__":
    main()
