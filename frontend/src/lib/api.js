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

// Messages génériques de FastAPI/Starlette (jamais écrits par notre code,
// toujours en anglais) — un exemple vécu : une mauvaise URL d'API côté
// frontend a fait passer "Not Found" tel quel à l'utilisateur. On ne les
// affiche jamais directement, on retombe sur le message français par défaut.
const GENERIC_FRAMEWORK_MESSAGES = new Set([
  "not found",
  "method not allowed",
  "internal server error",
  "unauthorized",
  "forbidden",
  "unprocessable entity",
  "bad request",
]);

/**
 * FastAPI renvoie `detail` soit comme une chaîne (HTTPException — écrite en
 * français par notre code, ex. "Identifiants invalides"), soit comme un
 * tableau d'objets d'erreur de validation Pydantic ({loc, msg, type, ...},
 * toujours en anglais, ex. "field required"), soit comme un message
 * générique du framework (toujours en anglais aussi, ex. "Not Found" sur une
 * route inexistante). On ne rend jamais l'un de ces objets directement dans
 * du JSX, et on ne laisse jamais passer un message anglais non voulu —
 * toujours passer par cette fonction pour obtenir une chaîne affichable
 * dans la langue de l'interface.
 */
export function extractErrorMessage(err, fallback = "Une erreur est survenue") {
  const detail = err?.response?.data?.detail;
  if (typeof detail === "string") {
    if (GENERIC_FRAMEWORK_MESSAGES.has(detail.trim().toLowerCase())) return fallback;
    return detail;
  }
  // Erreurs de validation Pydantic : toujours en anglais et très techniques
  // (ex. "value is not a valid email address") — pas pensées pour
  // l'utilisateur final, on retombe donc sur le message français fourni.
  return fallback;
}
