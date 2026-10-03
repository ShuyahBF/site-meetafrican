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
// Le hash court du commit et la date de compilation, eux, sont calculés
// AUTOMATIQUEMENT à la compilation (voir vite.config.js) : rien à saisir.
// ============================================================================

// Compteur de déploiements : +1 à chaque déploiement.
export const VERSION = 3;

// Numéro de la PR GitHub fusionnée pour ce déploiement.
export const LOT = 43;

// Hash court du commit compilé (RENDER_GIT_COMMIT sur Render, sinon `git`),
// injecté par vite.config.js. "dev" si introuvable (ex. hors dépôt git).
export const COMMIT = import.meta.env.VITE_COMMIT_BUILD || "dev";

// Date et heure de compilation (ISO, UTC), injectées par vite.config.js.
export const DATE_BUILD = import.meta.env.VITE_DATE_BUILD || "";

// Texte prêt à afficher : « Version 1 · Lot 40 · a1b2c3d »
export const LIBELLE_VERSION = `Version ${VERSION} · Lot ${LOT} · ${COMMIT}`;
