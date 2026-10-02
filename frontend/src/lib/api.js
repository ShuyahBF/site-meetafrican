import axios from "axios";

// Adresse de l'API : variable VITE_API_BASE_URL si définie au build, sinon
// l'API officielle en production (https://api.beauthentik.net/api) et le
// serveur local en développement.
export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ||
  (import.meta.env.PROD ? "https://api.beauthentik.net/api" : "http://localhost:8000/api");

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

// Requêtes de FOND (rafraîchissements automatiques : compteurs, suivi, bandeaux) :
// contrôlées par le serveur mais NON comptées comme une activité du membre, sinon
// un onglet oublié ne serait jamais déconnecté pour inactivité (voir
// backend/inactivite.py). Usage : apiClient.get(url, FOND).
export const FOND = { headers: { "X-BA-Fond": "1" } };

// Motif de la dernière déconnexion forcée, affiché sur la page de connexion
export const MOTIF_DECONNEXION_KEY = "ba_motif_deconnexion";

// Session fermée par le serveur (limite d'appareils, fermeture depuis un autre
// appareil ou par l'administrateur, inactivité) : le jeton est effacé et le
// membre revient à la page de connexion avec le motif.
const PREFIXES_SESSION_FERMEE = ["Session fermée", "Session expirée après inactivité"];
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    const detail = error?.response?.data?.detail;
    if (
      error?.response?.status === 401 &&
      typeof detail === "string" &&
      PREFIXES_SESSION_FERMEE.some((p) => detail.startsWith(p)) &&
      localStorage.getItem("maf_token")
    ) {
      try {
        localStorage.removeItem("maf_token");
        sessionStorage.setItem(MOTIF_DECONNEXION_KEY, detail);
      } catch { /* stockage indisponible */ }
      if (window.location.pathname !== "/connexion") window.location.assign("/connexion");
    }
    return Promise.reject(error);
  },
);

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
