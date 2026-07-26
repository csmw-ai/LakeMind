import { FormEvent } from "react";
import { Card, Form, Input, Button, Typography, Alert } from "antd";
import { useNavigate, Link } from "react-router-dom";
import { api } from "../api/client";

export default function Register() {
  const nav = useNavigate();

  async function onFinish(e: FormEvent) {
    e.preventDefault();
    const form = e.target as HTMLFormElement;
    const fd = new FormData(form);
    const password = fd.get("password") as string;
    const confirm = fd.get("confirm") as string;
    if (password !== confirm) { alert("密码不一致"); return; }
    if (password.length < 8) { alert("密码至少 8 位"); return; }
    try {
      await api.post("/auth/register", {
        username: fd.get("username"),
        password,
        display_name: fd.get("display_name") || fd.get("username"),
      });
      nav("/app/meetings");
    } catch (err: any) {
      alert(err?.response?.data?.detail || "注册失败");
    }
  }

  return (
    <div style={{ maxWidth: 400, margin: "80px auto" }}>
      <Card title={<Typography.Title level={3}>注册 Meeting Agent</Typography.Title>}>
        <Alert type="info" message="录音将由 AI 处理，结果可能存在错误，请审核后发布知识。" style={{ marginBottom: 16 }} />
        <form onSubmit={onFinish}>
          <Form.Item label="用户名"><Input name="username" required /></Form.Item>
          <Form.Item label="显示名称"><Input name="display_name" /></Form.Item>
          <Form.Item label="密码（至少 8 位）"><Input.Password name="password" required /></Form.Item>
          <Form.Item label="确认密码"><Input.Password name="confirm" required /></Form.Item>
          <Button type="primary" htmlType="submit" block>注册</Button>
        </form>
        <div style={{ marginTop: 16, textAlign: "center" }}>
          已有账号？<Link to="/auth/login">登录</Link>
        </div>
      </Card>
    </div>
  );
}
