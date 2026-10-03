import { useCallback, useEffect, useState } from "react";
import { apiClient } from "@/lib/api";

// ============================================================================
// État du serveur (lot 46, demande du propriétaire, comme sur Ster et SAWALI) :
// petite pastille sous le formulaire de connexion.
//   - verte  : « Serveur actif »  (réponse en moins de 2 s)
//   - orange : « Serveur lent »   (réponse en plus de 2 s)
//   - rouge  : « Serveur injoignable » ou « Pas de réseau »
// Vérification au chargement puis toutes les 15 s (route publique /api/health),
// et immédiatement quand l'appareil retrouve ou perd le réseau.
// ============================================================================
const LENT_MS = 2000;
const INTERVALLE_MS = 15000;

const AFFICHAGE = {
  verif: { couleur: "bg-slate-300", texte: "Vérification du serveur…" },
  ok: { couleur: "bg-emerald-500", texte: "Serveur actif" },
  lent: { couleur: "bg-amber-500", texte: "Serveur lent" },
  injoignable: { couleur: "bg-red-500", texte: "Serveur injoignable" },
  hors_ligne: { couleur: "bg-red-500", texte: "Pas de réseau" },
};

export default function EtatServeur({ className = "" }) {
  const [statut, setStatut] = useState("verif");

  // Un essai de joignabilité : durée mesurée, délai maximal 10 s
  const verifier = useCallback(async () => {
    if (typeof navigator !== "undefined" && navigator.onLine === false) { setStatut("hors_ligne"); return; }
    const debut = performance.now();
    try {
      await apiClient.get("/health", { timeout: 10000 });
      setStatut(performance.now() - debut > LENT_MS ? "lent" : "ok");
    } catch {
      setStatut("injoignable");
    }
  }, []);

  useEffect(() => {
    // Premier essai juste après l'affichage, puis toutes les 15 s
    const premier = setTimeout(verifier, 0);
    const minuterie = setInterval(verifier, INTERVALLE_MS);
    window.addEventListener("online", verifier);
    window.addEventListener("offline", verifier);
    return () => {
      clearTimeout(premier);
      clearInterval(minuterie);
      window.removeEventListener("online", verifier);
      window.removeEventListener("offline", verifier);
    };
  }, [verifier]);

  const a = AFFICHAGE[statut];
  return (
    <p className={`flex items-center justify-center gap-2 text-sm text-slate-500 dark:text-slate-400 ${className}`} role="status">
      <span className={`inline-block h-2.5 w-2.5 rounded-full ${a.couleur} ${statut === "ok" ? "animate-pulse" : ""}`} />
      {a.texte}
    </p>
  );
}
