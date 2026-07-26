import { useEffect, useState } from "react";
import { Card, Col, Row, Tag, Button, Space, Input, Select, Empty, Skeleton, Typography } from "antd";
import {
  PlusOutlined,
  AudioOutlined,
  UploadOutlined,
  ClockCircleOutlined,
  FieldTimeOutlined,
  ExclamationCircleOutlined,
  CheckCircleOutlined,
  SoundOutlined,
} from "@ant-design/icons";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";

const STATUS_META: Record<string, { label: string; color: string; accent: string; bg: string }> = {
  DRAFT: { label: "草稿", color: "default", accent: "#bfbfbf", bg: "#fafafa" },
  READY: { label: "就绪", color: "blue", accent: "#1677ff", bg: "#e6f4ff" },
  RECORDING: { label: "录音中", color: "processing", accent: "#722ed1", bg: "#f9f0ff" },
  FINALIZING: { label: "处理中", color: "orange", accent: "#fa8c16", bg: "#fff7e6" },
  REVIEW_REQUIRED: { label: "待审核", color: "gold", accent: "#faad14", bg: "#fffbe6" },
  COMPLETED: { label: "已完成", color: "green", accent: "#52c41a", bg: "#f6ffed" },
  FAILED: { label: "失败", color: "red", accent: "#ff4d4f", bg: "#fff2f0" },
  DELETED: { label: "已删除", color: "default", accent: "#bfbfbf", bg: "#fafafa" },
};

function fmtDuration(ms?: number) {
  if (!ms) return "-";
  const s = Math.floor(ms / 1000);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

function fmtTime(t?: string) {
  if (!t) return "-";
  const d = new Date(t);
  const now = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  if (d.toDateString() === now.toDateString()) return `今天 ${pad(d.getHours())}:${pad(d.getMinutes())}`;
  const yest = new Date(now);
  yest.setDate(now.getDate() - 1);
  if (d.toDateString() === yest.toDateString()) return `昨天 ${pad(d.getHours())}:${pad(d.getMinutes())}`;
  return `${d.getMonth() + 1}/${d.getDate()} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export default function Meetings() {
  const nav = useNavigate();
  const [tasks, setTasks] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [search, setSearch] = useState("");

  useEffect(() => { load(); }, [statusFilter, search]);

  async function load() {
    setLoading(true);
    const params: any = {};
    if (statusFilter) params.status = statusFilter;
    if (search) params.q = search;
    const r = await api.get("/tasks", { params });
    setTasks(r.data.items || []);
    setLoading(false);
  }

  const counts = {
    total: tasks.length,
    recording: tasks.filter(t => t.status === "RECORDING").length,
    review: tasks.filter(t => t.status === "REVIEW_REQUIRED").length,
    completed: tasks.filter(t => t.status === "COMPLETED").length,
  };

  const statCards = [
    { key: "total", label: "全部", value: counts.total, icon: <SoundOutlined />, color: "#1677ff" },
    { key: "recording", label: "录音中", value: counts.recording, icon: <AudioOutlined />, color: "#722ed1" },
    { key: "review", label: "待审核", value: counts.review, icon: <ExclamationCircleOutlined />, color: "#faad14" },
    { key: "completed", label: "已完成", value: counts.completed, icon: <CheckCircleOutlined />, color: "#52c41a" },
  ];

  return (
    <div>
      <div
        style={{
          background: "linear-gradient(135deg, #1677ff 0%, #722ed1 100%)",
          borderRadius: 12,
          padding: "20px 24px",
          marginBottom: 16,
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          boxShadow: "0 6px 16px rgba(22, 119, 255, 0.18)",
        }}
      >
        <div>
          <Typography.Title level={3} style={{ margin: 0, color: "#fff" }}>我的会议</Typography.Title>
          <Typography.Text style={{ color: "rgba(255,255,255,0.85)", fontSize: 13 }}>
            实时录音 · 智能纪要 · 知识萃取
          </Typography.Text>
        </div>
        <Button
          type="primary"
          size="large"
          icon={<PlusOutlined />}
          onClick={() => nav("/app/meetings/new")}
          style={{ background: "#fff", color: "#1677ff", border: "none", fontWeight: 600, boxShadow: "0 4px 12px rgba(0,0,0,0.15)" }}
        >
          新建会议
        </Button>
      </div>

      <Row gutter={12} style={{ marginBottom: 16 }}>
        {statCards.map(s => (
          <Col key={s.key} xs={12} sm={6}>
            <Card size="small" style={{ borderRadius: 8, border: "none", boxShadow: "0 1px 4px rgba(0,0,0,0.06)" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                <div style={{ width: 40, height: 40, borderRadius: 8, background: `${s.color}14`, color: s.color, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 18 }}>
                  {s.icon}
                </div>
                <div>
                  <div style={{ fontSize: 22, fontWeight: 700, lineHeight: 1.1 }}>{s.value}</div>
                  <div style={{ fontSize: 12, color: "#8c8c8c" }}>{s.label}</div>
                </div>
              </div>
            </Card>
          </Col>
        ))}
      </Row>

      <Space style={{ marginBottom: 16, width: "100%", justifyContent: "space-between" }} wrap>
        <Space wrap>
          <Select
            placeholder="状态筛选"
            allowClear
            style={{ width: 150 }}
            onChange={(v) => setStatusFilter(v || "")}
            options={[
              { value: "RECORDING", label: "录音中" },
              { value: "FINALIZING", label: "处理中" },
              { value: "REVIEW_REQUIRED", label: "待审核" },
              { value: "COMPLETED", label: "已完成" },
              { value: "FAILED", label: "失败" },
            ]}
          />
          <Input.Search placeholder="搜索会议" onSearch={setSearch} style={{ width: 220 }} allowClear />
        </Space>
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          {loading ? "加载中…" : `共 ${tasks.length} 场`}
        </Typography.Text>
      </Space>

      {loading ? (
        <Row gutter={[16, 16]}>
          {Array.from({ length: 8 }).map((_, i) => (
            <Col key={i} xs={24} sm={12} md={8} lg={6}>
              <Card style={{ borderRadius: 10 }}><Skeleton active paragraph={{ rows: 2 }} /></Card>
            </Col>
          ))}
        </Row>
      ) : tasks.length === 0 ? (
        <Card style={{ borderRadius: 12, border: "1px dashed #d9d9d9", background: "#fafafa" }}>
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={<Typography.Text type="secondary">暂无会议，点击右上角「新建会议」开始</Typography.Text>}
          >
            <Button type="primary" icon={<PlusOutlined />} onClick={() => nav("/app/meetings/new")}>新建会议</Button>
          </Empty>
        </Card>
      ) : (
        <Row gutter={[16, 16]}>
          {tasks.map((t: any) => {
            const meta = STATUS_META[t.status] || STATUS_META.DRAFT;
            const isLive = t.source_type === "LIVE";
            return (
              <Col key={t.task_id} xs={24} sm={12} md={8} lg={6}>
                <Card
                  hoverable
                  onClick={() => nav(`/app/meetings/${t.task_id}`)}
                  style={{
                    borderRadius: 10,
                    overflow: "hidden",
                    border: "1px solid #f0f0f0",
                    transition: "all 0.25s ease",
                  }}
                  bodyStyle={{ padding: 0 }}
                >
                  <div style={{ height: 4, background: meta.accent }} />
                  <div style={{ padding: "14px 16px" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
                      <Tag color={meta.color} style={{ margin: 0 }}>
                        {t.status === "RECORDING" && <span style={{ animation: "pulse 1.5s infinite" }}>● </span>}
                        {meta.label}
                      </Tag>
                      <Tooltip text={isLive ? "实时录音" : "上传"} icon={isLive ? <AudioOutlined /> : <UploadOutlined />} />
                    </div>

                    <Typography.Text
                      strong
                      style={{ fontSize: 15, display: "block", lineHeight: 1.4 }}
                      ellipsis={{ tooltip: t.title }}
                    >
                      {t.title || "未命名会议"}
                    </Typography.Text>

                    <div style={{ marginTop: 12, paddingTop: 10, borderTop: "1px solid #f5f5f5", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <Space size="small" style={{ color: "#8c8c8c", fontSize: 12 }}>
                        <ClockCircleOutlined />
                        <span>{fmtTime(t.created_at)}</span>
                      </Space>
                      <Space size="small" style={{ color: "#8c8c8c", fontSize: 12 }}>
                        <FieldTimeOutlined />
                        <span>{fmtDuration(t.duration_ms)}</span>
                      </Space>
                    </div>
                  </div>
                </Card>
              </Col>
            );
          })}
        </Row>
      )}
    </div>
  );
}

function Tooltip({ text, icon }: { text: string; icon: React.ReactNode }) {
  return (
    <span title={text} style={{ color: "#bfbfbf", fontSize: 14, cursor: "help" }}>
      {icon}
    </span>
  );
}
