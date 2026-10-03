// ============================================================================
// VERSION ET LOT DE LA PLATEFORME beAuthentik — SOURCE UNIQUE
// ============================================================================
//
// Règle permanente du propriétaire : version et lot TOUJOURS à jour à chaque
// déploiement, et affichés sur la page de connexion et dans le portail.
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
// La date de compilation, elle, est calculée AUTOMATIQUEMENT à la compilation
// (voir vite.config.js) : rien à saisir.
//
// Libellé affiché partout (format demandé par le propriétaire, lot 45) :
//   « Version VERSION.LOT du JJ/MM/AAAA à HH:MM »   ex. « Version 7.47 du 03/10/2026 à 21:30 »
// (lot 46 : l'heure de compilation suit la date, demande du propriétaire)
// La date est celle de la compilation, au fuseau Africa/Ouagadougou (= UTC).
// Aucun hash de commit n'est affiché (ni dans le libellé, ni au survol).
// ============================================================================

// Compteur de déploiements : +1 à chaque déploiement.
export const VERSION = 12;

// Numéro de la PR GitHub fusionnée pour ce déploiement.
export const LOT = 52;

// Hash court du commit compilé (RENDER_GIT_COMMIT sur Render, sinon `git`),
// injecté par vite.config.js. "dev" si introuvable. Gardé pour le diagnostic
// technique uniquement : il n'est JAMAIS affiché à l'écran.
export const COMMIT = import.meta.env.VITE_COMMIT_BUILD || "dev";

// Date et heure de compilation (ISO, UTC), injectées par vite.config.js.
export const DATE_BUILD = import.meta.env.VITE_DATE_BUILD || "";

// Date de compilation au format français JJ/MM/AAAA. Ouagadougou est à UTC+0
// toute l'année : on lit donc simplement le jour UTC de la date ISO.
function dateFrancaise(iso) {
  const d = new Date(iso);
  if (!iso || Number.isNaN(d.getTime())) return "";
  const deuxChiffres = (n) => String(n).padStart(2, "0");
  // Lot 46 — l'heure (HH:MM, heure de Ouagadougou = UTC) suit la date
  return `${deuxChiffres(d.getUTCDate())}/${deuxChiffres(d.getUTCMonth() + 1)}/${d.getUTCFullYear()}`
    + ` à ${deuxChiffres(d.getUTCHours())}:${deuxChiffres(d.getUTCMinutes())}`;
}
export const DATE_BUILD_FR = dateFrancaise(DATE_BUILD);

// Texte prêt à afficher : « Version 7.47 du 03/10/2026 à 21:30 »
// (sans date connue, par ex. hors compilation : « Version 5.45 »)
export const LIBELLE_VERSION = `Version ${VERSION}.${LOT}${DATE_BUILD_FR ? ` du ${DATE_BUILD_FR}` : ""}`;
