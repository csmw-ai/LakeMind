import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lakemind_utils import llm_chat, upload_to_s3

KNOWLEDGE_TYPE_DEFINITIONS = {
    "process": "process（流程知识）：业务流程、操作步骤、工作流、SOP、阶段划分",
    "rule": "rule（规则知识）：制度、规范、约束条件、准入标准、合规要求",
    "insight": "insight（洞察知识）：分析结论、规律发现、因果推断、趋势判断",
    "risk": "risk（风险知识）：风险点、隐患、问题、待解决事项、依赖风险",
    "case": "case（案例知识）：具体事例、过往经验、参考案例、实践故事",
    "concept": "concept（概念知识）：核心概念、术语定义、概念关系（上下位/同义/因果等关系）",
}

DEFAULT_PROMPT = """你是会议知识萃取专家。从会议纪要与转写中提炼结构化知识，输出 JSON 数组。

每个知识点格式：
{"type": "类型key", "title": "简洁标题(≤20字)", "body": "详细描述(含上下文与关键信息)", "tags": ["相关标签"], "confidence": 0.0-1.0, "evidence": {"quote": "原文支撑片段", "start_ms": null, "end_ms": null}}

要求：
1. 每条知识必须有原文支撑（evidence.quote 引用转写或纪要中的原句）
2. 去重：同一知识不重复提取
3. 概念知识需在 body 中说明概念间关系（如有）
4. title 简明扼要，body 完整自洽
5. 只输出 JSON 数组，不要 markdown 代码块标记"""


def main():
    params = json.loads(os.environ["RAY_JOB_PARAMS"])
    transcript = params.get("transcript", "")
    minutes = params.get("minutes", "")
    template = params.get("template_snapshot", {})

    enabled_types = template.get("knowledge", {}).get("enabled_types") or list(KNOWLEDGE_TYPE_DEFINITIONS.keys())
    type_defs = "\n".join(
        f"- {KNOWLEDGE_TYPE_DEFINITIONS[t]}" for t in enabled_types if t in KNOWLEDGE_TYPE_DEFINITIONS
    )
    if not type_defs.strip():
        type_defs = "\n".join(f"- {v}" for v in KNOWLEDGE_TYPE_DEFINITIONS.values())
    prompt = DEFAULT_PROMPT + f"\n\n本次只提取以下类型：\n{type_defs}"

    custom_instructions = template.get("knowledge", {}).get("custom_instructions", "")
    if custom_instructions:
        prompt += f"\n\n额外要求：{custom_instructions}"

    user_content = f"会议纪要：\n{minutes}\n\n转写文本：\n{transcript}"
    raw = llm_chat(prompt, user_content, profile="meeting-knowledge-extract")
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw
        if raw.endswith("```"):
            raw = raw[:-3]
        raw = raw.strip()

    items = json.loads(raw)
    for item in items:
        item.setdefault("type", "concept")
        item.setdefault("tags", [])
        item.setdefault("confidence", 0.8)
        item.setdefault("evidence", {})

    output = {"items": items}
    result_uri = params.get("result_uri")
    if result_uri:
        upload_to_s3(result_uri, json.dumps(output, ensure_ascii=False))
    print(json.dumps(output, ensure_ascii=False))


if __name__ == "__main__":
    main()
