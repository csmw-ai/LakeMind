import { useEffect, FormEvent } from "react";
import { Card, Form, Input, Button, Typography, Alert } from "antd";
import { useNavigate, Link } from "react-router-dom";
import { api } from "../api/client";

export default function Login() {
  const nav = useNavigate();
  useEffect(() => { document.title = "登录 - Meeting Agent"; }, []);

  async function onFinish(e: FormEvent) {
    e.preventDefault();
    const form = e.target as HTMLFormElement;
    const fd = new FormData(form);
    try {
      await api.post("/auth/login", {
        username: fd.get("username"),
        password: fd.get("password"),
      });
      nav("/app/meetings");
    } catch (err: any) {
      alert(err?.response?.data?.detail || "登录失败");
    }
  }

  return (
    <div style={{ maxWidth: 400, margin: "80px auto" }}>
      <Card title={<Typography.Title level={3}>Meeting Agent 登录</Typography.Title>}>
        <form onSubmit={onFinish}>
          <Form.Item label="用户名">
            <Input name="username" required />
          </Form.Item>
          <Form.Item label="密码">
            <Input.Password name="password" required />
          </Form.Item>
          <Button type="primary" htmlType="submit" block>登录</Button>
        </form>
        <div style={{ marginTop: 16, textAlign: "center" }}>
          没有账号？<Link to="/auth/register">注册</Link>
        </div>
      </Card>
    </div>
  );
}
