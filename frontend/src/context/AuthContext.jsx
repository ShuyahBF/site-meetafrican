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

  // tiktokLien : code de liaison TikTok (« Continuer avec TikTok » sur un compte existant)
  const login = async (identifier, password, tiktokLien = null) => {
    const res = await apiClient.post("/auth/login", { identifier, password, tiktok_lien: tiktokLien });
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

  // Connexion directe après « Continuer avec TikTok » (compte déjà lié)
  const loginWithToken = (data) => {
    localStorage.setItem("maf_token", data.access_token);
    setUser(data.user);
    return data.user;
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
    <AuthContext.Provider value={{ user, loading, login, loginWithToken, register, logout, refresh }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth doit être utilisé dans un <AuthProvider>");
  return ctx;
}
