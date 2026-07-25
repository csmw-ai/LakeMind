import { Card, Row, Col, Statistic, Progress, Tag, Table, Button, Space, Segmented, Tooltip, Spin, Alert, Typography, Switch, message } from 'antd';
import { BarChartOutlined, SyncOutlined, CheckCircleOutlined, CloseCircleOutlined, ClockCircleOutlined, ReloadOutlined } from '@ant-design/icons';
import { useEffect, useState, useRef, useCallback } from 'react';
import { api } from '../api/client';

const { Text } = Typography;

interface Job {
  job_id: string;
  status: string;
  tenant_id: string;
  initiator_id: string;
  skill_uri?: string;
  job_name?: string;
  task_id?: string | null;
  created_at: string;
}

interface DashboardData {
  total: number;
  succeeded: number | null;
  failed: number | null;
  running: number | null;
  pending: number | null;
  recent_jobs: Job[];
  _meta: {
    observed_at: string;
    partial: boolean;
    partial_failure: string[];
  };
}

const STATUS_COLORS: Record<string, string> = {
  SUCCEEDED: '#52c41a',
  FAILED: '#ff4d4f',
  RUNNING: '#1677ff',
  PENDING: '#faad14',
};

function ThroughputChart({ jobs }: { jobs: Job[] }) {
  const now = Date.now();
  const bucketMs = 2 * 60 * 1000;
  const numBuckets = 15;

  const buckets = Array.from({ length: numBuckets }, (_, i) => {
    const start = now - (numBuckets - i) * bucketMs;
    const end = now - (numBuckets - i - 1) * bucketMs;
    const bucketJobs = jobs.filter(j => {
      const t = new Date(j.created_at).getTime();
      return t >= start && t < end;
    });
    return {
      time: new Date(end),
      succeeded: bucketJobs.filter(j => j.status === 'SUCCEEDED').length,
      failed: bucketJobs.filter(j => j.status === 'FAILED').length,
      running: bucketJobs.filter(j => j.status === 'RUNNING').length,
      pending: bucketJobs.filter(j => j.status === 'PENDING').length,
      total: bucketJobs.length,
    };
  });

  const maxCount = Math.max(...buckets.map(b => b.total), 1);

  return (
    <div style={{ display: 'flex', alignItems: 'flex-end', gap: 3, height: 140, padding: '0 4px' }}>
      {buckets.map((b, i) => (
        <div key={i} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', height: '100%', justifyContent: 'flex-end' }}>
          <Tooltip title={`${b.time.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })} — ${b.total} 个任务`}>
            <div style={{
              width: '100%',
              height: `${(b.total / maxCount) * 100}%`,
              minHeight: b.total > 0 ? 3 : 0,
              display: 'flex',
              flexDirection: 'column',
              borderRadius: 3,
              overflow: 'hidden',
              transition: 'height 0.3s ease',
            }}>
              {b.succeeded > 0 && <div style={{ flex: b.succeeded, background: STATUS_COLORS.SUCCEEDED }} />}
              {b.failed > 0 && <div style={{ flex: b.failed, background: STATUS_COLORS.FAILED }} />}
              {b.running > 0 && <div style={{ flex: b.running, background: STATUS_COLORS.RUNNING }} />}
              {b.pending > 0 && <div style={{ flex: b.pending, background: STATUS_COLORS.PENDING }} />}
            </div>
          </Tooltip>
          <Text type="secondary" style={{ fontSize: 9, marginTop: 4, whiteSpace: 'nowrap' }}>
            {i % 3 === 0 ? b.time.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }) : ''}
          </Text>
        </div>
      ))}
    </div>
  );
}

export default function Jobs() {
  const [dashboard, setDashboard] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [refreshInterval, setRefreshInterval] = useState(10);
  const [statusFilter, setStatusFilter] = useState<string>('ALL');
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const load = useCallback(async () => {
    try {
      const resp = await api.get('/view/jobs-dashboard');
      setDashboard(resp.data);
      setError(null);
      setLastUpdated(new Date());
    } catch (err: any) {
      setError(err?.message || '加载失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    if (intervalRef.current) clearInterval(intervalRef.current);
    if (autoRefresh) {
      intervalRef.current = setInterval(load, refreshInterval * 1000);
    }
    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  }, [autoRefresh, refreshInterval, load]);

  async function retry(jobId: string) {
    try { await api.post(`/jobs/${jobId}/retry`); message.success('重试已提交'); load(); }
    catch { message.error('重试失败'); }
  }

  async function cancel(jobId: string) {
    try { await api.post(`/jobs/${jobId}/cancel`); message.success('已取消'); load(); }
    catch { message.error('取消失败'); }
  }

  if (loading && !dashboard) {
    return <div style={{ textAlign: 'center', padding: 48 }}><Spin size="large" /></div>;
  }
  if (error && !dashboard) {
    return <Alert type="error" message="加载失败" description={error} />;
  }
  if (!dashboard) return null;

  const total = dashboard.total ?? 0;
  const succeeded = dashboard.succeeded ?? 0;
  const failed = dashboard.failed ?? 0;
  const running = dashboard.running ?? 0;
  const pending = dashboard.pending ?? 0;
  const recentJobs = dashboard.recent_jobs || [];

  const succeededPct = total > 0 ? Math.round((succeeded / total) * 100) : 0;
  const failedPct = total > 0 ? Math.round((failed / total) * 100) : 0;
  const runningPct = total > 0 ? Math.round((running / total) * 100) : 0;

  const filteredJobs = statusFilter === 'ALL'
    ? recentJobs
    : recentJobs.filter(j => j.status === statusFilter);

  const statusCounts: Record<string, number> = {};
  recentJobs.forEach(j => { statusCounts[j.status] = (statusCounts[j.status] || 0) + 1; });

  const columns = [
    { title: 'Job ID', dataIndex: 'job_id', key: 'job_id', width: 140, ellipsis: true,
      render: (v: string) => <Text style={{ fontFamily: 'monospace', fontSize: 12 }}>{v}</Text> },
    { title: '状态', dataIndex: 'status', key: 'status', width: 90, render: (v: string) => {
      const color = v === 'SUCCEEDED' ? 'green' : v === 'FAILED' ? 'red' : v === 'RUNNING' ? 'blue' : 'orange';
      return <Tag color={color}>{v}</Tag>;
    }},
    { title: '任务名', dataIndex: 'job_name', key: 'job_name', width: 120, ellipsis: true },
    { title: '发起者', dataIndex: 'initiator_id', key: 'initiator_id', width: 130, ellipsis: true },
    { title: '创建时间', dataIndex: 'created_at', key: 'created_at', width: 160,
      render: (v: string) => v ? <Text style={{ fontSize: 12 }}>{new Date(v).toLocaleString('zh-CN')}</Text> : '-' },
    { title: '操作', key: 'actions', width: 120, render: (_: any, row: any) => (
      <Space>
        <Button size="small" type="link" onClick={() => retry(row.job_id)}>重试</Button>
        <Button size="small" type="link" danger onClick={() => cancel(row.job_id)}>取消</Button>
      </Space>
    )},
  ];

  return (
    <div>
      <Row justify="space-between" align="middle" style={{ marginBottom: 16 }}>
        <Col><h2 style={{ margin: 0 }}>Job 监控看板</h2></Col>
        <Col>
          <Space>
            <Switch checkedChildren="自动" unCheckedChildren="手动" checked={autoRefresh} onChange={setAutoRefresh} />
            <Segmented
              size="small"
              value={String(refreshInterval)}
              onChange={(v) => setRefreshInterval(Number(v))}
              options={[{ label: '5s', value: '5' }, { label: '10s', value: '10' }, { label: '30s', value: '30' }]}
            />
            <Button size="small" icon={<ReloadOutlined />} onClick={load}>刷新</Button>
            {lastUpdated && <Text type="secondary" style={{ fontSize: 12 }}>更新于 {lastUpdated.toLocaleTimeString('zh-CN')}</Text>}
          </Space>
        </Col>
      </Row>

      {dashboard._meta?.partial && (
        <Alert
          type="warning"
          message="部分数据源不可用"
          description={`失败: ${Array.isArray(dashboard._meta?.partial_failure) ? dashboard._meta.partial_failure.join(', ') : 'unknown'}`}
          style={{ marginBottom: 16 }}
        />
      )}

      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col span={5}>
          <Card hoverable>
            <Statistic
              title="累计任务"
              value={total}
              prefix={<BarChartOutlined style={{ color: '#1677ff' }} />}
            />
          </Card>
        </Col>
        <Col span={5}>
          <Card hoverable>
            <Statistic
              title="运行中 / 积压"
              value={running}
              prefix={<SyncOutlined spin={running > 0} style={{ color: '#1677ff' }} />}
              valueStyle={{ color: running > 0 ? '#1677ff' : undefined }}
            />
          </Card>
        </Col>
        <Col span={5}>
          <Card hoverable>
            <Statistic
              title="已完成"
              value={succeeded}
              prefix={<CheckCircleOutlined style={{ color: '#52c41a' }} />}
              valueStyle={{ color: '#52c41a' }}
              suffix={total > 0 ? <Text type="secondary" style={{ fontSize: 14 }}>{succeededPct}%</Text> : undefined}
            />
          </Card>
        </Col>
        <Col span={5}>
          <Card hoverable>
            <Statistic
              title="失败"
              value={failed}
              prefix={<CloseCircleOutlined style={{ color: '#ff4d4f' }} />}
              valueStyle={{ color: failed > 0 ? '#ff4d4f' : undefined }}
              suffix={total > 0 ? <Text type="secondary" style={{ fontSize: 14 }}>{failedPct}%</Text> : undefined}
            />
          </Card>
        </Col>
        <Col span={4}>
          <Card hoverable>
            <Statistic
              title="排队中"
              value={pending}
              prefix={<ClockCircleOutlined style={{ color: '#faad14' }} />}
              valueStyle={{ color: pending > 0 ? '#faad14' : undefined }}
            />
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col span={8}>
          <Card title="状态分布" size="small">
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', padding: '8px 0' }}>
              <Progress
                type="circle"
                percent={succeededPct}
                size={120}
                strokeColor="#52c41a"
                format={(pct) => <div style={{ textAlign: 'center' }}><div style={{ fontSize: 20, fontWeight: 600 }}>{pct}%</div><div style={{ fontSize: 11, color: '#999' }}>已完成</div></div>}
              />
              <div style={{ marginTop: 16, width: '100%' }}>
                {[
                  { label: '已完成', value: succeeded, color: STATUS_COLORS.SUCCEEDED },
                  { label: '失败', value: failed, color: STATUS_COLORS.FAILED },
                  { label: '运行中', value: running, color: STATUS_COLORS.RUNNING },
                  { label: '排队中', value: pending, color: STATUS_COLORS.PENDING },
                ].map(item => (
                  <div key={item.label} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '4px 0' }}>
                    <Space>
                      <div style={{ width: 8, height: 8, borderRadius: '50%', background: item.color }} />
                      <Text style={{ fontSize: 13 }}>{item.label}</Text>
                    </Space>
                    <Text strong style={{ fontSize: 13 }}>{item.value?.toLocaleString()}</Text>
                  </div>
                ))}
              </div>
            </div>
          </Card>
        </Col>
        <Col span={16}>
          <Card title="任务吞吐 (近 30 分钟)" size="small">
            <ThroughputChart jobs={recentJobs} />
            <div style={{ display: 'flex', justifyContent: 'center', gap: 24, marginTop: 8 }}>
              {[
                { label: '已完成', color: STATUS_COLORS.SUCCEEDED },
                { label: '失败', color: STATUS_COLORS.FAILED },
                { label: '运行中', color: STATUS_COLORS.RUNNING },
                { label: '排队中', color: STATUS_COLORS.PENDING },
              ].map(item => (
                <Space key={item.label}>
                  <div style={{ width: 10, height: 10, borderRadius: 2, background: item.color }} />
                  <Text type="secondary" style={{ fontSize: 12 }}>{item.label}</Text>
                </Space>
              ))}
            </div>
          </Card>
        </Col>
      </Row>

      <Card title="最近任务" size="small">
        <div style={{ marginBottom: 12 }}>
          <Segmented
            value={statusFilter}
            onChange={(v) => setStatusFilter(v as string)}
            options={[
              { label: `全部 ${recentJobs.length}`, value: 'ALL' },
              { label: `运行中 ${statusCounts.RUNNING || 0}`, value: 'RUNNING' },
              { label: `已完成 ${statusCounts.SUCCEEDED || 0}`, value: 'SUCCEEDED' },
              { label: `失败 ${statusCounts.FAILED || 0}`, value: 'FAILED' },
              { label: `排队 ${statusCounts.PENDING || 0}`, value: 'PENDING' },
            ]}
          />
        </div>
        <Table
          dataSource={filteredJobs}
          columns={columns}
          rowKey="job_id"
          loading={loading}
          pagination={{ pageSize: 15, size: 'small' }}
          size="small"
        />
      </Card>
    </div>
  );
}
