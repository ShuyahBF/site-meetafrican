import { useEffect, useRef } from "react";
import { apiClient } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";

const CHECK_EVERY_MS = 60 * 1000; // vérifie s'il y a un suivi actif
const SEND_EVERY_MS = 20 * 1000; // une position toutes les 20 s au plus

/**
 * Émetteur invisible de « Me suivre » : monté une fois pour tout le site.
 * Tant qu'un suivi est actif, il suit la position du téléphone
 * (watchPosition) et l'envoie au serveur beAuthentik, quelle que soit la
 * page ouverte. Limite des navigateurs : l'envoi s'arrête si le site est
 * fermé ou l'écran verrouillé (on demande donc à garder l'écran allumé).
 */
export default function TrackingBeacon() {
  const { user } = useAuth();
  const sessionRef = useRef(null);
  const watchRef = useRef(null);
  const lastSentRef = useRef(0);
  const wakeLockRef = useRef(null);

  useEffect(() => {
    if (!user) return undefined;

    const stopWatching = () => {
      if (watchRef.current != null) navigator.geolocation?.clearWatch(watchRef.current);
      watchRef.current = null;
      sessionRef.current = null;
      wakeLockRef.current?.release?.().catch(() => {});
      wakeLockRef.current = null;
    };

    // Envoi d'une position (limité à une toutes les 20 s)
    const onPosition = ({ coords }) => {
      const session = sessionRef.current;
      if (!session || Date.now() - lastSentRef.current < SEND_EVERY_MS) return;
      lastSentRef.current = Date.now();
      apiClient
        .post(`/tracking/sessions/${session.id}/points`, { lat: coords.latitude, lng: coords.longitude, accuracy: coords.accuracy })
        .catch((err) => {
          if (err?.response?.status === 410 || err?.response?.status === 404) stopWatching(); // suivi terminé
        });
    };

    // Y a-t-il un suivi actif ? -> démarrer / arrêter la géolocalisation
    const check = async () => {
      try {
        const { data } = await apiClient.get("/tracking/me");
        const active = data.mine.find((s) => s.status === "active");
        if (active && !sessionRef.current && navigator.geolocation) {
          sessionRef.current = active;
          lastSentRef.current = 0;
          watchRef.current = navigator.geolocation.watchPosition(onPosition, () => {}, {
            enableHighAccuracy: true,
            maximumAge: 10000,
            timeout: 30000,
          });
          // Garder l'écran allumé pendant le suivi (si le navigateur le permet)
          wakeLockRef.current = await navigator.wakeLock?.request?.("screen").catch(() => null);
        } else if (!active && sessionRef.current) {
          stopWatching();
        }
      } catch {
        // réseau capricieux : prochain essai dans une minute
      }
    };

    check();
    const timer = setInterval(check, CHECK_EVERY_MS);
    // Démarrage immédiat depuis la page « Me suivre »
    window.addEventListener("tracking:changed", check);
    return () => {
      clearInterval(timer);
      window.removeEventListener("tracking:changed", check);
      stopWatching();
    };
  }, [user?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  return null;
}
