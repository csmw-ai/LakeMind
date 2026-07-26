import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import json
from lakemind_utils import download_from_s3, upload_to_s3, llm_chat

SUMMARIZE_PROMPT = """你是会议纪要助手。根据转写文本生成结构化会议纪要（Markdown）。
格式：
## 会议摘要
（一句话概括）

## 关键决策
1. ...

## 行动项
- [ ] 负责人：任务

## 讨论要点
- ...

只输出纪要内容，不要加额外说明。"""


def main():
    params = json.loads(os.environ["RAY_JOB_PARAMS"])
    transcript_uri = params["transcript_uri"]
    result_uri = params["result_uri"]
    meeting_title = params.get("meeting_title", "会议")

    transcript = json.loads(download_from_s3(transcript_uri))

    minutes = llm_chat(
        SUMMARIZE_PROMPT,
        f"会议标题：{meeting_title}\n\n转写文本：\n{transcript['text']}",
    )

    minutes_uri = transcript_uri.replace("transcript.json", "minutes.md")
    upload_to_s3(minutes_uri, minutes)

    output = {"minutes": minutes, "minutes_uri": minutes_uri}
    upload_to_s3(result_uri, json.dumps(output, ensure_ascii=False))
    print(json.dumps(output, ensure_ascii=False))


if __name__ == "__main__":
    main()
