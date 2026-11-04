// Test de la page d'installation (logique pure). Lancer : cd frontend && node tests/installation.test.mjs (Node 20+, aucune installation).
// Vérifie la reconnaissance du téléphone et du navigateur (identités réelles de navigateurs) et les étapes montrées dans chaque cas.
import { detecterEnvironnement as det, guideInstallation as guide, estInstallee } from "../src/lib/installation.js";
const ok = (n, v) => { console.log((v ? "OK  " : "ECHEC ") + n); if (!v) process.exitCode = 1; };

const UA = {
  chromeAndroid: "Mozilla/5.0 (Linux; Android 13; SM-A135F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
  samsung: "Mozilla/5.0 (Linux; Android 13; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) SamsungBrowser/23.0 Chrome/115.0.0.0 Mobile Safari/537.36",
  firefoxAndroid: "Mozilla/5.0 (Android 13; Mobile; rv:120.0) Gecko/120.0 Firefox/120.0",
  edgeAndroid: "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36 EdgA/120.0.0.0",
  operaAndroid: "Mozilla/5.0 (Linux; Android 12; TECNO KG5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Mobile Safari/537.36 OPR/76.0.0.0",
  ucBrowser: "Mozilla/5.0 (Linux; U; Android 11; fr-FR; Infinix X662) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/78.0.3904.108 UCBrowser/13.4.0.1306 Mobile Safari/537.36",
  webviewAndroid: "Mozilla/5.0 (Linux; Android 12; TECNO KF6; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/110.0.0.0 Mobile Safari/537.36",
  facebookAndroid: "Mozilla/5.0 (Linux; Android 12; SM-A125F Build/SP1A.210812.016; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/119.0.0.0 Mobile Safari/537.36 [FB_IAB/FB4A;FBAV/430.0.0.0;]",
  safariIphone: "Mozilla/5.0 (iPhone; CPU iPhone OS 17_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Mobile/15E148 Safari/604.1",
  chromeIphone: "Mozilla/5.0 (iPhone; CPU iPhone OS 17_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/120.0.6099.119 Mobile/15E148 Safari/604.1",
  instagramIphone: "Mozilla/5.0 (iPhone; CPU iPhone OS 17_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 Instagram 300.0.0.29.110",
  ipadMac: "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
  chromeWindows: "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
};

// --- Reconnaissance
let e = det(UA.chromeAndroid);
ok("Chrome Android : système et navigateur", e.systeme === "android" && e.navigateur === "chrome" && !e.appIntegree);
ok("Chrome Android : installation directe possible", e.installationDirecte);
e = det(UA.samsung); ok("Samsung Internet reconnu (et pas pris pour Chrome)", e.navigateur === "samsung" && e.installationDirecte);
e = det(UA.firefoxAndroid); ok("Firefox Android : pas d'installation directe", e.navigateur === "firefox" && !e.installationDirecte);
e = det(UA.edgeAndroid); ok("Edge Android reconnu", e.navigateur === "edge");
e = det(UA.operaAndroid); ok("Opera Android reconnu", e.navigateur === "opera");
e = det(UA.ucBrowser); ok("UC Browser : navigateur « autre » sans installation directe", e.navigateur === "autre" && !e.installationDirecte);
e = det(UA.webviewAndroid); ok("WebView Android = navigateur intégré à une application", e.appIntegree === "une application" && !e.installationDirecte);
e = det(UA.facebookAndroid); ok("Facebook Android reconnu", e.appIntegree === "Facebook");
e = det(UA.safariIphone); ok("Safari iPhone : ios + safari, pas d'installation directe", e.systeme === "ios" && e.navigateur === "safari" && !e.appIntegree && !e.installationDirecte);
e = det(UA.chromeIphone); ok("Chrome iPhone reconnu (pas confondu avec une application)", e.systeme === "ios" && e.navigateur === "chrome" && !e.appIntegree);
e = det(UA.instagramIphone); ok("Instagram iPhone = navigateur intégré", e.appIntegree === "Instagram");
e = det(UA.ipadMac, { pointsTactiles: 5 }); ok("iPad qui se présente comme un Mac (tactile) = ios", e.systeme === "ios");
e = det(UA.ipadMac, { pointsTactiles: 0 }); ok("Vrai Mac sans tactile = ordinateur", e.systeme === "ordinateur");
e = det(UA.chromeWindows); ok("Chrome Windows : ordinateur, installation directe possible", e.systeme === "ordinateur" && e.installationDirecte);
e = det(""); ok("Identité vide : ne plante pas", e.systeme === "ordinateur");
e = det(undefined); ok("Identité absente : ne plante pas", e.systeme === "ordinateur");

// --- Étapes montrées
const g = (ua, o = {}, tactile = 0) => guide(det(ua, { pointsTactiles: tactile }), { nomApp: "auRor", ...o });
let r = g(UA.chromeAndroid, { invitePrete: true }); ok("Chrome + invitation prête : mode direct, aucune étape", r.mode === "direct" && r.etapes.length === 0);
r = g(UA.chromeAndroid); ok("Chrome sans invitation : 3 étapes, la 1re parle des trois points", r.mode === "etapes" && r.etapes.length === 3 && /⋮/.test(r.etapes[0].texte));
ok("Le nom de l'application est repris dans les étapes", r.etapes.some((x) => x.texte.includes("auRor")));
r = g(UA.samsung); ok("Samsung : étapes propres à Samsung Internet", r.mode === "etapes" && /≡/.test(r.etapes[0].texte));
r = g(UA.firefoxAndroid); ok("Firefox : étape « Installer »", r.mode === "etapes" && /« Installer »/.test(r.etapes[1].texte));
r = g(UA.edgeAndroid); ok("Edge sans invitation : étapes génériques (pas de renvoi vers Chrome)", r.mode === "etapes");
r = g(UA.ucBrowser); ok("UC Browser : on recommande Chrome", r.mode === "ouvrir-navigateur" && /Chrome/.test(r.titre));
r = g(UA.facebookAndroid); ok("Facebook : d'abord ouvrir dans le navigateur", r.mode === "ouvrir-navigateur" && /Facebook/.test(r.etapes[0].texte));
r = g(UA.safariIphone); ok("Safari iPhone : Partager, écran d'accueil, Ajouter", r.mode === "etapes" && r.etapes[0].icone === "partager" && /écran d'accueil/.test(r.etapes[1].texte) && /bas de l'écran/.test(r.etapes[0].texte));
r = g(UA.ipadMac, {}, 5); ok("iPad Safari : le bouton Partager est EN HAUT", /haut de l'écran/.test(guide(det(UA.ipadMac, { pointsTactiles: 5 }), { nomApp: "auRor", ipad: true }).etapes[0].texte));
r = g(UA.chromeIphone); ok("Chrome iPhone : il faut passer par Safari", r.mode === "ouvrir-navigateur" && /Safari/.test(r.titre));
r = g(UA.instagramIphone); ok("Instagram iPhone : ouvrir dans Safari", r.mode === "ouvrir-navigateur" && /Safari/.test(r.titre));
r = g(UA.chromeWindows); ok("Ordinateur : on renvoie vers le téléphone", r.mode === "ordinateur");
r = g(UA.chromeWindows, { invitePrete: true }); ok("Ordinateur Chrome avec invitation : installation directe", r.mode === "direct");
r = g(UA.firefoxAndroid, { invitePrete: true }); ok("Invitation prête mais navigateur sans installation directe : étapes", r.mode === "etapes");
for (const ua of Object.values(UA)) {
  const x = guide(det(ua, { pointsTactiles: 0 }), { nomApp: "x" });
  ok("Toutes les étapes ont un texte et un pictogramme connu : " + det(ua).navigateur, x.etapes.every((s) => s.texte && ["menu-points", "menu-lignes", "partager", "ecran-accueil", "installer", "navigateur", "copier"].includes(s.icone)));
}

// --- Application déjà installée
ok("Déjà installée (mode autonome)", estInstallee({ matchMedia: () => ({ matches: true }) }));
ok("Déjà installée (iPhone)", estInstallee({ matchMedia: () => ({ matches: false }), navigator: { standalone: true } }));
ok("Pas installée", !estInstallee({ matchMedia: () => ({ matches: false }), navigator: {} }));
ok("Fenêtre absente : ne plante pas", !estInstallee(undefined));
