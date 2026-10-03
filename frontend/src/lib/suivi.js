// ---------------------------------------------------------------------------
// Lot 53 — « Me suivre » : outils partagés (état du signal, bip d'alerte,
// positions mémorisées hors connexion, exemption de la déconnexion pour inactivité)
// ---------------------------------------------------------------------------
import { useEffect, useState } from "react";

// Seuils de l'état du signal (demande du propriétaire)
export const SECONDES_SIGNAL_FAIBLE = 2 * 60; // au-delà : orange « signal faible »
export const SECONDES_SIGNAL_PERDU = 5 * 60;  // au-delà : rouge « signal perdu » + bip

/**
 * État du signal d'un suivi, à l'instant `maintenant` (ms).
 * Renvoie { niveau, texte, classes } :
 *   niveau : "termine" | "attente" | "direct" | "faible" | "perdu"
 */
export function etatSignal(session, maintenant = Date.now()) {
  if (!session) return { niveau: "attente", texte: "", classes: "" };
  if (session.status !== "active") {
    if (session.motif_fin === "arrive") {
      return { niveau: "termine", texte: "✅ Bien arrivé·e — suivi terminé", classes: "bg-emerald-50 text-emerald-800 ring-emerald-200" };
    }
    return { niveau: "termine", texte: "Suivi terminé", classes: "bg-slate-100 text-slate-600 ring-slate-200" };
  }
  const reference = session.last_point?.at || session.started_at;
  const age = Math.max(0, Math.round((maintenant - new Date(reference).getTime()) / 1000));
  const minutes = Math.floor(age / 60);
  if (!session.last_point && age < SECONDES_SIGNAL_FAIBLE) {
    return { niveau: "attente", texte: "En attente de la première position…", classes: "bg-slate-100 text-slate-600 ring-slate-200" };
  }
  if (age <= SECONDES_SIGNAL_FAIBLE) {
    return { niveau: "direct", texte: "🟢 En direct", classes: "bg-emerald-50 text-emerald-800 ring-emerald-200" };
  }
  if (age <= SECONDES_SIGNAL_PERDU) {
    return { niveau: "faible", texte: `🟠 Signal faible — dernière position il y a ${minutes} min`, classes: "bg-amber-50 text-amber-800 ring-amber-200" };
  }
  return { niveau: "perdu", texte: `🔴 Signal perdu depuis ${minutes} min`, classes: "bg-rose-50 text-rose-700 ring-rose-200" };
}

/** Horloge qui avance chaque seconde (pour recalculer l'âge de la dernière position). */
export function useMaintenant(intervalle = 1000) {
  const [maintenant, setMaintenant] = useState(Date.now());
  useEffect(() => {
    const t = setInterval(() => setMaintenant(Date.now()), intervalle);
    return () => clearInterval(t);
  }, [intervalle]);
  return maintenant;
}

/** Bip d'alerte « signal perdu » : trois notes courtes (Web Audio, sans fichier son). */
export function bipAlerte() {
  try {
    const Contexte = window.AudioContext || window.webkitAudioContext;
    if (!Contexte) return;
    const ctx = new Contexte();
    [0, 0.25, 0.5].forEach((decalage) => {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = "square";
      osc.frequency.value = 880;
      gain.gain.value = 0.08;
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start(ctx.currentTime + decalage);
      osc.stop(ctx.currentTime + decalage + 0.15);
    });
    setTimeout(() => ctx.close().catch(() => {}), 1200);
  } catch {
    /* son indisponible : l'alerte reste visible à l'écran */
  }
}

// ---------------------------------------------------------------------------
// Positions mémorisées dans le téléphone pendant une coupure d'Internet
// (stockage local du navigateur ; jamais bloquant s'il est indisponible)
// ---------------------------------------------------------------------------
const cleFile = (sessionId) => `ba_suivi_file_${sessionId}`;
export const MAX_FILE = 2000; // ~11 h de positions à raison d'une toutes les 20 s

export function lireFile(sessionId) {
  try {
    return JSON.parse(localStorage.getItem(cleFile(sessionId)) || "[]");
  } catch {
    return [];
  }
}

export function ecrireFile(sessionId, points) {
  try {
    if (points.length) localStorage.setItem(cleFile(sessionId), JSON.stringify(points.slice(-MAX_FILE)));
    else localStorage.removeItem(cleFile(sessionId));
  } catch {
    /* stockage plein ou indisponible */
  }
  // Prévient l'interface (bandeau, page « Me suivre ») du nombre de positions en attente
  window.dispatchEvent(new CustomEvent("suivi:file", { detail: { sessionId, enAttente: points.length } }));
}

// ---------------------------------------------------------------------------
// Exemption de la déconnexion pour inactivité pendant un suivi
// (le serveur applique la même règle : backend/sessions_comptes.py)
// ---------------------------------------------------------------------------
const exemptions = new Set();

/** Active (ou retire) une raison de ne pas déconnecter pour inactivité. */
export function exempterInactivite(cle, actif) {
  const avant = exemptions.size;
  if (actif) exemptions.add(cle);
  else exemptions.delete(cle);
  if (avant !== exemptions.size) window.dispatchEvent(new Event("suivi:exemption"));
}

/** Vrai tant qu'au moins une exemption est active (suivi en cours, carte de suivi ouverte). */
export function useExemptionInactivite() {
  const [exempte, setExempte] = useState(exemptions.size > 0);
  useEffect(() => {
    const maj = () => setExempte(exemptions.size > 0);
    window.addEventListener("suivi:exemption", maj);
    maj();
    return () => window.removeEventListener("suivi:exemption", maj);
  }, []);
  return exempte;
}
