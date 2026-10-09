// ============================================================================
// VERSION ET LOT DE LA PLATEFORME beAuthentik — SOURCE UNIQUE
// ============================================================================
//
// Règle permanente du propriétaire : version et lot TOUJOURS à jour à chaque
// déploiement, et version + date/heure de déploiement toujours affichées.
//
// À FAIRE À CHAQUE DÉPLOIEMENT (donc dans chaque PR fusionnée sur `main`) :
//   1. VERSION : ajouter 1 au nombre ci-dessous (compteur de déploiements).
//   2. LOT     : mettre le numéro de la PR GitHub qui sera fusionnée pour ce
//                déploiement (ex. PR #41 → LOT = 41).
//
// Pourquoi ce fichier est dans `frontend/` : sur Render, un service avec
// `rootDir` ne se redéploie QUE si un fichier de son dossier change. Comme ce
// fichier change à chaque PR, le site (frontend) est TOUJOURS reconstruit, et
// le numéro affiché est donc toujours celui du dernier déploiement.
//
// La date/heure de déploiement (= date de compilation du site) et le hash
// court du commit sont calculés AUTOMATIQUEMENT à la compilation
// (voir vite.config.js) : rien à saisir.
//
// Libellés affichés (règle commune à toutes les plateformes, lot 54) :
//   - court    (connexion + portail) :
//       « Version 14 · déployée le 04/10/2026 21:10 »   (ni lot ni commit)
//   - détaillé (pages d'administration / paramétrage uniquement) :
//       « Version 14 · Lot 54 · 1a2b3c4 · déployée le 04/10/2026 21:10 »
// La date est affichée à l'heure de Ouagadougou (Africa/Ouagadougou = UTC).
// ============================================================================

// Compteur de déploiements : +1 à chaque déploiement.
export const VERSION = 26;

// Numéro de la PR GitHub fusionnée pour ce déploiement.
export const LOT = 66;

// Hash court du commit compilé (RENDER_GIT_COMMIT sur Render, sinon `git`),
// injecté par vite.config.js. "dev" si introuvable. Affiché UNIQUEMENT dans le
// libellé détaillé des pages d'administration (jamais sur la connexion ni
// dans le portail, pas même au survol).
export const COMMIT = import.meta.env.VITE_COMMIT_BUILD || "dev";

// Date et heure de compilation (ISO, UTC), injectées par vite.config.js.
export const DATE_BUILD = import.meta.env.VITE_DATE_BUILD || "";

// Date/heure de déploiement au format français court « JJ/MM/AAAA HH:MM »
// (ex. « 04/10/2026 21:10 »). Renvoie "" si la date est absente ou invalide
// (par ex. hors compilation).
function dateHeureFrancaise(iso) {
  const d = new Date(iso);
  if (!iso || Number.isNaN(d.getTime())) return "";
  return d.toLocaleString("fr-FR", {
    dateStyle: "short",
    timeStyle: "short",
    // Heure de Ouagadougou (UTC toute l'année) : même affichage pour tous
    timeZone: "Africa/Ouagadougou",
  });
}
export const DATE_BUILD_FR = dateHeureFrancaise(DATE_BUILD);

// ----------------------------------------------------------------------------
// libelleVersion(detaille) : texte prêt à afficher.
//   detaille = false (par défaut) → « Version 14 · déployée le 04/10/2026 21:10 »
//   detaille = true               → « Version 14 · Lot 54 · 1a2b3c4 · déployée le 04/10/2026 21:10 »
// Sans date connue, la partie « déployée le … » est simplement omise.
// ----------------------------------------------------------------------------
export function libelleVersion(detaille = false) {
  const morceaux = [`Version ${VERSION}`];
  if (detaille) {
    // Lot et commit : réservés aux pages d'administration / paramétrage
    morceaux.push(`Lot ${LOT}`, COMMIT);
  }
  if (DATE_BUILD_FR) morceaux.push(`déployée le ${DATE_BUILD_FR}`);
  return morceaux.join(" · ");
}

// Libellé court (connexion et portail), gardé pour compatibilité.
export const LIBELLE_VERSION = libelleVersion(false);
