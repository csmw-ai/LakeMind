import { Table, Tag, Card, Tabs, Button, Modal, Form, Input, InputNumber, Select, Space, message, Descriptions, Tooltip, Popconfirm, Radio } from 'antd';
import { useEffect, useState } from 'react';
import { PlusOutlined, EditOutlined, ExperimentOutlined, DeleteOutlined } from '@ant-design/icons';
import { api } from '../api/client';

interface TestResult {
  model_id: string;
  name: string;
  model_type: string;
  source: string;
  success: boolean;
  latency_ms: number | null;
  error: string | null;
  response_preview: string | null;
  health_status: string;
}

const MODEL_TYPES = ['chat', 'embedding', 'asr'];
const LOCAL_BACKENDS = ['fastembed', 'sensevoice-funasr', 'faster-whisper'];
const PROVIDER_TYPES = ['openai', 'anthropic', 'ollama', 'azure', 'gemini', 'bedrock'];

export default function ModelServing() {
  const [models, setModels] = useState<any[]>([]);
  const [profiles, setProfiles] = useState<any[]>([]);
  const [providers, setProviders] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [modelModalOpen, setModelModalOpen] = useState(false);
  const [profileModalOpen, setProfileModalOpen] = useState(false);
  const [providerModalOpen, setProviderModalOpen] = useState(false);
  const [editingModel, setEditingModel] = useState<any>(null);
  const [editingProfile, setEditingProfile] = useState<any>(null);
  const [editingProvider, setEditingProvider] = useState<any>(null);
  const [submitting, setSubmitting] = useState(false);
  const [testing, setTesting] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<TestResult | null>(null);
  const [modelForm] = Form.useForm();
  const [profileForm] = Form.useForm();
  const [providerForm] = Form.useForm();
  const [sourceType, setSourceType] = useState<string>('external');

  const loadData = () => {
    setLoading(true);
    Promise.all([
      api.get('/models').then(r => Array.isArray(r.data) ? r.data : r.data?.data || r.data?.items || []),
      api.get('/profiles').then(r => Array.isArray(r.data) ? r.data : r.data?.data || r.data?.items || []).catch(() => []),
      api.get('/providers').then(r => Array.isArray(r.data) ? r.data : r.data?.data || r.data?.items || []).catch(() => []),
    ]).then(([m, p, pv]) => { setModels(m); setProfiles(p); setProviders(pv); }).finally(() => setLoading(false));
  };

  useEffect(() => { loadData(); }, []);

  async function handleTest(modelId: string) {
    setTesting(modelId);
    setTestResult(null);
    try {
      const r = await api.post(`/models/${modelId}/test`);
      setTestResult(r.data);
      if (r.data.success) message.success(`Test passed (${r.data.latency_ms}ms)`);
      else message.error(`Test failed: ${r.data.error || ''}`);
      loadData();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || 'Test failed');
    } finally { setTesting(null); }
  }

  function openAddModel() {
    setEditingModel(null);
    setSourceType('external');
    modelForm.resetFields();
    modelForm.setFieldsValue({ source: 'external', model_type: 'chat', priority: 100, status: 'enabled' });
    setModelModalOpen(true);
  }

  function openEditModel(record: any) {
    setEditingModel(record);
    const src = record.source || 'external';
    setSourceType(src);
    modelForm.setFieldsValue({
      name: record.name,
      model_type: record.model_type,
      provider_id: record.provider_id,
      provider: record.provider,
      source: src,
      model_path: record.model_path,
      config: record.model_config ? JSON.stringify(record.model_config) : '{}',
      capabilities: (record.capabilities || []).join(', '),
      context_length: record.context_length,
      embedding_dim: record.embedding_dim,
      priority: record.priority,
    });
    setModelModalOpen(true);
  }

  async function handleSaveModel() {
    try {
      const values = await modelForm.validateFields();
      setSubmitting(true);
      const payload: any = {
        name: values.name,
        model_type: values.model_type,
        source: values.source,
        priority: values.priority || 100,
      };
      if (values.source === 'external') {
        payload.provider_id = values.provider_id;
        payload.provider = providers.find(p => p.provider_id === values.provider_id)?.name || '';
        payload.context_length = values.context_length;
      } else {
        payload.provider = values.provider;
        payload.model_path = values.model_path;
        payload.config = values.config ? JSON.parse(values.config) : {};
        payload.embedding_dim = values.embedding_dim;
      }
      if (values.capabilities) payload.capabilities = values.capabilities.split(',').map((s: string) => s.trim());

      if (editingModel) {
        await api.put(`/models/${editingModel.model_id}`, payload);
        message.success('Model updated');
      } else {
        await api.post('/models', payload);
        message.success('Model created');
      }
      setModelModalOpen(false);
      loadData();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e?.message || 'Failed to save model');
    } finally { setSubmitting(false); }
  }

  async function handleDeleteModel(modelId: string) {
    try {
      await api.delete(`/models/${modelId}`);
      message.success('Model deleted');
      loadData();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || 'Failed to delete model');
    }
  }

  const toggleModel = async (id: string, action: 'enable' | 'disable') => {
    try {
      await api.post(`/models/${id}/${action}`);
      message.success(`Model ${action}d`);
      loadData();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || `Failed to ${action} model`);
    }
  };

  function openAddProvider() {
    setEditingProvider(null);
    providerForm.resetFields();
    providerForm.setFieldsValue({ type: 'openai', status: 'enabled' });
    setProviderModalOpen(true);
  }

  function openEditProvider(record: any) {
    setEditingProvider(record);
    providerForm.setFieldsValue({
      name: record.name,
      type: record.type,
      base_url: record.base_url,
      api_key: record.api_key,
      status: record.status,
    });
    setProviderModalOpen(true);
  }

  async function handleSaveProvider() {
    try {
      const values = await providerForm.validateFields();
      setSubmitting(true);
      if (editingProvider) {
        await api.put(`/providers/${editingProvider.provider_id}`, values);
        message.success('Provider updated');
      } else {
        await api.post('/providers', values);
        message.success('Provider created');
      }
      setProviderModalOpen(false);
      loadData();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || 'Failed to save provider');
    } finally { setSubmitting(false); }
  }

  async function handleDeleteProvider(providerId: string) {
    try {
      await api.delete(`/providers/${providerId}`);
      message.success('Provider deleted');
      loadData();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || 'Failed to delete provider');
    }
  }

  function openAddProfile() {
    setEditingProfile(null);
    profileForm.resetFields();
    setProfileModalOpen(true);
  }

  function openEditProfile(record: any) {
    setEditingProfile(record);
    profileForm.setFieldsValue({
      name: record.name,
      model_type: record.model_type,
      model_id: record.model_id,
      fallback_model_id: record.fallback_model_id,
      description: record.description,
    });
    setProfileModalOpen(true);
  }

  async function handleSaveProfile() {
    try {
      const values = await profileForm.validateFields();
      setSubmitting(true);
      if (editingProfile) {
        await api.put(`/profiles/${editingProfile.profile_id}`, values);
        message.success('Profile updated');
      } else {
        await api.post('/profiles', values);
        message.success('Profile created');
      }
      setProfileModalOpen(false);
      loadData();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || 'Failed to save profile');
    } finally { setSubmitting(false); }
  }

  async function handleDeleteProfile(profileId: string) {
    try {
      await api.delete(`/profiles/${profileId}`);
      message.success('Profile deleted');
      loadData();
    } catch (e: any) {
      message.error(e?.response?.data?.detail || 'Failed to delete profile');
    }
  }

  const providerColumns = [
    { title: 'Name', dataIndex: 'name', key: 'name', render: (v: string) => <strong>{v}</strong> },
    { title: 'Type', dataIndex: 'type', key: 'type', render: (v: string) => <Tag color="cyan">{v}</Tag> },
    { title: 'Base URL', dataIndex: 'base_url', key: 'base_url', ellipsis: true, render: (v: string) => v ? <Tooltip title={v}>{v}</Tooltip> : '—' },
    { title: 'API Key', dataIndex: 'api_key', key: 'api_key', render: (v: string) => v ? '••••••' : '—' },
    { title: 'Status', dataIndex: 'status', key: 'status', render: (v: string) => <Tag color={v === 'enabled' ? 'green' : 'red'}>{v}</Tag> },
    {
      title: 'Actions', key: 'actions', width: 120,
      render: (_: any, record: any) => (
        <Space size="small">
          <Button size="small" type="link" icon={<EditOutlined />} onClick={() => openEditProvider(record)}>Edit</Button>
          <Popconfirm title="Delete this provider?" onConfirm={() => handleDeleteProvider(record.provider_id)}>
            <Button size="small" type="link" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  const modelColumns = [
    { title: 'Name', dataIndex: 'name', key: 'name', render: (v: string) => <strong>{v}</strong> },
    { title: 'Type', dataIndex: 'model_type', key: 'model_type', render: (v: string) => <Tag color="purple">{v}</Tag> },
    {
      title: 'Provider', key: 'provider', render: (_: any, record: any) => {
        if (record.source === 'external') return record.provider_name || record.provider || '—';
        return <Tag color="blue">{record.provider}</Tag>;
      },
    },
    { title: 'Source', dataIndex: 'source', key: 'source', render: (v: string) => <Tag color={v === 'local' ? 'blue' : 'green'}>{v}</Tag> },
    { title: 'Status', dataIndex: 'status', key: 'status', render: (v: string) => <Tag color={v === 'enabled' ? 'green' : 'red'}>{v}</Tag> },
    { title: 'Health', dataIndex: 'health_status', key: 'health_status', render: (v: string) => <Tag color={v === 'healthy' ? 'green' : v === 'unhealthy' ? 'red' : 'default'}>{v}</Tag> },
    {
      title: 'Detail', key: 'detail', ellipsis: true,
      render: (_: any, record: any) => {
        if (record.source === 'external') return <Tooltip title={record.provider_base_url}>{record.provider_type ? `${record.provider_type}/${record.name}` : record.provider}</Tooltip>;
        return <Tooltip title={record.model_path}>{record.model_path || '—'}</Tooltip>;
      },
    },
    {
      title: 'Actions', key: 'actions', width: 240,
      render: (_: any, record: any) => (
        <Space size="small">
          <Button size="small" type="link" icon={<ExperimentOutlined />}
            loading={testing === record.model_id}
            onClick={() => handleTest(record.model_id)}>Test</Button>
          <Button size="small" type="link" icon={<EditOutlined />} onClick={() => openEditModel(record)}>Edit</Button>
          <Button size="small" type="link"
            onClick={() => toggleModel(record.model_id, record.status === 'enabled' ? 'disable' : 'enable')}>
            {record.status === 'enabled' ? 'Disable' : 'Enable'}
          </Button>
          <Popconfirm title="Delete this model?" onConfirm={() => handleDeleteModel(record.model_id)}>
            <Button size="small" type="link" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  const profileColumns = [
    { title: 'Name', dataIndex: 'name', key: 'name', render: (v: string) => <Tag color="blue">{v}</Tag> },
    { title: 'Type', dataIndex: 'model_type', key: 'model_type', render: (v: string) => <Tag color="purple">{v}</Tag> },
    {
      title: 'Model', key: 'model', render: (_: any, record: any) => {
        const m = models.find(m => m.model_id === record.model_id);
        return m ? m.name : record.model_id;
      },
    },
    {
      title: 'Fallback', key: 'fallback', render: (_: any, record: any) => {
        if (!record.fallback_model_id) return '—';
        const m = models.find(m => m.model_id === record.fallback_model_id);
        return m ? m.name : record.fallback_model_id;
      },
    },
    { title: 'Tenant', dataIndex: 'tenant_id', key: 'tenant_id', render: (v: string) => v || '—' },
    {
      title: 'Actions', key: 'actions', width: 120,
      render: (_: any, record: any) => (
        <Space size="small">
          <Button size="small" type="link" icon={<EditOutlined />} onClick={() => openEditProfile(record)}>Edit</Button>
          <Popconfirm title="Delete this profile?" onConfirm={() => handleDeleteProfile(record.profile_id)}>
            <Button size="small" type="link" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <>
      <Tabs items={[
        {
          key: 'providers', label: 'Providers',
          children: (
            <Card>
              <Space style={{ marginBottom: 16 }}>
                <Button type="primary" icon={<PlusOutlined />} onClick={openAddProvider}>Add Provider</Button>
              </Space>
              <Table dataSource={providers} columns={providerColumns} rowKey="provider_id" loading={loading} pagination={{ pageSize: 20 }} size="small" />
            </Card>
          ),
        },
        {
          key: 'models', label: 'Models',
          children: (
            <Card>
              <Space style={{ marginBottom: 16 }}>
                <Button type="primary" icon={<PlusOutlined />} onClick={openAddModel}>Add Model</Button>
              </Space>
              <Table dataSource={models} columns={modelColumns} rowKey="model_id" loading={loading} pagination={{ pageSize: 20 }} size="small" />
              {testResult && (
                <Modal title="Test Result" open={!!testResult} onCancel={() => setTestResult(null)} footer={null} width={700}>
                  <Descriptions column={1} bordered size="small">
                    <Descriptions.Item label="Result"><Tag color={testResult.success ? 'green' : 'red'}>{testResult.success ? 'PASSED' : 'FAILED'}</Tag></Descriptions.Item>
                    <Descriptions.Item label="Model">{testResult.name} ({testResult.model_type})</Descriptions.Item>
                    <Descriptions.Item label="Source">{testResult.source}</Descriptions.Item>
                    <Descriptions.Item label="Latency">{testResult.latency_ms != null ? `${testResult.latency_ms}ms` : '—'}</Descriptions.Item>
                    <Descriptions.Item label="Health">{testResult.health_status}</Descriptions.Item>
                    {testResult.error && <Descriptions.Item label="Error"><span style={{ color: 'red' }}>{testResult.error}</span></Descriptions.Item>}
                    {testResult.response_preview && <Descriptions.Item label="Preview"><pre style={{ maxHeight: 200, overflow: 'auto', fontSize: 11 }}>{testResult.response_preview}</pre></Descriptions.Item>}
                  </Descriptions>
                </Modal>
              )}
            </Card>
          ),
        },
        {
          key: 'profiles', label: 'Profiles',
          children: (
            <Card>
              <Space style={{ marginBottom: 16 }}>
                <Button type="primary" icon={<PlusOutlined />} onClick={openAddProfile}>Add Profile</Button>
              </Space>
              <Table dataSource={profiles} columns={profileColumns} rowKey="profile_id" loading={loading} pagination={{ pageSize: 20 }} size="small" />
            </Card>
          ),
        },
      ]} />

      <Modal title={editingProvider ? "Edit Provider" : "Add Provider"} open={providerModalOpen} onOk={handleSaveProvider} onCancel={() => setProviderModalOpen(false)} confirmLoading={submitting} width={500}>
        <Form form={providerForm} layout="vertical">
          <Form.Item name="name" label="Provider Name" rules={[{ required: true }]}><Input placeholder="e.g. modelarts, openai, ollama" /></Form.Item>
          <Form.Item name="type" label="Type" rules={[{ required: true }]}>
            <Select options={PROVIDER_TYPES.map(t => ({ value: t }))} />
          </Form.Item>
          <Form.Item name="base_url" label="Base URL"><Input placeholder="https://api.openai.com/v1" /></Form.Item>
          <Form.Item name="api_key" label="API Key"><Input.Password placeholder="sk-xxx" /></Form.Item>
          <Form.Item name="status" label="Status" rules={[{ required: true }]}>
            <Select options={[{ value: 'enabled' }, { value: 'disabled' }]} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal title={editingModel ? "Edit Model" : "Add Model"} open={modelModalOpen} onOk={handleSaveModel} onCancel={() => setModelModalOpen(false)} confirmLoading={submitting} width={600}>
        <Form form={modelForm} layout="vertical">
          <Form.Item name="name" label="Name" rules={[{ required: true }]}><Input placeholder="e.g. deepseek-v4-flash" /></Form.Item>
          <Form.Item name="model_type" label="Type" rules={[{ required: true }]}>
            <Select options={MODEL_TYPES.map(t => ({ value: t }))} />
          </Form.Item>
          <Form.Item name="source" label="Source" rules={[{ required: true }]}>
            <Radio.Group onChange={(e) => setSourceType(e.target.value)}>
              <Radio.Button value="external">External API</Radio.Button>
              <Radio.Button value="local">Local (offline files)</Radio.Button>
            </Radio.Group>
          </Form.Item>

          {sourceType === 'external' ? (
            <>
              <Form.Item name="provider_id" label="Provider" rules={[{ required: true }]}>
                <Select
                  placeholder="Select a provider"
                  options={providers.map(p => ({ value: p.provider_id, label: `${p.name} (${p.type})` }))}
                />
              </Form.Item>
              <Form.Item name="context_length" label="Context Length"><InputNumber style={{ width: '100%' }} /></Form.Item>
            </>
          ) : (
            <>
              <Form.Item name="provider" label="Backend" rules={[{ required: true }]}>
                <Select options={LOCAL_BACKENDS.map(b => ({ value: b }))} />
              </Form.Item>
              <Form.Item name="model_path" label="Model Path" rules={[{ required: true }]}><Input placeholder="/data/asr_models/whisper-large-v3-turbo" /></Form.Item>
              <Form.Item name="config" label="Config (JSON)"><Input.TextArea rows={2} placeholder='{"device": "cpu", "compute_type": "int8"}' /></Form.Item>
              <Form.Item name="embedding_dim" label="Embedding Dim"><InputNumber style={{ width: '100%' }} /></Form.Item>
            </>
          )}

          <Form.Item name="capabilities" label="Capabilities (comma-separated)"><Input placeholder="chat, vision" /></Form.Item>
          <Form.Item name="priority" label="Priority" initialValue={100}><InputNumber style={{ width: '100%' }} /></Form.Item>
        </Form>
      </Modal>

      <Modal title={editingProfile ? "Edit Profile" : "Add Profile"} open={profileModalOpen} onOk={handleSaveProfile} onCancel={() => setProfileModalOpen(false)} confirmLoading={submitting}>
        <Form form={profileForm} layout="vertical">
          <Form.Item name="name" label="Profile Name" rules={[{ required: true }]}><Input placeholder="e.g. meeting-minutes" /></Form.Item>
          <Form.Item name="model_type" label="Type" rules={[{ required: true }]}>
            <Select options={MODEL_TYPES.map(t => ({ value: t }))} />
          </Form.Item>
          <Form.Item name="model_id" label="Model" rules={[{ required: true }]}>
            <Select options={models.map(m => ({ value: m.model_id, label: `${m.name} (${m.model_type}) [${m.status}]` }))} />
          </Form.Item>
          <Form.Item name="fallback_model_id" label="Fallback Model">
            <Select allowClear options={models.map(m => ({ value: m.model_id, label: m.name }))} />
          </Form.Item>
          <Form.Item name="description" label="Description"><Input /></Form.Item>
        </Form>
      </Modal>
    </>
  );
}
