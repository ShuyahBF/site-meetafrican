// ============================================================================
// PAGE D'INSTALLATION — LOGIQUE PURE (testée : node tests/installation.test.mjs)
// ============================================================================
// Objectif : un utilisateur peu familier avec la technologie ouvre un lien (souvent reçu par WhatsApp) et doit pouvoir installer
// l'application sur son téléphone en suivant 2 ou 3 étapes simples, quel que soit son téléphone et son navigateur.
//
// Pour un développeur WinDev : ce fichier ne dessine rien. Il lit « l'identité » du navigateur (user agent) et répond à deux questions :
//   1. detecterEnvironnement : sur quoi suis-je ? (Android, iPhone, ordinateur) et dans quel navigateur ? (Chrome, Samsung, Safari…)
//      Les applications qui ouvrent les liens dans leur propre petit navigateur (Facebook, Instagram, TikTok…) sont reconnues : on ne peut
//      pas y installer une application, il faut d'abord ouvrir le lien dans le vrai navigateur.
//   2. guideInstallation : quelles étapes montrer à l'écran, avec quel pictogramme, dans cet environnement ?
// ============================================================================

// Navigateurs sur lesquels l'installation directe est proposée par le système (événement « beforeinstallprompt »)
const NAVIGATEURS_INSTALLATION_DIRECTE = ["chrome", "edge", "samsung", "opera"];

/**
 * Lit l'identité du navigateur.
 * @param {string} ua  navigator.userAgent
 * @param {{pointsTactiles?: number}} options  navigator.maxTouchPoints (un iPad récent se présente comme un Mac : seul le tactile le trahit)
 * @returns {{systeme: "android"|"ios"|"ordinateur", navigateur: string, appIntegree: string, installationDirecte: boolean}}
 */
export function detecterEnvironnement(ua = "", { pointsTactiles = 0 } = {}) {
  const u = String(ua || "");
  const iphone = /iPhone|iPod/.test(u);
  const ipad = /iPad/.test(u) || (/Macintosh/.test(u) && pointsTactiles > 1);
  const ios = iphone || ipad;
  const android = /Android/i.test(u);
  const systeme = ios ? "ios" : android ? "android" : "ordinateur";

  // Navigateur : l'ordre compte (Chrome est écrit dans l'identité de presque tous les autres)
  let navigateur = "autre";
  if (/SamsungBrowser/.test(u)) navigateur = "samsung";
  else if (/EdgA|EdgiOS|Edg\//.test(u)) navigateur = "edge";
  else if (/OPR\/|OPT\/|OPiOS/.test(u)) navigateur = "opera";
  else if (/Firefox|FxiOS/.test(u)) navigateur = "firefox";
  else if (/UCBrowser|Opera Mini|OPiOS|Phoenix|HiBrowser|MiuiBrowser|HeyTapBrowser|VivoBrowser/i.test(u)) navigateur = "autre";   // très répandus en Afrique, installation peu fiable
  else if (/Chrome|CriOS/.test(u)) navigateur = "chrome";
  else if (/Safari/.test(u)) navigateur = "safari";

  // Navigateur intégré à une application (le lien a été ouvert depuis Facebook, Instagram, TikTok…) : on ne peut pas y installer
  let appIntegree = "";
  if (/FBAN|FBAV|FB_IAB|FBIOS/.test(u)) appIntegree = "Facebook";
  else if (/Instagram/.test(u)) appIntegree = "Instagram";
  else if (/TikTok|musical_ly|BytedanceWebview|Bytedance/i.test(u)) appIntegree = "TikTok";
  else if (/Snapchat/.test(u)) appIntegree = "Snapchat";
  else if (/Twitter/.test(u)) appIntegree = "X (Twitter)";
  else if (/\bLine\//.test(u)) appIntegree = "LINE";
  else if (android && /; wv\)/.test(u)) appIntegree = "une application";                       // WebView Android générique
  else if (ios && !/Safari\//.test(u) && !/CriOS|FxiOS|EdgiOS|OPiOS/.test(u)) appIntegree = "une application";   // iPhone : pas de « Safari/ » = navigateur intégré

  const installationDirecte = !ios && !appIntegree && NAVIGATEURS_INSTALLATION_DIRECTE.includes(navigateur);
  return { systeme, navigateur, appIntegree, installationDirecte };
}

// Les étapes de chaque cas. « icone » désigne un pictogramme dessiné par PictoInstallation (voir ce composant).
const ETAPES = {
  chromeAndroid: (app) => [
    { icone: "menu-points", texte: "En haut à droite de l'écran, touchez les trois points ⋮." },
    { icone: "installer", texte: "Touchez « Installer l'application » (ou « Ajouter à l'écran d'accueil »)." },
    { icone: "ecran-accueil", texte: `Touchez « Installer » pour confirmer. L'icône ${app} apparaît sur votre écran d'accueil.` },
  ],
  samsung: (app) => [
    { icone: "menu-lignes", texte: "En bas à droite de l'écran, touchez le menu ≡." },
    { icone: "installer", texte: "Touchez « Ajouter la page à », puis « Écran d'accueil »." },
    { icone: "ecran-accueil", texte: `Confirmez. L'icône ${app} apparaît sur votre écran d'accueil.` },
  ],
  firefox: (app) => [
    { icone: "menu-points", texte: "En haut à droite de l'écran, touchez les trois points ⋮." },
    { icone: "installer", texte: "Touchez « Installer »." },
    { icone: "ecran-accueil", texte: `Confirmez. L'icône ${app} apparaît sur votre écran d'accueil.` },
  ],
  autreAndroid: (app) => [
    { icone: "menu-points", texte: "Touchez le menu du navigateur (⋮ ou ≡)." },
    { icone: "installer", texte: "Cherchez « Installer l'application » ou « Ajouter à l'écran d'accueil »." },
    { icone: "ecran-accueil", texte: `Confirmez. L'icône ${app} apparaît sur votre écran d'accueil.` },
  ],
  safariIos: (app, ipad) => [
    { icone: "partager", texte: ipad ? "En haut de l'écran, touchez le bouton Partager (un carré avec une flèche vers le haut)." : "En bas de l'écran, touchez le bouton Partager (un carré avec une flèche vers le haut)." },
    { icone: "ecran-accueil", texte: "Faites glisser le menu vers le haut et touchez « Sur l'écran d'accueil »." },
    { icone: "installer", texte: `Touchez « Ajouter » en haut à droite. L'icône ${app} apparaît sur votre écran d'accueil.` },
  ],
  ouvrirDansNavigateur: (nomNavigateur, appIntegree) => [
    { icone: "menu-points", texte: `Vous avez ouvert ce lien dans ${appIntegree}. Touchez les trois points (⋮ ou …) ou l'icône « boussole » de l'écran.` },
    { icone: "navigateur", texte: `Touchez « Ouvrir dans ${nomNavigateur} » (ou « Ouvrir dans le navigateur »).` },
    { icone: "installer", texte: "La page s'ouvre dans le navigateur : revenez ici pour installer." },
  ],
  copierLien: (nomNavigateur) => [
    { icone: "copier", texte: "Touchez le bouton « Copier le lien » ci-dessous." },
    { icone: "navigateur", texte: `Ouvrez ${nomNavigateur} sur votre téléphone.` },
    { icone: "installer", texte: "Collez le lien dans la barre d'adresse (appui long, puis « Coller »), puis validez." },
  ],
};

/**
 * Ce que la page doit montrer.
 * @param {ReturnType<typeof detecterEnvironnement>} env
 * @param {{nomApp?: string, invitePrete?: boolean, ipad?: boolean}} options  invitePrete = le navigateur a déjà proposé l'installation directe
 * @returns {{mode: "direct"|"etapes"|"ouvrir-navigateur"|"ordinateur", titre: string, intro: string, etapes: Array<{icone: string, texte: string}>, conseil: string}}
 */
export function guideInstallation(env, { nomApp = "l'application", invitePrete = false, ipad = false } = {}) {
  const nomNavigateurRecommande = env.systeme === "ios" ? "Safari" : "Chrome";

  // Installation en un seul geste : le navigateur l'a déjà proposée
  if (invitePrete && env.installationDirecte) {
    return { mode: "direct", titre: `Installer ${nomApp}`, intro: "Un seul geste : touchez le grand bouton ci-dessous, puis « Installer ».", etapes: [],
             conseil: "L'application s'ouvre ensuite en plein écran, comme les autres applications de votre téléphone." };
  }
  // Ordinateur : l'application est pensée pour le téléphone
  if (env.systeme === "ordinateur") {
    return { mode: "ordinateur", titre: `Installer ${nomApp} sur votre téléphone`, intro: "Cette page est faite pour être ouverte sur un téléphone.",
             etapes: [{ icone: "copier", texte: "Envoyez-vous le lien de cette page (bouton « Copier le lien »), ou scannez le QR code avec l'appareil photo de votre téléphone." },
                      { icone: "navigateur", texte: "Ouvrez ce lien dans Chrome sur Android, ou dans Safari sur iPhone." }],
             conseil: "Sur ordinateur, Chrome et Edge peuvent aussi installer l'application : cherchez l'icône d'installation dans la barre d'adresse." };
  }
  // Lien ouvert depuis une autre application : il faut d'abord sortir vers le vrai navigateur
  if (env.appIntegree) {
    return { mode: "ouvrir-navigateur", titre: `Ouvrez d'abord ce lien dans ${nomNavigateurRecommande}`, intro: "L'installation ne marche pas dans le petit navigateur d'une application.",
             etapes: ETAPES.ouvrirDansNavigateur(nomNavigateurRecommande, env.appIntegree), conseil: "Si vous ne trouvez pas l'option, utilisez le bouton « Copier le lien » puis collez le lien dans le navigateur." };
  }
  if (env.systeme === "ios") {
    // Sur iPhone, seule la méthode de Safari est sûre
    if (env.navigateur !== "safari") {
      return { mode: "ouvrir-navigateur", titre: "Ouvrez d'abord ce lien dans Safari", intro: "Sur iPhone, l'installation se fait avec Safari (le navigateur bleu avec une boussole).",
               etapes: ETAPES.copierLien("Safari"), conseil: "Une fois dans Safari, revenez sur cette page : les 3 étapes d'installation s'affichent." };
    }
    return { mode: "etapes", titre: `Installer ${nomApp} sur iPhone`, intro: "Trois gestes avec Safari :", etapes: ETAPES.safariIos(nomApp, ipad),
             conseil: "Le bouton « Sur l'écran d'accueil » est parfois en bas de la liste : faites glisser le menu vers le haut." };
  }
  // Android
  if (env.navigateur === "samsung") return { mode: "etapes", titre: `Installer ${nomApp} sur Android`, intro: "Trois gestes avec Samsung Internet :", etapes: ETAPES.samsung(nomApp), conseil: "Si vous préférez, vous pouvez aussi ouvrir ce lien dans Chrome." };
  if (env.navigateur === "firefox") return { mode: "etapes", titre: `Installer ${nomApp} sur Android`, intro: "Trois gestes avec Firefox :", etapes: ETAPES.firefox(nomApp), conseil: "Chrome propose aussi l'installation en un seul geste." };
  if (env.navigateur === "chrome") return { mode: "etapes", titre: `Installer ${nomApp} sur Android`, intro: "Trois gestes avec Chrome :", etapes: ETAPES.chromeAndroid(nomApp),
                                           conseil: "Si « Installer l'application » n'apparaît pas, rechargez cette page une fois, puis recommencez." };
  if (env.navigateur === "edge" || env.navigateur === "opera") return { mode: "etapes", titre: `Installer ${nomApp} sur Android`, intro: "Trois gestes :", etapes: ETAPES.autreAndroid(nomApp), conseil: "Chrome propose aussi l'installation en un seul geste." };
  // Navigateurs peu fiables (UC Browser, Opera Mini, Phoenix…) ou inconnus : on recommande Chrome
  return { mode: "ouvrir-navigateur", titre: "Utilisez plutôt Chrome", intro: "Ce navigateur n'installe pas toujours l'application correctement.",
           etapes: ETAPES.copierLien("Chrome"), conseil: "Chrome est installé sur presque tous les téléphones Android (icône ronde rouge, jaune, verte et bleue)." };
}

/** Vrai si la page tourne déjà comme application installée (écran d'accueil). */
export function estInstallee(fenetre) {
  try { return !!(fenetre?.matchMedia?.("(display-mode: standalone)")?.matches || fenetre?.navigator?.standalone === true); } catch { return false; }
}
