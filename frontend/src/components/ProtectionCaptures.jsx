import { useEffect, useRef, useState } from "react";

// ============================================================================
// PROTECTION CONTRE LES CAPTURES D'ÉCRAN (lot 46, règle du propriétaire :
// « les captures d'écran sont interdites sur tout le site »).
//
// LIMITE IMPORTANTE : un site web ne peut PAS bloquer techniquement une
// capture faite par le téléphone (boutons physiques), par le système
// (Win+Maj+S, Cmd+Maj+4…) ou par un appareil photo. Ce composant applique
// donc toutes les parades possibles côté navigateur :
//   1. Touche « Impr. écran » : le presse-papiers est vidé aussitôt, l'écran est
//      flouté un instant et un message rappelle l'interdiction.
//   2. Fenêtre qui perd le focus (outil de capture qui s'ouvre, changement
//      d'application) ou page masquée (aperçu des applications sur mobile) :
//      le contenu est FLOUTÉ tant que la page n'est pas de nouveau active.
//   3. Impression (Ctrl/Cmd+P) bloquée ; à l'impression la page est blanche (CSS).
//   4. Clic droit / appui long et glisser-déposer interdits sur les photos et vidéos.
// Monté une seule fois dans App.jsx : actif sur toutes les pages.
// ============================================================================
// ----------------------------------------------------------------------------
// Correctif lot 57 — « écran tout blanc pendant le sablier » :
// le flou (28 px sur un site à fond blanc = écran blanc) était posé à CHAQUE
// perte de focus de la fenêtre et retiré UNIQUEMENT par l'événement « focus ».
// Or le site provoque lui-même des pertes de focus juste avant d'afficher le
// « Patientez… » : boîte de confirmation native (window.confirm / alert),
// sélecteur de fichier (envoi de photo / vidéo), clic dans une maquette en
// <iframe>. Sur mobile, au retour de ces fenêtres, le navigateur ne renvoie
// pas toujours « focus » : le flou restait donc affiché jusqu'au prochain
// toucher de l'écran. Désormais :
//   - les fenêtres ouvertes par le site lui-même (confirmation, sélecteur de
//     fichier, iframe du site) NE déclenchent PAS le flou ;
//   - le flou dû à une perte de focus se retire TOUT SEUL : dès que la page a
//     de nouveau le focus (vérifié toutes les 400 ms), et au plus tard après
//     4 s si la page est visible ; le flou « page masquée » se retire dès que
//     la page redevient visible (visibilitychange / pageshow).
// Les protections exigées restent actives : Impr. écran, raccourcis de
// capture, impression bloquée, flou quand la page est réellement masquée ou
// que la fenêtre perd le focus au profit d'une autre application.
// ----------------------------------------------------------------------------

// Durée maximale du flou « perte de focus » quand la page reste visible.
const DUREE_MAX_FLOU_FOCUS_MS = 4000;
// Fréquence de vérification du retour du focus pendant le flou.
const INTERVALLE_VERIFICATION_MS = 400;
// Délai de tolérance après une fenêtre native ouverte par le site.
const TOLERANCE_DIALOGUE_MS = 1500;
// Durée maximale de tolérance pendant un sélecteur de fichier.
const TOLERANCE_FICHIER_MS = 120000;

const MESSAGE = "Les captures d'écran sont interdites sur beAuthentik.";

export default function ProtectionCaptures() {
  const [message, setMessage] = useState("");
  const minuterie = useRef(null);

  useEffect(() => {
    const racine = document.documentElement;

    // Jusqu'à quand (horodatage ms) une perte de focus est « normale » car
    // provoquée par le site lui-même (confirmation, sélecteur de fichier).
    let tolereJusqua = 0;
    // Minuteries du flou temporaire (perte de focus, Impr. écran)
    let verification = null;
    let delaiMax = null;

    // Arrête les minuteries de retrait automatique
    const arreterMinuteries = () => {
      clearInterval(verification);
      clearTimeout(delaiMax);
      verification = null;
      delaiMax = null;
    };

    // Floute / défloute tout le site (classe CSS définie dans index.css)
    const masquer = () => racine.classList.add("masque-capture");
    const demasquer = () => {
      arreterMinuteries();
      if (!racine.classList.contains("masque-capture")) return;
      racine.classList.remove("masque-capture");
      // Force le navigateur à redessiner tout de suite (Safari iOS gardait
      // parfois l'image floutée affichée jusqu'au prochain toucher).
      void document.body?.offsetHeight;
    };

    // Flou TEMPORAIRE : retiré automatiquement dès que la page est de nouveau
    // active (visible + focus), et au plus tard après `dureeMax` ms si la page
    // est visible. Aucun toucher de l'écran n'est nécessaire.
    const masquerTemporairement = (dureeMax) => {
      masquer();
      arreterMinuteries();
      verification = setInterval(() => {
        if (document.visibilityState === "visible" && document.hasFocus()) demasquer();
      }, INTERVALLE_VERIFICATION_MS);
      delaiMax = setTimeout(() => {
        // Page toujours masquée : on garde le flou (il partira au retour)
        if (document.visibilityState === "visible") demasquer();
      }, dureeMax);
    };

    // Message de rappel, affiché 3 s
    const prevenir = () => {
      setMessage(MESSAGE);
      clearTimeout(minuterie.current);
      minuterie.current = setTimeout(() => setMessage(""), 3000);
    };

    // Fenêtres natives ouvertes par le site (confirm / alert / prompt) :
    // on les enveloppe pour que la perte de focus qu'elles provoquent ne
    // floute pas l'écran (sinon : écran blanc sous le « Patientez… »).
    const originaux = {};
    ["confirm", "alert", "prompt"].forEach((nom) => {
      originaux[nom] = window[nom];
      window[nom] = function (...args) {
        tolereJusqua = Date.now() + 60000; // pendant la fenêtre
        try {
          return originaux[nom].apply(window, args);
        } finally {
          // Les événements blur/focus peuvent arriver juste après le retour
          tolereJusqua = Date.now() + TOLERANCE_DIALOGUE_MS;
          demasquer();
        }
      };
    });

    // Sélecteur de fichier (photo, vidéo, pièce jointe) ouvert par le site
    const surClic = (e) => {
      const cible = e.target;
      // Champ fichier cliqué directement (ou par programme : input.click())
      let champ = cible?.closest?.('input[type="file"]');
      // … ou étiquette <label> qui ouvre un champ fichier
      if (!champ) {
        const etiquette = cible?.closest?.("label");
        champ = etiquette?.control || etiquette?.querySelector?.('input[type="file"]');
      }
      if (champ?.type === "file") tolereJusqua = Date.now() + TOLERANCE_FICHIER_MS;
    };
    // Fichier choisi ou sélection annulée : fin de la tolérance (petit délai)
    const surFinSelection = (e) => {
      if (e.target?.type === "file") {
        tolereJusqua = Date.now() + TOLERANCE_DIALOGUE_MS;
        demasquer();
      }
    };

    // 1 et 3 — touches surveillées
    const surTouche = (e) => {
      if (e.key === "PrintScreen") {
        // Vide le presse-papiers (l'image capturée y est remplacée par du texte vide)
        try { navigator.clipboard?.writeText(""); } catch { /* navigateur sans accès au presse-papiers */ }
        masquerTemporairement(1500);
        prevenir();
      }
      const touche = (e.key || "").toLowerCase();
      if ((e.ctrlKey || e.metaKey) && touche === "p") {
        e.preventDefault(); // impression bloquée
        prevenir();
      }
      // Raccourcis de capture connus (macOS Cmd+Maj+3/4/5, Windows Win+Maj+S) :
      // le système les traite avant la page, on floute au mieux et on prévient.
      if (e.shiftKey && (e.metaKey || e.key === "Meta") && ["3", "4", "5", "s"].includes(touche)) {
        masquerTemporairement(1500);
        prevenir();
      }
    };

    // 2a — la fenêtre perd le focus (outil de capture, autre application)
    const surPerteFocus = () => {
      // Perte de focus provoquée par le site lui-même : pas de flou
      if (Date.now() < tolereJusqua) return;
      // On attend un instant que le navigateur mette à jour l'élément actif
      setTimeout(() => {
        if (Date.now() < tolereJusqua) return;
        // Clic dans une maquette du site affichée en <iframe> (zone /secure) :
        // le focus reste dans la page, pas de flou.
        if (document.activeElement?.tagName === "IFRAME") return;
        masquerTemporairement(DUREE_MAX_FLOU_FOCUS_MS);
      }, 0);
    };

    // 2b — page masquée (aperçu des applications sur mobile, autre onglet) :
    // flou tant qu'elle est masquée, retiré dès qu'elle redevient visible.
    const surVisibilite = () => {
      if (document.hidden) {
        arreterMinuteries();
        masquer();
      } else {
        demasquer();
      }
    };

    // Retour sur la page (cache arrière/avant du navigateur) : jamais flouté
    const surRetourPage = () => demasquer();

    // 4 — clic droit / appui long sur les médias
    const surMenuContextuel = (e) => {
      if (e.target?.closest?.("img, video, canvas, picture")) { e.preventDefault(); prevenir(); }
    };
    const surGlisser = (e) => {
      if (e.target?.closest?.("img, video, canvas, picture")) e.preventDefault();
    };

    window.addEventListener("keydown", surTouche);
    window.addEventListener("keyup", surTouche);
    window.addEventListener("blur", surPerteFocus);
    window.addEventListener("focus", demasquer);
    window.addEventListener("pageshow", surRetourPage);
    document.addEventListener("visibilitychange", surVisibilite);
    document.addEventListener("contextmenu", surMenuContextuel);
    document.addEventListener("dragstart", surGlisser);
    document.addEventListener("click", surClic, true);
    document.addEventListener("change", surFinSelection, true);
    document.addEventListener("cancel", surFinSelection, true);
    return () => {
      window.removeEventListener("keydown", surTouche);
      window.removeEventListener("keyup", surTouche);
      window.removeEventListener("blur", surPerteFocus);
      window.removeEventListener("focus", demasquer);
      window.removeEventListener("pageshow", surRetourPage);
      document.removeEventListener("visibilitychange", surVisibilite);
      document.removeEventListener("contextmenu", surMenuContextuel);
      document.removeEventListener("dragstart", surGlisser);
      document.removeEventListener("click", surClic, true);
      document.removeEventListener("change", surFinSelection, true);
      document.removeEventListener("cancel", surFinSelection, true);
      // Rétablit les fenêtres natives d'origine
      Object.entries(originaux).forEach(([nom, fn]) => { window[nom] = fn; });
      clearTimeout(minuterie.current);
      demasquer();
    };
  }, []);

  if (!message) return null;
  return (
    <div className="pointer-events-none fixed inset-x-0 top-4 z-[90] flex justify-center px-4" role="alert">
      <div className="rounded-full bg-ink/90 px-5 py-2.5 text-sm font-semibold text-white shadow-xl backdrop-blur">{message}</div>
    </div>
  );
}
