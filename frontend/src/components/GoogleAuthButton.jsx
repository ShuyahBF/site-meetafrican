/**
 * Bouton "Continuer avec Google" — redirige vers l'URL Emergent OAuth
 * avec un redirect dynamique construit depuis window.location.origin.
 *
 * REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
 */
export default function GoogleAuthButton({ label = "Continuer avec Google" }) {
  const startGoogleAuth = () => {
    // Le redirect doit pointer vers une route de l'app (pas la landing).
    // On envoie sur /decouverte : AppRoutes intercepte le #session_id=
    // avant même que ProtectedRoute ne redirige.
    const redirectUrl = `${window.location.origin}/decouverte`;
    window.location.href = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirectUrl)}`;
  };

  return (
    <button
      type="button"
      onClick={startGoogleAuth}
      className="flex h-12 w-full items-center justify-center gap-3 rounded-full border border-slate-300 bg-white text-sm font-semibold text-slate-800 transition hover:bg-slate-50 dark:border-white/20 dark:bg-white/10 dark:text-white dark:hover:bg-white/15"
      data-testid="google-auth-button"
    >
      <GoogleGlyph />
      {label}
    </button>
  );
}

function GoogleGlyph() {
  return (
    <svg aria-hidden viewBox="0 0 48 48" width="20" height="20">
      <path fill="#EA4335" d="M24 9.5c3.9 0 6.6 1.7 8.1 3.1l5.9-5.7C34.4 3.4 29.7 1.5 24 1.5 14.7 1.5 6.6 6.9 2.9 14.7l6.9 5.4C11.6 14.3 17.2 9.5 24 9.5z" />
      <path fill="#4285F4" d="M46.5 24.5c0-1.6-.1-3.1-.4-4.5H24v9h12.7c-.5 3-2.3 5.5-4.8 7.2l7.4 5.8c4.3-4 6.8-9.9 6.8-17.5z" />
      <path fill="#FBBC05" d="M9.8 28.6c-.5-1.5-.8-3.1-.8-4.6s.3-3.1.8-4.6l-6.9-5.4C1.2 17.1 0 20.4 0 24s1.2 6.9 3.4 10l6.4-5.4z" />
      <path fill="#34A853" d="M24 46.5c6.5 0 12-2.1 15.9-5.8l-7.4-5.8c-2 1.4-4.7 2.4-8.5 2.4-6.8 0-12.4-4.8-14.2-11.2l-6.4 5.4C6.6 41.1 14.7 46.5 24 46.5z" />
      <path fill="none" d="M0 0h48v48H0z" />
    </svg>
  );
}
