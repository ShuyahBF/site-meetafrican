// ============================================================================
// BIP SONORE DES NOUVEAUX MESSAGES
// ============================================================================
//
// Le son est GÉNÉRÉ par le navigateur (Web Audio API) : aucun fichier audio à
// télécharger. Trois sons courts au choix (réglés dans « Réglages ») :
//   - carillon : deux notes douces montantes ;
//   - goutte   : une note qui descend, comme une goutte d'eau ;
//   - bip      : un bip bref et net.
//
// Préférences du membre (enregistrées dans son profil, côté serveur, via
// PUT /api/me/settings) : son activé ou mode silencieux, volume (0 à 100) et
// son choisi. Une COPIE est gardée dans le navigateur (localStorage) : c'est le
// « repli local » utilisé si le serveur ne répond pas.
//
// Contrainte des navigateurs : un site ne peut pas jouer de son tant que
// l'utilisateur n'a pas interagi avec la page (clic, touche, toucher). On
// « déverrouille » donc le son à la première interaction ; avant cela, le bip
// est simplement ignoré (jamais d'erreur).
// ============================================================================

// Clé de la copie locale des préférences
const CLE_PREFERENCES = "maf_son_messages";

// Valeurs par défaut (identiques à celles du serveur, routes/account_extras.py)
export const PREFERENCES_DEFAUT = { son_messages: true, son_volume: 70, son_type: "carillon" };

// Sons proposés : identifiant -> libellé affiché
export const SONS = { carillon: "Carillon", goutte: "Goutte", bip: "Bip court" };

// Délai minimal entre deux bips (évite une rafale si plusieurs messages arrivent ensemble)
const ECART_MIN_MS = 1500;

let contexteAudio = null; // AudioContext créé à la première interaction
let dernierBip = 0; // horodatage du dernier bip joué
let creditConversation = 0; // bips déjà joués par la page Conversation (voir noterBipConversation)

// ---------------------------------------------------------------------------
// Préférences : lecture / écriture de la copie locale
// ---------------------------------------------------------------------------
export function lirePreferencesSon() {
  try {
    const brut = JSON.parse(localStorage.getItem(CLE_PREFERENCES) || "null");
    return { ...PREFERENCES_DEFAUT, ...(brut || {}) };
  } catch {
    return { ...PREFERENCES_DEFAUT }; // stockage indisponible : valeurs par défaut
  }
}

/** Garde une copie locale des préférences reçues du serveur (ou modifiées). */
export function enregistrerPreferencesSon(reglages) {
  if (!reglages) return;
  const prefs = {
    son_messages: reglages.son_messages ?? PREFERENCES_DEFAUT.son_messages,
    son_volume: reglages.son_volume ?? PREFERENCES_DEFAUT.son_volume,
    son_type: SONS[reglages.son_type] ? reglages.son_type : PREFERENCES_DEFAUT.son_type,
  };
  try {
    localStorage.setItem(CLE_PREFERENCES, JSON.stringify(prefs));
  } catch {
    /* stockage indisponible : tant pis, le serveur reste la référence */
  }
}

// ---------------------------------------------------------------------------
// Déverrouillage du son à la première interaction de l'utilisateur
// ---------------------------------------------------------------------------
function obtenirContexte() {
  if (contexteAudio) return contexteAudio;
  const Classe = window.AudioContext || window.webkitAudioContext;
  if (!Classe) return null; // navigateur sans Web Audio : pas de son
  contexteAudio = new Classe();
  return contexteAudio;
}

/** À appeler une fois au démarrage : le son sera autorisé dès le premier clic / toucher / touche. */
export function installerDeverrouillageSon() {
  const deverrouiller = () => {
    const ctx = obtenirContexte();
    if (ctx && ctx.state === "suspended") ctx.resume().catch(() => {});
    ["pointerdown", "keydown", "touchstart"].forEach((evt) => window.removeEventListener(evt, deverrouiller));
  };
  ["pointerdown", "keydown", "touchstart"].forEach((evt) => window.addEventListener(evt, deverrouiller, { passive: true }));
}

// ---------------------------------------------------------------------------
// Fabrication des sons (oscillateurs + enveloppe de volume)
// ---------------------------------------------------------------------------
// Une note : fréquence de départ (et d'arrivée pour un glissé), début, durée.
function note(ctx, sortie, { forme = "sine", de, vers = de, debut = 0, duree = 0.12 }) {
  const t0 = ctx.currentTime + debut;
  const osc = ctx.createOscillator();
  const enveloppe = ctx.createGain();
  osc.type = forme;
  osc.frequency.setValueAtTime(de, t0);
  if (vers !== de) osc.frequency.exponentialRampToValueAtTime(vers, t0 + duree);
  // Attaque très courte puis extinction douce (évite les « clics »)
  enveloppe.gain.setValueAtTime(0.0001, t0);
  enveloppe.gain.exponentialRampToValueAtTime(1, t0 + 0.01);
  enveloppe.gain.exponentialRampToValueAtTime(0.0001, t0 + duree);
  osc.connect(enveloppe).connect(sortie);
  osc.start(t0);
  osc.stop(t0 + duree + 0.02);
}

/**
 * Joue un son (utilisé par le bouton « Écouter » des Réglages et par le bip).
 * `type` : carillon | goutte | bip ; `volume` : 0 à 100.
 * Renvoie false si le son n'a pas pu être joué (pas encore d'interaction…).
 */
export function jouerSon(type = "carillon", volume = 70) {
  const ctx = obtenirContexte();
  if (!ctx || Number(volume) <= 0) return false;
  if (ctx.state === "suspended") ctx.resume().catch(() => {});
  if (ctx.state !== "running" && ctx.state !== "suspended") return false;
  // Volume général : 0..100 -> 0..0.5 (au-delà, le son devient agressif)
  const sortie = ctx.createGain();
  sortie.gain.value = (Math.min(100, Math.max(0, Number(volume))) / 100) * 0.5;
  sortie.connect(ctx.destination);
  if (type === "goutte") {
    note(ctx, sortie, { de: 1400, vers: 520, duree: 0.18 });
  } else if (type === "bip") {
    note(ctx, sortie, { forme: "square", de: 1000, duree: 0.09 });
  } else {
    note(ctx, sortie, { de: 880, duree: 0.14 });
    note(ctx, sortie, { de: 1320, debut: 0.12, duree: 0.2 });
  }
  return true;
}

/**
 * Bip « nouveau message reçu », selon les préférences du membre :
 * rien en mode silencieux, ni avant la première interaction, ni en rafale.
 */
export function bipNouveauMessage() {
  const prefs = lirePreferencesSon();
  if (!prefs.son_messages) return false; // mode silencieux
  const maintenant = Date.now();
  if (maintenant - dernierBip < ECART_MIN_MS) return false; // anti-rafale
  // Pas de « déverrouillage » encore (aucune interaction) : on ne force rien
  if (!contexteAudio || contexteAudio.state !== "running") return false;
  dernierBip = maintenant;
  return jouerSon(prefs.son_type, prefs.son_volume);
}

// ---------------------------------------------------------------------------
// Coordination page Conversation / compteur global
// ---------------------------------------------------------------------------
// Quand la page Conversation reçoit un message en temps réel, elle joue le bip
// et le signale ici : le compteur de non-lus (sondé toutes les 20 s) ne rejouera
// pas le bip pour ce même message.
export function noterBipConversation() {
  creditConversation += 1;
}

/** Utilisé par le compteur global : part des nouveaux messages déjà « sonnés ». */
export function consommerCreditConversation(nombre) {
  const pris = Math.min(nombre, creditConversation);
  creditConversation -= pris;
  return pris;
}

/** Remise à zéro (les messages ont été lus, ou changement de compte). */
export function effacerCreditConversation() {
  creditConversation = 0;
}
