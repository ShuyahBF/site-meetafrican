import { createContext, useContext, useEffect, useState } from "react";
import { apiClient } from "@/lib/api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = localStorage.getItem("maf_token");
    if (!token) {
      setLoading(false);
      return;
    }
    apiClient
      .get("/auth/me")
      .then((res) => setUser(res.data))
      .catch(() => localStorage.removeItem("maf_token"))
      .finally(() => setLoading(false));
  }, []);

  const login = async (identifier, password) => {
    const res = await apiClient.post("/auth/login", { identifier, password });
    localStorage.setItem("maf_token", res.data.access_token);
    setUser(res.data.user);
    return res.data.user;
  };

  const register = async (payload) => {
    const res = await apiClient.post("/auth/register", payload);
    localStorage.setItem("maf_token", res.data.access_token);
    setUser(res.data.user);
    return res.data.user;
  };

  const logout = () => {
    localStorage.removeItem("maf_token");
    setUser(null);
  };

  const refresh = async () => {
    const res = await apiClient.get("/auth/me");
    setUser(res.data);
    return res.data;
  };

  return (
    <AuthContext.Provider value={{ user, loading, login, register, logout, refresh }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth doit être utilisé dans un <AuthProvider>");
  return ctx;
}
