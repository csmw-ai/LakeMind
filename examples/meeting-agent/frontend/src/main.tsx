import { createRoot } from "react-dom/client";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { useEffect } from "react";
import { useAuth } from "./state/auth";
import Login from "./pages/Login";
import Register from "./pages/Register";
import AppLayout from "./components/AppLayout";
import Meetings from "./pages/Meetings";
import NewMeeting from "./pages/NewMeeting";
import TaskDetail from "./pages/TaskDetail";
import Templates from "./pages/Templates";

function Guard({ children }: { children: React.ReactNode }) {
  const { user, loading, fetchMe } = useAuth();
  useEffect(() => { if (loading) fetchMe(); }, []);
  if (loading) return <div>加载中...</div>;
  if (!user) return <Navigate to="/auth/login" />;
  return <>{children}</>;
}

createRoot(document.getElementById("root")!).render(
  <BrowserRouter>
    <Routes>
      <Route path="/auth/login" element={<Login />} />
      <Route path="/auth/register" element={<Register />} />
      <Route path="/app" element={<Guard><AppLayout /></Guard>}>
        <Route path="meetings" element={<Meetings />} />
        <Route path="meetings/new" element={<NewMeeting />} />
        <Route path="meetings/:taskId" element={<TaskDetail />} />
        <Route path="templates" element={<Templates />} />
      </Route>
      <Route path="*" element={<Navigate to="/app/meetings" />} />
    </Routes>
  </BrowserRouter>
);
