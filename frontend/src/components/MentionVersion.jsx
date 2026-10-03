import { LIBELLE_VERSION } from "@/version";

/**
 * Mention discrète « Version 5.45 du JJ/MM/AAAA » (règle permanente : version et
 * lot visibles sur la page de connexion et dans tout le portail).
 *
 * Le libellé vient de src/version.js (source unique). Aucun hash de commit
 * n'est affiché, ni dans le texte ni au survol (demande du propriétaire) :
 * l'info-bulle reprend seulement le même libellé.
 *
 * `className` : classes supplémentaires (marges, couleur sur fond sombre…).
 */
export default function MentionVersion({ className = "" }) {
  return (
    <p
      className={`select-text text-center text-[10px] font-medium tracking-wide text-slate-400 ${className}`}
      title={LIBELLE_VERSION}
      data-testid="mention-version"
    >
      {LIBELLE_VERSION}
    </p>
  );
}
