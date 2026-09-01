import { createContext, useContext, useEffect, useState } from "react";
import { apiClient } from "@/lib/api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // CRITICAL: si on revient d'une OAuth callback (session_id dans le hash),
    // c'est AuthCallback qui va échanger le token et poser le cookie ; on
    // n'appelle PAS /auth/me ici (sinon 401 avant le set-cookie).
    // REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
    if (window.location.hash?.includes("session_id=")) {
      setLoading(false);
      return;
    }
    // Deux modes coexistent : Bearer JWT local (localStorage) OU cookie
    // httpOnly de session Google. On tente /auth/me qui accepte les deux ;
    // 401 => non connecté (silencieux).
    apiClient
      .get("/auth/me")
      .then((res) => setUser(res.data))
      .catch(() => {
        localStorage.removeItem("maf_token");
      })
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

  const logout = async () => {
    try {
      await apiClient.post("/auth/logout");
    } catch { /* ignore : on nettoie côté client dans tous les cas */ }
    localStorage.removeItem("maf_token");
    setUser(null);
  };

  const refresh = async () => {
    const res = await apiClient.get("/auth/me");
    setUser(res.data);
    return res.data;
  };

  // Appelé par AuthCallback après échange réussi du session_id.
  const applyGoogleSession = (userObj) => {
    // Le backend a posé le cookie httpOnly ; on nettoie l'ancien JWT local
    // pour éviter que l'axios interceptor n'envoie un Bearer expiré.
    localStorage.removeItem("maf_token");
    setUser(userObj);
  };

  return (
    <AuthContext.Provider value={{ user, loading, login, register, logout, refresh, applyGoogleSession }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth doit être utilisé dans un <AuthProvider>");
  return ctx;
}
