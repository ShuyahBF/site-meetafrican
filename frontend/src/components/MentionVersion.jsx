import { libelleVersion } from "@/version";

/**
 * Mention discrète de la version déployée (règle permanente : version et
 * date/heure de déploiement visibles sur la connexion et dans tout le portail).
 *
 * Le libellé vient de src/version.js (source unique) :
 *   - par défaut (connexion, portail) : « Version 14 · déployée le 04/10/2026 21:10 »
 *     → ni lot ni commit, ni dans le texte ni au survol ;
 *   - `detaille` (pages d'administration / paramétrage uniquement) :
 *     « Version 14 · Lot 54 · 1a2b3c4 · déployée le 04/10/2026 21:10 ».
 * L'info-bulle reprend exactement le même texte que celui affiché.
 *
 * `className` : classes supplémentaires (marges, couleur sur fond sombre…).
 */
export default function MentionVersion({ className = "", detaille = false }) {
  const texte = libelleVersion(detaille);
  return (
    <p
      className={`select-text text-center text-[10px] font-medium tracking-wide text-slate-400 ${className}`}
      title={texte}
      data-testid={detaille ? "mention-version-detaillee" : "mention-version"}
    >
      {texte}
    </p>
  );
}
