import { useEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { apiClient, extractErrorMessage } from "@/lib/api";

/**
 * Route de callback OAuth Emergent — reçoit `#session_id=...` dans l'URL,
 * appelle POST /api/auth/session (le backend récupère le profil Google et
 * pose un cookie httpOnly session_token), puis redirige vers /decouverte
 * (ou /admin si compte staff).
 *
 * REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
 */
export default function AuthCallback() {
  const location = useLocation();
  const navigate = useNavigate();
  const { applyGoogleSession } = useAuth();
  const [error, setError] = useState("");
  // useRef (pas useState) : StrictMode monte deux fois — évite le double
  // échange qui invaliderait le premier cookie.
  const hasProcessed = useRef(false);

  useEffect(() => {
    if (hasProcessed.current) return;
    hasProcessed.current = true;

    const hash = location.hash || window.location.hash || "";
    const match = hash.match(/session_id=([^&]+)/);
    if (!match) {
      navigate("/connexion", { replace: true });
      return;
    }
    const sessionId = decodeURIComponent(match[1]);

    (async () => {
      try {
        const res = await apiClient.post(
          "/auth/session",
          null,
          { headers: { "X-Session-ID": sessionId } },
        );
        const user = res.data.user;
        applyGoogleSession(user);

        // Nettoie le fragment #session_id de l'URL pour éviter d'y revenir.
        window.history.replaceState({}, document.title, window.location.pathname);

        const isStaff = user.role === "admin" || user.role === "moderator";
        navigate(isStaff ? "/admin" : "/decouverte", { replace: true });
      } catch (err) {
        setError(extractErrorMessage(err, "Connexion Google impossible"));
      }
    })();
  }, [location.hash, navigate, applyGoogleSession]);

  return (
    <div
      className="flex min-h-screen w-full flex-col items-center justify-center gap-4 bg-background-light px-6 font-display dark:bg-background-dark"
      data-testid="auth-callback-screen"
    >
      {error ? (
        <>
          <p className="text-sm text-red-400" data-testid="auth-callback-error">{error}</p>
          <button
            onClick={() => navigate("/connexion", { replace: true })}
            className="h-12 rounded-full bg-primary px-6 text-sm font-bold text-white"
            data-testid="auth-callback-back-to-login"
          >
            Retour à la connexion
          </button>
        </>
      ) : (
        <p className="text-sm text-slate-600 dark:text-slate-300">Connexion en cours…</p>
      )}
    </div>
  );
}
