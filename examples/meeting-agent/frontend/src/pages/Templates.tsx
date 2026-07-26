import { useEffect, useState } from "react";
import { Card, List, Button, Tag, Modal, Input } from "antd";
import { api } from "../api/client";

export default function Templates() {
  const [templates, setTemplates] = useState<any[]>([]);
  const [preview, setPreview] = useState<any>(null);

  useEffect(() => { load(); }, []);
  async function load() {
    const r = await api.get("/templates");
    setTemplates(r.data.items || []);
  }

  async function clone(id: string) {
    await api.post(`/templates/${id}/clone`);
    load();
  }
  async function archive(id: string) {
    await api.post(`/templates/${id}/archive`);
    load();
  }

  return (
    <div>
      <List
        dataSource={templates}
        renderItem={(t: any) => (
          <List.Item actions={[
            <Button size="small" onClick={() => setPreview(t)}>预览</Button>,
            t.is_builtin ? <Button size="small" onClick={() => clone(t.template_id)}>复制</Button> : null,
            !t.is_builtin ? <Button size="small" danger onClick={() => archive(t.template_id)}>归档</Button> : null,
          ].filter(Boolean)}>
            <List.Item.Meta
              title={<Space><span>{t.name}</span>{t.is_builtin && <Tag color="blue">内置</Tag>}</Space>}
              description={t.description}
            />
          </List.Item>
        )}
      />
      <Modal open={!!preview} title={preview?.name} onCancel={() => setPreview(null)} footer={null} width={600}>
        {preview && <pre style={{ whiteSpace: "pre-wrap" }}>{JSON.stringify(preview.config, null, 2)}</pre>}
      </Modal>
    </div>
  );
}

import { Space } from "antd";
