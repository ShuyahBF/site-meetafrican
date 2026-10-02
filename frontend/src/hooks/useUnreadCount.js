import { useEffect, useState } from "react";
import { apiClient, FOND } from "@/lib/api";

const POLL_MS = 20000;

/**
 * Nombre total de messages non lus + demandes "Voir en clair" en attente
 * (badge sur l'onglet "Messages").
 * Rafraîchi toutes les 20 s et quand l'onglet du navigateur redevient
 * visible — pas besoin d'un WebSocket global pour un simple compteur.
 */
export function useUnreadCount() {
  const [unread, setUnread] = useState(0);

  useEffect(() => {
    let cancelled = false;
    const load = () =>
      apiClient
        .get("/conversations/unread-count", FOND)
        .then((r) => !cancelled && setUnread(r.data.unread + (r.data.video_requests || 0)))
        .catch(() => {});
    load();
    const interval = setInterval(load, POLL_MS);
    const onVisible = () => document.visibilityState === "visible" && load();
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      cancelled = true;
      clearInterval(interval);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, []);

  return unread;
}
