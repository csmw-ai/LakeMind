import { create } from "zustand";
import { api } from "../api/client";

interface User {
  principal_id: string;
  tenant_id: string;
  roles: string[];
  capabilities: string[];
}

interface AuthState {
  user: User | null;
  loading: boolean;
  fetchMe: () => Promise<void>;
  logout: () => Promise<void>;
}

export const useAuth = create<AuthState>((set) => ({
  user: null,
  loading: true,
  fetchMe: async () => {
    try {
      const r = await api.get("/auth/me");
      set({ user: r.data, loading: false });
    } catch {
      set({ user: null, loading: false });
    }
  },
  logout: async () => {
    await api.post("/auth/logout");
    set({ user: null });
    window.location.href = "/auth/login";
  },
}));
