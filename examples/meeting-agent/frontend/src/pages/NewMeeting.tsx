import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";

export default function NewMeeting() {
  const nav = useNavigate();

  useEffect(() => {
    (async () => {
      try {
        const r = await api.post("/tasks", {
          title: "未命名会议",
          source_type: "LIVE",
          template_snapshot: {
            transcription: { language: "zh", timestamps: "segment", punctuation: true },
            minutes: { preset: "general", sections: ["会议摘要", "关键决策", "行动项", "讨论要点", "待解决问题"] },
            knowledge: { enabled_types: ["process", "rule", "insight", "risk", "case", "concept"], auto_publish: false },
          },
        });
        nav(`/app/meetings/${r.data.task_id}`, { replace: true });
      } catch {
        nav("/app/meetings", { replace: true });
      }
    })();
  }, []);

  return <div>创建中...</div>;
}
