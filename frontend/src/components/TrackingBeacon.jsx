import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { apiClient, FOND } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { ecrireFile, exempterInactivite, lireFile } from "@/lib/suivi";

const CHECK_EVERY_MS = 60 * 1000; // vérifie s'il y a un suivi actif
const SEND_EVERY_MS = 20 * 1000; // une position toutes les 20 s au plus
const TAILLE_LOT = 200; // positions renvoyées par requête après une coupure

/**
 * Émetteur invisible de « Me suivre » : monté une fois pour tout le site.
 * Tant qu'un suivi est actif, il suit la position du téléphone
 * (watchPosition) et l'envoie au serveur beAuthentik, quelle que soit la
 * page ouverte. Limite des navigateurs : l'envoi s'arrête si le site est
 * fermé ou l'écran verrouillé (on demande donc à garder l'écran allumé).
 *
 * Lot 53 :
 *  - HORS CONNEXION : chaque position non envoyée est gardée dans le téléphone
 *    avec son heure réelle, puis renvoyée en lot dès le retour d'Internet ;
 *  - pas de déconnexion pour inactivité pendant le suivi ;
 *  - bandeau permanent « Suivi actif — gardez l'écran allumé » sur toutes les pages.
 */
export default function TrackingBeacon() {
  const { user } = useAuth();
  const sessionRef = useRef(null);
  const watchRef = useRef(null);
  const lastSentRef = useRef(0);
  const wakeLockRef = useRef(null);
  const envoiEnCoursRef = useRef(false);
  // État affiché dans le bandeau
  const [actif, setActif] = useState(false);
  const [enAttente, setEnAttente] = useState(0);
  const [horsLigne, setHorsLigne] = useState(typeof navigator !== "undefined" && navigator.onLine === false);

  useEffect(() => {
    if (!user) return undefined;

    const stopWatching = () => {
      if (watchRef.current != null) navigator.geolocation?.clearWatch(watchRef.current);
      watchRef.current = null;
      sessionRef.current = null;
      wakeLockRef.current?.release?.().catch(() => {});
      wakeLockRef.current = null;
      setActif(false);
      exempterInactivite("suivi-membre", false);
    };

    // Suivi terminé côté serveur : on oublie les positions encore en attente
    const terminer = (sessionId) => {
      ecrireFile(sessionId, []);
      stopWatching();
    };

    // Renvoie les positions gardées pendant une coupure (par lots, les plus anciennes d'abord)
    const viderFile = async () => {
      const session = sessionRef.current;
      if (!session || envoiEnCoursRef.current || navigator.onLine === false) return;
      envoiEnCoursRef.current = true;
      try {
        let file = lireFile(session.id);
        while (file.length) {
          const lot = file.slice(0, TAILLE_LOT);
          await apiClient.post(`/tracking/sessions/${session.id}/points/lot`, { points: lot }, FOND);
          file = lireFile(session.id).slice(lot.length);
          ecrireFile(session.id, file);
        }
      } catch (err) {
        if (err?.response?.status === 410 || err?.response?.status === 404) terminer(session.id);
        // sinon : réseau encore capricieux, nouvel essai au prochain retour du réseau / contrôle
      } finally {
        envoiEnCoursRef.current = false;
      }
    };

    // Écran allumé (Wake Lock) : le navigateur le relâche quand la page est masquée,
    // on note alors qu'il faut le redemander au retour sur l'onglet.
    const garderEcranAllume = async () => {
      const verrou = await navigator.wakeLock?.request?.("screen").catch(() => null);
      verrou?.addEventListener?.("release", () => { wakeLockRef.current = null; });
      wakeLockRef.current = verrou || null;
    };

    // Garde une position dans le téléphone (envoi impossible pour l'instant)
    const mettreEnFile = (sessionId, point) => {
      ecrireFile(sessionId, [...lireFile(sessionId), point]);
    };

    // Envoi d'une position (limité à une toutes les 20 s)
    const onPosition = ({ coords }) => {
      const session = sessionRef.current;
      if (!session || Date.now() - lastSentRef.current < SEND_EVERY_MS) return;
      lastSentRef.current = Date.now();
      const point = { lat: coords.latitude, lng: coords.longitude, accuracy: coords.accuracy, at: new Date().toISOString() };
      if (navigator.onLine === false) {
        mettreEnFile(session.id, point);
        return;
      }
      apiClient
        .post(`/tracking/sessions/${session.id}/points`, { lat: point.lat, lng: point.lng, accuracy: point.accuracy }, FOND)
        .then(() => viderFile())
        .catch((err) => {
          if (err?.response?.status === 410 || err?.response?.status === 404) terminer(session.id); // suivi terminé
          else if (!err?.response) mettreEnFile(session.id, point); // pas de réponse : réseau coupé
        });
    };

    // Y a-t-il un suivi actif ? -> démarrer / arrêter la géolocalisation
    const check = async () => {
      try {
        const { data } = await apiClient.get("/tracking/me", FOND);
        const active = data.mine.find((s) => s.status === "active");
        if (active && !sessionRef.current && navigator.geolocation) {
          sessionRef.current = active;
          lastSentRef.current = 0;
          setActif(true);
          setEnAttente(lireFile(active.id).length);
          exempterInactivite("suivi-membre", true);
          watchRef.current = navigator.geolocation.watchPosition(onPosition, () => {}, {
            enableHighAccuracy: true,
            maximumAge: 10000,
            timeout: 30000,
          });
          // Garder l'écran allumé pendant le suivi (si le navigateur le permet)
          await garderEcranAllume();
        } else if (!active && sessionRef.current) {
          stopWatching();
        }
        viderFile();
      } catch {
        // réseau capricieux : prochain essai dans une minute
      }
    };

    // Réseau : bandeau « hors connexion » et renvoi des positions dès son retour
    const surEnLigne = () => { setHorsLigne(false); viderFile(); };
    const surHorsLigne = () => setHorsLigne(true);
    const surFile = (e) => { if (e.detail?.sessionId === sessionRef.current?.id) setEnAttente(e.detail.enAttente); };
    // Retour sur l'onglet : l'écran a pu être verrouillé, on relance le maintien de l'écran allumé
    const surVisibilite = async () => {
      if (document.visibilityState === "visible" && sessionRef.current && !wakeLockRef.current) await garderEcranAllume();
    };

    check();
    const timer = setInterval(check, CHECK_EVERY_MS);
    // Démarrage immédiat depuis la page « Me suivre »
    window.addEventListener("tracking:changed", check);
    window.addEventListener("online", surEnLigne);
    window.addEventListener("offline", surHorsLigne);
    window.addEventListener("suivi:file", surFile);
    document.addEventListener("visibilitychange", surVisibilite);
    return () => {
      clearInterval(timer);
      window.removeEventListener("tracking:changed", check);
      window.removeEventListener("online", surEnLigne);
      window.removeEventListener("offline", surHorsLigne);
      window.removeEventListener("suivi:file", surFile);
      document.removeEventListener("visibilitychange", surVisibilite);
      stopWatching();
    };
  }, [user?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!user || !actif) return null;
  // Bandeau permanent pendant le suivi (toutes les pages)
  return (
    <Link
      to="/me-suivre"
      className="fixed left-1/2 top-2 z-[60] flex max-w-[92vw] -translate-x-1/2 items-center gap-2 rounded-full bg-emerald-600 px-3 py-1.5 text-xs font-bold text-white shadow-lg"
    >
      <span className="h-2 w-2 shrink-0 animate-pulse rounded-full bg-white" />
      <span className="truncate">
        Suivi actif — gardez l'écran allumé
        {(horsLigne || enAttente > 0) && ` · Hors connexion : ${enAttente} position${enAttente > 1 ? "s" : ""} en attente`}
      </span>
    </Link>
  );
}
