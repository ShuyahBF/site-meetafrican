import axios from "axios";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api";

export const apiClient = axios.create({ baseURL: API_BASE_URL });

// ws(s):// équivalent de l'URL de l'API, pour le chat temps réel.
export const WS_BASE_URL = API_BASE_URL.replace(/^http/, "ws");

apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem("maf_token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

/**
 * FastAPI renvoie `detail` soit comme une chaîne (HTTPException), soit comme
 * un tableau d'objets d'erreur de validation Pydantic ({loc, msg, type, ...}).
 * On ne rend jamais l'un de ces objets directement dans du JSX — toujours
 * passer par cette fonction pour obtenir une chaîne affichable.
 */
export function extractErrorMessage(err, fallback = "Une erreur est survenue") {
  const detail = err?.response?.data?.detail;
  if (!detail) return fallback;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail.map((d) => (typeof d === "string" ? d : d.msg || JSON.stringify(d))).join(" · ");
  }
  return fallback;
}
