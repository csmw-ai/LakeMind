import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lakemind_utils import llm_chat, upload_to_s3

DEFAULT_SECTIONS = ["会议摘要", "关键决策", "行动项", "讨论要点", "待解决问题"]


def build_minutes_prompt(sections):
    parts = []
    for s in sections:
        if "摘要" in s or "总结" in s:
            parts.append(f"## {s}\n（1-2 句话概括会议主题与核心结论）")
        elif "行动" in s:
            parts.append(f"## {s}\n- [ ] 负责人：任务")
        else:
            parts.append(f"## {s}\n- ...")
    skeleton = "\n\n".join(parts)
    return f"""你是专业的会议纪要助手。根据会议转写文本生成结构化会议纪要（Markdown）。

要求：
1. 客观忠实于原文，不编造未讨论的内容
2. 决策与行动项尽量标注负责人（如原文提及）
3. 保留关键时间节点与量化数据
4. 语言简练，使用要点式表达
5. 转写可能存在 ASR 错别字，可在纪要中修正明显错误

输出格式（Markdown），按以下章节组织：
{skeleton}

只输出纪要正文，不要加额外说明或代码块标记。"""


def main():
    params = json.loads(os.environ["RAY_JOB_PARAMS"])
    transcript = params.get("transcript", "")
    meeting_title = params.get("meeting_title", "会议")
    template = params.get("template_snapshot", {})
    custom_instructions = template.get("minutes", {}).get("custom_instructions", "")
    sections = template.get("minutes", {}).get("sections") or DEFAULT_SECTIONS

    prompt = build_minutes_prompt(sections)
    if custom_instructions:
        prompt += f"\n\n额外要求：{custom_instructions}"

    minutes = llm_chat(prompt, f"会议标题：{meeting_title}\n\n转写文本：\n{transcript}")

    output = {"minutes": minutes}
    result_uri = params.get("result_uri")
    if result_uri:
        upload_to_s3(result_uri, json.dumps(output, ensure_ascii=False))
    print(json.dumps(output, ensure_ascii=False))


if __name__ == "__main__":
    main()
