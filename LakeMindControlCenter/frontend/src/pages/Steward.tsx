import { Card, Input, Button, List, Typography } from 'antd';
import { useState } from 'react';

const { Text } = Typography;

export default function Steward() {
  const [messages, setMessages] = useState<{ role: string; content: string }[]>([
    { role: 'system', content: 'Steward chat ready. Ask about platform health, inspection, or actions.' },
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);

  async function send() {
    const message = input.trim();
    if (!message) return;
    setMessages(prev => [...prev, { role: 'user', content: message }]);
    setInput('');
    setLoading(true);
    try {
      const resp = await fetch('/steward/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message }),
      });
      const data = await resp.json();
      setMessages(prev => [...prev, { role: 'assistant', content: data.response || JSON.stringify(data) }]);
    } catch {
      setMessages(prev => [...prev, { role: 'assistant', content: 'Steward 请求失败，请稍后重试。' }]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <Card title="Steward Chat" style={{ height: '100%' }}>
      <div style={{ marginBottom: 16, maxHeight: 400, overflow: 'auto' }}>
        <List
          dataSource={messages}
          renderItem={(msg) => (
            <List.Item>
              <div style={{ width: '100%' }}>
                <Text strong color={msg.role === 'user' ? '#1677ff' : undefined}>
                  {msg.role}:
                </Text>{' '}
                <Text>{msg.content}</Text>
              </div>
            </List.Item>
          )}
        />
      </div>
      <Input.Group compact>
        <Input
          style={{ width: 'calc(100% - 80px)' }}
          value={input}
          onChange={e => setInput(e.target.value)}
          onPressEnter={send}
          placeholder="Ask Steward..."
          disabled={loading}
        />
        <Button type="primary" onClick={send} loading={loading}>Send</Button>
      </Input.Group>
    </Card>
  );
}
