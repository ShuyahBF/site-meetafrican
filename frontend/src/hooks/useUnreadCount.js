import { useEffect, useState } from "react";
import { apiClient, FOND } from "@/lib/api";

const POLL_MS = 20000;

// ---------------------------------------------------------------------------
// Sondage PARTAGÉ du nombre de non-lus
// ---------------------------------------------------------------------------
// Un seul appel toutes les 20 s pour tout le site, quel que soit le nombre de
// composants qui affichent le compteur (barre du bas, bip des nouveaux messages…).
// Le sondage démarre avec le premier abonné et s'arrête avec le dernier.
const abonnes = new Set(); // fonctions appelées à chaque nouvelle valeur
let dernier = null; // dernière réponse : { messages, demandes, total }
let minuteur = null;

function charger() {
  apiClient
    .get("/conversations/unread-count", FOND)
    .then((r) => {
      const messages = Number(r.data.unread) || 0;
      const demandes = Number(r.data.video_requests) || 0;
      dernier = { messages, demandes, total: messages + demandes };
      abonnes.forEach((f) => f(dernier));
    })
    .catch(() => {});
}

function surVisibilite() {
  if (document.visibilityState === "visible") charger();
}

/**
 * S'abonne au compteur de non-lus. `rappel({messages, demandes, total})` est
 * appelé à chaque relevé. Renvoie la fonction de désabonnement.
 */
export function abonnerNonLus(rappel) {
  abonnes.add(rappel);
  if (abonnes.size === 1) {
    // Premier abonné : démarrage du sondage
    charger();
    minuteur = setInterval(charger, POLL_MS);
    document.addEventListener("visibilitychange", surVisibilite);
  } else if (dernier) {
    rappel(dernier); // valeur déjà connue : affichée tout de suite
  }
  return () => {
    abonnes.delete(rappel);
    if (abonnes.size === 0) {
      // Dernier abonné parti (déconnexion…) : arrêt du sondage et oubli de la valeur
      clearInterval(minuteur);
      minuteur = null;
      dernier = null;
      document.removeEventListener("visibilitychange", surVisibilite);
    }
  };
}

/**
 * Nombre total de messages non lus + demandes "Voir en clair" en attente
 * (badge sur l'onglet "Messages").
 * Rafraîchi toutes les 20 s et quand l'onglet du navigateur redevient
 * visible — pas besoin d'un WebSocket global pour un simple compteur.
 */
export function useUnreadCount() {
  const [unread, setUnread] = useState(0);

  useEffect(() => abonnerNonLus((v) => setUnread(v.total)), []);

  return unread;
}
