import { useEffect } from "react";
import { apiClient } from "@/lib/api";

// ============================================================================
// Lot 71 — Visite signalée à SAWALI (alerte WhatsApp du propriétaire)
// ============================================================================
// Quand un visiteur NON connecté arrive sur le site, le navigateur prévient le
// serveur beAuthentik (POST /api/presence/visite), qui transmet un signal signé
// à SAWALI en arrière-plan (backend/signal_connexions_sawali.py).
//
// Règles (pour un développeur WinDev) :
//   - une seule fois au chargement du site (composant monté une fois dans App) ;
//   - seulement si personne n'est connecté (pas de jeton « maf_token ») : les
//     connexions sont signalées par le serveur lui-même ;
//   - au plus une fois toutes les 30 minutes par navigateur : un identifiant
//     anonyme tiré au hasard et l'heure du dernier envoi sont gardés dans le
//     stockage local (clé « ba_visiteur ») ;
//   - aucune erreur n'est jamais montrée au visiteur (tout est dans des try/catch).
// Le serveur applique de son côté la même limite (par visiteur ou par IP) et
// ignore les robots.
// ============================================================================

const CLE_VISITEUR = "ba_visiteur";
const INTERVALLE_MS = 30 * 60 * 1000; // 30 minutes

// Identifiant anonyme aléatoire (aucune donnée personnelle)
function nouvelIdentifiant() {
  try {
    if (window.crypto?.randomUUID) return window.crypto.randomUUID().replace(/-/g, "");
  } catch { /* navigateur ancien : solution de repli ci-dessous */ }
  return `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 12)}`;
}

// Lecture de l'état mémorisé { id, dernier } (null si absent ou illisible)
function lireEtat() {
  try {
    const brut = JSON.parse(localStorage.getItem(CLE_VISITEUR) || "null");
    return brut && typeof brut.id === "string" ? brut : null;
  } catch {
    return null;
  }
}

export default function SignalVisite() {
  useEffect(() => {
    try {
      // Membre connecté : rien à faire (la connexion est signalée par le serveur)
      if (localStorage.getItem("maf_token")) return;
      const maintenant = Date.now();
      const etat = lireEtat();
      // Déjà signalé il y a moins de 30 minutes depuis ce navigateur : rien à faire
      if (etat && maintenant - Number(etat.dernier || 0) < INTERVALLE_MS) return;
      const id = etat?.id || nouvelIdentifiant();
      // On mémorise AVANT l'envoi : pas de second envoi si la page est rechargée aussitôt
      localStorage.setItem(CLE_VISITEUR, JSON.stringify({ id, dernier: maintenant }));
      apiClient
        .post("/presence/visite", { visiteur: id, page: window.location.pathname || "/" })
        .catch(() => { /* serveur injoignable : sans importance pour le visiteur */ });
    } catch {
      /* stockage local indisponible (navigation privée…) : on n'envoie rien */
    }
  }, []);

  // Composant invisible : il n'affiche rien
  return null;
}
