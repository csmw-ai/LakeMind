import { useEffect, useRef, useState } from "react";
import { Button, Space, Typography, Tag, Input, message, Popconfirm, Modal, Select, Card, List, Tooltip, Tabs } from "antd";
import { SettingOutlined, EditOutlined, CheckOutlined } from "@ant-design/icons";
import { useParams, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import ChunkPlayer from "../components/ChunkPlayer";

const { TextArea } = Input;

const KNOWLEDGE_TYPES: Record<string, string> = {
  process: "流程知识",
  rule: "规则知识",
  insight: "洞察知识",
  risk: "风险知识",
  case: "案例知识",
  concept: "概念知识",
};

const KNOWLEDGE_LABELS: Record<string, string> = {
  ...KNOWLEDGE_TYPES,
  decision: "决策",
  action_item: "行动项",
  requirement: "需求",
  lesson: "经验教训",
  fact: "事实",
};

export default function TaskDetail() {
  const { taskId } = useParams();
  const nav = useNavigate();
  const [task, setTask] = useState<any>(null);
  const [recording, setRecording] = useState(false);
  const [segments, setSegments] = useState<any[]>([]);
  const [minutes, setMinutes] = useState<any[]>([]);
  const [knowledge, setKnowledge] = useState<any[]>([]);
  const [recElapsed, setRecElapsed] = useState(0);
  const [uploadingChunks, setUploadingChunks] = useState(0);
  const [chunks, setChunks] = useState<any[]>([]);
  const [editingTitle, setEditingTitle] = useState(false);
  const [titleDraft, setTitleDraft] = useState("");
  const [configOpen, setConfigOpen] = useState(false);
  const [templates, setTemplates] = useState<any[]>([]);
  const [configDraft, setConfigDraft] = useState<any>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunkSeqRef = useRef(0);
  const sseRef = useRef<EventSource | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const recStartRef = useRef(0);
  const stoppingRef = useRef(false);
  const transcriptEndRef = useRef<HTMLDivElement | null>(null);

  const [loadError, setLoadError] = useState(false);

  useEffect(() => { loadAll(); connectSSE(); return () => { sseRef.current?.close(); if (timerRef.current) clearInterval(timerRef.current); }; }, []);

  async function loadAll() {
    if (!taskId) return;
    setLoadError(false);
    try {
      const [t, m, k] = await Promise.all([
        api.get(`/tasks/${taskId}`),
        api.get(`/tasks/${taskId}/minutes`),
        api.get(`/tasks/${taskId}/knowledge`),
      ]);
      setTask(t.data);
      setMinutes(m.data.versions || []);
      setKnowledge(k.data.items || []);
      if (t.data.status === "RECORDING") {
        setRecording(true);
        recStartRef.current = Date.now() - (t.data.duration_ms || 0);
        timerRef.current = setInterval(() => {
          setRecElapsed(Math.floor((Date.now() - recStartRef.current) / 1000));
        }, 1000);
      }
      if (t.data.status === "RECORDING" || t.data.status === "FINALIZING" || t.data.status === "REVIEW_REQUIRED" || t.data.status === "COMPLETED") {
        try {
          const manifest = await api.get(`/tasks/${taskId}/audio/manifest`);
          setChunks(manifest.data.chunks || []);
        } catch {}
      }
      const seg = await api.get(`/tasks/${taskId}/transcript`);
      setSegments(seg.data.segments || []);
    } catch (err: any) {
      if (err?.response?.status === 404) {
        setLoadError(true);
      } else {
        message.error(`加载失败: ${err?.message || err}`);
      }
    }
  }

  function connectSSE() {
    if (!taskId) return;
    const es = new EventSource(`/api/tasks/${taskId}/events`);
    sseRef.current = es;
    es.addEventListener("chunk.uploaded", () => loadManifest());
    es.addEventListener("transcript.segment_ready", () => loadTranscript());
    es.addEventListener("minutes.preview_ready", () => loadMinutes());
    es.addEventListener("knowledge.draft_ready", () => loadKnowledge());
    es.addEventListener("task.status_changed", (e: any) => {
      const data = JSON.parse(e.data);
      setTask((prev: any) => prev ? { ...prev, status: data.status } : prev);
      if (data.status === "REVIEW_REQUIRED" || data.status === "COMPLETED") loadAll();
    });
    es.addEventListener("error", (e: any) => {
      try { const data = JSON.parse(e.data); message.error(`${data.stage}: ${data.message}`); } catch {}
    });
  }

  async function loadManifest() {
    if (!taskId) return;
    try {
      const r = await api.get(`/tasks/${taskId}/audio/manifest`);
      setChunks(r.data.chunks || []);
    } catch {}
  }
  async function loadTranscript() {
    if (!taskId) return;
    const r = await api.get(`/tasks/${taskId}/transcript`);
    setSegments(r.data.segments || []);
    setTimeout(() => { transcriptEndRef.current?.scrollIntoView({ behavior: "smooth" }); }, 100);
  }
  async function loadMinutes() {
    if (!taskId) return;
    const r = await api.get(`/tasks/${taskId}/minutes`);
    setMinutes(r.data.versions || []);
  }
  async function loadKnowledge() {
    if (!taskId) return;
    const r = await api.get(`/tasks/${taskId}/knowledge`);
    setKnowledge(r.data.items || []);
  }

  async function uploadChunk(seq: number, buf: ArrayBuffer, durationMs: number) {
    const checksum = await crypto.subtle.digest("SHA-256", buf);
    const checksumHex = Array.from(new Uint8Array(checksum)).map(b => b.toString(16).padStart(2, "0")).join("");
    setUploadingChunks(c => c + 1);
    try {
      await api.put(`/tasks/${taskId}/audio/chunks/${seq}`, buf, {
        headers: { "Content-Type": "audio/webm", "X-Chunk-Checksum": checksumHex, "X-Chunk-Duration-Ms": String(durationMs) },
      });
    } catch (err: any) {
      message.error(`分片 ${seq} 上传失败: ${err?.message || err}`);
    } finally {
      setUploadingChunks(c => c - 1);
    }
  }

  async function startRecording() {
    try {
      await api.post(`/tasks/${taskId}/start`);
      setTask((p: any) => ({ ...p, status: "RECORDING" }));
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      chunkSeqRef.current = 0;
      stoppingRef.current = false;
      recStartRef.current = Date.now();
      setRecElapsed(0);
      setRecording(true);
      timerRef.current = setInterval(() => {
        setRecElapsed(Math.floor((Date.now() - recStartRef.current) / 1000));
      }, 1000);

      function recordOneChunk() {
        if (stoppingRef.current) return;
        const mr = new MediaRecorder(stream, { mimeType: "audio/webm" });
        mediaRecorderRef.current = mr;
        mr.ondataavailable = async (e: BlobEvent) => {
          if (e.data.size > 100 && !stoppingRef.current) {
            const buf = await e.data.arrayBuffer();
            chunkSeqRef.current++;
            uploadChunk(chunkSeqRef.current, buf, 20000);
          }
        };
        mr.onstop = () => { recordOneChunk(); };
        mr.start();
        setTimeout(() => { if (mr.state === "recording") mr.stop(); }, 20000);
      }
      recordOneChunk();
    } catch (err: any) {
      message.error(err?.message || "录音启动失败");
    }
  }

  async function stopRecording() {
    stoppingRef.current = true;
    const mr = mediaRecorderRef.current;
    if (mr && mr.state !== "inactive") {
      mr.stop();
    }
    streamRef.current?.getTracks().forEach(t => t.stop());
    setRecording(false);
    if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null; }
    await new Promise(r => setTimeout(r, 500));
    try {
      await api.post(`/tasks/${taskId}/stop`);
      setTask((p: any) => ({ ...p, status: "FINALIZING" }));
    } catch (err: any) {
      message.error(`停止失败: ${err?.message || err}`);
    }
  }

  async function del() {
    sseRef.current?.close();
    sseRef.current = null;
    if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null; }
    stoppingRef.current = true;
    streamRef.current?.getTracks().forEach(t => t.stop());
    try { await api.delete(`/tasks/${taskId}`); } catch {}
    nav("/app/meetings");
  }

  async function saveTitle() {
    if (!titleDraft.trim()) { setEditingTitle(false); return; }
    try {
      await api.patch(`/tasks/${taskId}`, { title: titleDraft.trim() });
      setTask((p: any) => ({ ...p, title: titleDraft.trim() }));
    } catch { message.error("保存标题失败"); }
    setEditingTitle(false);
  }

  async function openConfig() {
    try {
      const r = await api.get("/templates");
      setTemplates(r.data.items || []);
    } catch {}
    setConfigDraft(task?.template_snapshot ? JSON.parse(JSON.stringify(task.template_snapshot)) : {});
    setConfigOpen(true);
  }

  async function saveConfig() {
    try {
      await api.patch(`/tasks/${taskId}`, { template_snapshot: configDraft });
      setTask((p: any) => ({ ...p, template_snapshot: configDraft }));
      setConfigOpen(false);
      message.success("配置已保存");
    } catch { message.error("保存配置失败"); }
  }

  if (loadError) return (
    <div style={{ textAlign: "center", marginTop: 80 }}>
      <Typography.Title level={4}>会议不存在或无权访问</Typography.Title>
      <Button type="primary" onClick={() => nav("/app/meetings")}>返回列表</Button>
    </div>
  );
  if (!task) return <div>加载中...</div>;

  const statusColor: Record<string, string> = {
    DRAFT: "default", READY: "blue", RECORDING: "processing",
    FINALIZING: "orange", REVIEW_REQUIRED: "gold",
    COMPLETED: "green", FAILED: "red",
  };
  const fmtTime = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
  const latestMinutes = minutes.length > 0 ? minutes[minutes.length - 1] : null;
  const ts = task.template_snapshot || {};
  const minutesSections = ts.minutes?.sections || [];
  const knowledgeTypes = ts.knowledge?.enabled_types || [];
  const minutesInstructions = ts.minutes?.custom_instructions || "";
  const knowledgeInstructions = ts.knowledge?.custom_instructions || "";

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "calc(100vh - 64px)", overflow: "hidden" }}>
      <div style={{ padding: "12px 0", display: "flex", alignItems: "center", justifyContent: "space-between", flexShrink: 0 }}>
        <Space>
          <Button size="small" onClick={() => nav("/app/meetings")}>←</Button>
          {editingTitle ? (
            <Space>
              <Input
                autoFocus
                size="small"
                value={titleDraft}
                onChange={e => setTitleDraft(e.target.value)}
                onPressEnter={saveTitle}
                style={{ width: 240 }}
              />
              <Button size="small" type="primary" icon={<CheckOutlined />} onClick={saveTitle} />
            </Space>
          ) : (
            <Space>
              <Typography.Title
                level={4}
                style={{ margin: 0, cursor: "pointer" }}
                onClick={() => { setTitleDraft(task.title); setEditingTitle(true); }}
              >
                {task.title}
              </Typography.Title>
              <Tooltip title="点击修改名称">
                <EditOutlined style={{ color: "#999", cursor: "pointer" }} onClick={() => { setTitleDraft(task.title); setEditingTitle(true); }} />
              </Tooltip>
            </Space>
          )}
          <Tag color={statusColor[task.status] || "default"}>{task.status}</Tag>
          {recording && (
            <Space size="small">
              <Tag color="red" style={{ animation: "pulse 1.5s infinite" }}>● 录音中 {fmtTime(recElapsed)}</Tag>
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                {chunks.length} 片{uploadingChunks > 0 ? ` · 上传${uploadingChunks}` : ""} · {segments.length} 段转写
              </Typography.Text>
            </Space>
          )}
          {task.status === "FINALIZING" && <Tag color="orange">处理中...</Tag>}
        </Space>
        <Space>
          <Button icon={<SettingOutlined />} onClick={openConfig}>配置</Button>
          {recording ? (
            <Button danger onClick={stopRecording}>■ 停止</Button>
          ) : (
            (task.status === "DRAFT" || task.status === "READY") && (
              <Button type="primary" onClick={startRecording}>● 开始录音</Button>
            )
          )}
          {task.status === "REVIEW_REQUIRED" && (
            <Button type="primary" onClick={async () => {
              const r = await api.post(`/tasks/${taskId}/knowledge/publish`);
              message.success(`发布 ${r.data.published.length} 条知识`);
              loadKnowledge();
            }}>发布知识</Button>
          )}
          <Popconfirm title="确认删除？" onConfirm={del}><Button danger size="small">删除</Button></Popconfirm>
        </Space>
      </div>

      {task.remarks && (
        <div style={{ marginBottom: 8, flexShrink: 0 }}>
          <Typography.Text type="secondary">备注：{task.remarks}</Typography.Text>
        </div>
      )}

      {chunks.length > 0 && !recording && (
        <div style={{ flexShrink: 0, marginBottom: 8 }}>
          <ChunkPlayer taskId={taskId!} chunks={chunks} />
        </div>
      )}

      <div style={{ display: "flex", gap: 12, flex: 1, minHeight: 0 }}>
        <div style={{ flex: 1, display: "flex", flexDirection: "column", background: "#fafafa", borderRadius: 8, overflow: "hidden" }}>
          <div style={{ padding: "8px 12px", borderBottom: "1px solid #eee", fontWeight: 600, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span>转写</span>
            <Tag>{segments.length} 段</Tag>
          </div>
          <div style={{ flex: 1, overflowY: "auto", padding: "8px 12px" }}>
            {segments.length === 0 ? (
              <Typography.Text type="secondary" style={{ display: "block", textAlign: "center", marginTop: 40 }}>
                {recording ? "等待语音识别..." : "暂无转写内容"}
              </Typography.Text>
            ) : (
              segments.map((s: any, i: number) => {
                const segStartMs = s.start_ms != null ? s.start_ms : ((s.chunk_sequence || 1) - 1) * 20000;
                const segMin = Math.floor(segStartMs / 60000);
                const segSec = Math.floor((segStartMs % 60000) / 1000);
                const timestamp = `${String(segMin).padStart(2, "0")}:${String(segSec).padStart(2, "0")}`;
                return (
                <div key={s.segment_id || i} style={{ marginBottom: 12 }}>
                  <Space size="small" style={{ marginBottom: 2 }}>
                    <Tag style={{ fontSize: 11 }}>{timestamp}</Tag>
                    {s.speaker_label && <Typography.Text type="secondary" style={{ fontSize: 11 }}>{s.speaker_label}</Typography.Text>}
                  </Space>
                  <div style={{ lineHeight: 1.7 }}>{s.edited_text || s.original_text}</div>
                </div>
                );
              })
            )}
            <div ref={transcriptEndRef} />
          </div>
        </div>

        <div style={{ flex: 1, display: "flex", flexDirection: "column", background: "#fff", borderRadius: 8, overflow: "hidden", border: "1px solid #eee" }}>
          <div style={{ padding: "8px 12px", borderBottom: "1px solid #eee", fontWeight: 600, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span>纪要</span>
            {latestMinutes && <Tag color="blue">v{latestMinutes.version}</Tag>}
          </div>
          <div style={{ flex: 1, overflowY: "auto", padding: "12px" }}>
            {latestMinutes ? (
              <div style={{ whiteSpace: "pre-wrap", lineHeight: 1.8, fontSize: 14 }}>{latestMinutes.content_markdown}</div>
            ) : (
              <Typography.Text type="secondary" style={{ display: "block", textAlign: "center", marginTop: 40 }}>
                {recording || task.status === "FINALIZING" ? "正在生成纪要..." : "暂无纪要"}
              </Typography.Text>
            )}
          </div>
        </div>

        <div style={{ flex: 1, display: "flex", flexDirection: "column", background: "#fafafa", borderRadius: 8, overflow: "hidden" }}>
          <div style={{ padding: "8px 12px", borderBottom: "1px solid #eee", fontWeight: 600, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span>知识</span>
            <Tag>{knowledge.length} 条</Tag>
          </div>
          <div style={{ flex: 1, overflowY: "auto", padding: "8px 12px" }}>
            {knowledge.length === 0 ? (
              <Typography.Text type="secondary" style={{ display: "block", textAlign: "center", marginTop: 40 }}>
                {recording || task.status === "FINALIZING" ? "正在提炼知识..." : "暂无知识"}
              </Typography.Text>
            ) : (
              knowledge.map((k: any) => (
                <Card key={k.item_id} size="small" style={{ marginBottom: 8 }} bodyStyle={{ padding: "8px 12px" }}>
                  <div style={{ marginBottom: 4 }}>
                    <Space size="small">
                      <Tag color="blue" style={{ fontSize: 11 }}>{KNOWLEDGE_LABELS[k.item_type] || k.item_type}</Tag>
                      <strong style={{ fontSize: 13 }}>{k.title}</strong>
                    </Space>
                  </div>
                  <div style={{ fontSize: 12, color: "#666", lineHeight: 1.6 }}>{k.body}</div>
                  <div style={{ marginTop: 6, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <Tag style={{ fontSize: 10 }} color={k.review_status === "PUBLISHED" ? "green" : k.review_status === "REJECTED" ? "red" : "default"}>
                      {k.review_status}
                    </Tag>
                    {k.review_status === "DRAFT" && (
                      <Space size="small">
                        <Button size="small" type="primary" onClick={async () => { await api.post(`/tasks/${taskId}/knowledge/${k.item_id}/accept`); loadKnowledge(); }}>接受</Button>
                        <Button size="small" danger onClick={async () => { await api.post(`/tasks/${taskId}/knowledge/${k.item_id}/reject`); loadKnowledge(); }}>拒绝</Button>
                      </Space>
                    )}
                  </div>
                </Card>
              ))
            )}
          </div>
        </div>
      </div>

      <Modal
        open={configOpen}
        title="会议配置"
        onCancel={() => setConfigOpen(false)}
        onOk={saveConfig}
        okText="保存"
        cancelText="取消"
        width={640}
      >
        {configDraft && (
          <Space direction="vertical" style={{ width: "100%" }} size="middle">
            <div style={{ width: "100%" }}>
              <Typography.Text strong>选择模板</Typography.Text>
              <Select
                placeholder="选择模板快速填充配置"
                style={{ width: "100%", marginTop: 4 }}
                onChange={(v) => {
                  const tmpl = templates.find(t => t.template_id === v);
                  if (tmpl) setConfigDraft(JSON.parse(JSON.stringify(tmpl.config)));
                }}
                options={templates.map(t => ({ value: t.template_id, label: t.name }))}
              />
            </div>

            <Tabs
              defaultActiveKey="minutes"
              items={[
                {
                  key: "minutes",
                  label: "纪要模板",
                  children: (
                    <Space direction="vertical" style={{ width: "100%" }} size="middle">
                      <div style={{ width: "100%" }}>
                        <Typography.Text type="secondary" style={{ fontSize: 12, display: "block", marginBottom: 4 }}>
                          自定义纪要生成的指令（保存为本次会议的模板）
                        </Typography.Text>
                        <TextArea
                          rows={4}
                          value={configDraft.minutes?.custom_instructions || ""}
                          onChange={e => setConfigDraft((d: any) => ({ ...d, minutes: { ...d.minutes, custom_instructions: e.target.value } }))}
                          placeholder="例如：请重点关注技术方案选型和风险点，纪要需包含方案对比表格"
                        />
                      </div>
                      <div style={{ width: "100%" }}>
                        <Typography.Text type="secondary" style={{ fontSize: 12 }}>章节：</Typography.Text>
                        <Space wrap size="small" style={{ marginTop: 4 }}>
                          {(configDraft.minutes?.sections || []).map((s: string) => <Tag key={s}>{s}</Tag>)}
                        </Space>
                      </div>
                      <div style={{ width: "100%" }}>
                        <Typography.Text strong>备注</Typography.Text>
                        <TextArea
                          rows={2}
                          value={task.remarks || ""}
                          onChange={e => setTask((p: any) => ({ ...p, remarks: e.target.value }))}
                          placeholder="会议备注信息"
                          onBlur={async () => {
                            try { await api.patch(`/tasks/${taskId}`, { remarks: task.remarks || "" }); } catch {}
                          }}
                        />
                      </div>
                    </Space>
                  ),
                },
                {
                  key: "knowledge",
                  label: "知识提炼",
                  children: (
                    <Space direction="vertical" style={{ width: "100%" }} size="middle">
                      <div style={{ width: "100%" }}>
                        <Typography.Text type="secondary" style={{ fontSize: 12, display: "block", marginBottom: 4 }}>
                          选择需要提取的知识类型
                        </Typography.Text>
                        <Select
                          mode="multiple"
                          style={{ width: "100%" }}
                          value={configDraft.knowledge?.enabled_types || []}
                          onChange={(v) => setConfigDraft((d: any) => ({ ...d, knowledge: { ...d.knowledge, enabled_types: v } }))}
                          options={Object.entries(KNOWLEDGE_TYPES).map(([k, v]) => ({ value: k, label: v }))}
                        />
                      </div>
                      <div style={{ width: "100%" }}>
                        <Typography.Text type="secondary" style={{ fontSize: 12, display: "block", marginBottom: 4 }}>
                          自定义知识提炼指令
                        </Typography.Text>
                        <TextArea
                          rows={3}
                          value={configDraft.knowledge?.custom_instructions || ""}
                          onChange={e => setConfigDraft((d: any) => ({ ...d, knowledge: { ...d.knowledge, custom_instructions: e.target.value } }))}
                          placeholder="例如：只提取与安全相关的内容，忽略一般性讨论"
                        />
                      </div>
                    </Space>
                  ),
                },
              ]}
            />
          </Space>
        )}
      </Modal>
    </div>
  );
}
