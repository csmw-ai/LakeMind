import { useEffect } from "react";
import { Layout, Menu, Dropdown, Button, Space } from "antd";
import { Outlet, useNavigate, useLocation } from "react-router-dom";
import { useAuth } from "../state/auth";

const { Header, Content } = Layout;

export default function AppLayout() {
  const nav = useNavigate();
  const loc = useLocation();
  const { user, fetchMe, logout } = useAuth();

  useEffect(() => { if (!user) fetchMe(); }, []);

  if (!user) return <div>加载中...</div>;

  const menuItems = [
    { key: "/app/meetings", label: "我的会议" },
    { key: "/app/meetings/new", label: "新建会议" },
    { key: "/app/templates", label: "我的模板" },
  ];

  return (
    <Layout style={{ minHeight: "100vh" }}>
      <Header style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <Space>
          <span style={{ color: "#fff", fontSize: 18, fontWeight: "bold" }}>Meeting Agent</span>
          <Menu
            theme="dark"
            mode="horizontal"
            selectedKeys={[loc.pathname]}
            items={menuItems}
            onClick={(e) => nav(e.key)}
            style={{ flex: 1, minWidth: 0 }}
          />
        </Space>
        <Dropdown menu={{ items: [
          { key: "logout", label: "退出", onClick: logout },
        ]}}>
          <Button type="text" style={{ color: "#fff" }}>{user.principal_id.slice(0, 12)}...</Button>
        </Dropdown>
      </Header>
      <Content style={{ padding: 24, width: "100%" }}>
        <Outlet />
      </Content>
    </Layout>
  );
}
