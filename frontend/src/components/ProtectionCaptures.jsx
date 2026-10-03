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
const MESSAGE = "Les captures d'écran sont interdites sur beAuthentik.";

export default function ProtectionCaptures() {
  const [message, setMessage] = useState("");
  const minuterie = useRef(null);

  useEffect(() => {
    const racine = document.documentElement;

    // Floute / défloute tout le site (classe CSS définie dans index.css)
    const masquer = () => racine.classList.add("masque-capture");
    const demasquer = () => racine.classList.remove("masque-capture");

    // Message de rappel, affiché 3 s
    const prevenir = () => {
      setMessage(MESSAGE);
      clearTimeout(minuterie.current);
      minuterie.current = setTimeout(() => setMessage(""), 3000);
    };

    // 1 et 3 — touches surveillées
    const surTouche = (e) => {
      if (e.key === "PrintScreen") {
        // Vide le presse-papiers (l'image capturée y est remplacée par du texte vide)
        try { navigator.clipboard?.writeText(""); } catch { /* navigateur sans accès au presse-papiers */ }
        masquer();
        setTimeout(demasquer, 1500);
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
        masquer();
        setTimeout(demasquer, 1500);
        prevenir();
      }
    };

    // 2 — page inactive ou masquée : contenu flouté
    const surVisibilite = () => (document.hidden ? masquer() : demasquer());

    // 4 — clic droit / appui long sur les médias
    const surMenuContextuel = (e) => {
      if (e.target?.closest?.("img, video, canvas, picture")) { e.preventDefault(); prevenir(); }
    };
    const surGlisser = (e) => {
      if (e.target?.closest?.("img, video, canvas, picture")) e.preventDefault();
    };

    window.addEventListener("keydown", surTouche);
    window.addEventListener("keyup", surTouche);
    window.addEventListener("blur", masquer);
    window.addEventListener("focus", demasquer);
    document.addEventListener("visibilitychange", surVisibilite);
    document.addEventListener("contextmenu", surMenuContextuel);
    document.addEventListener("dragstart", surGlisser);
    return () => {
      window.removeEventListener("keydown", surTouche);
      window.removeEventListener("keyup", surTouche);
      window.removeEventListener("blur", masquer);
      window.removeEventListener("focus", demasquer);
      document.removeEventListener("visibilitychange", surVisibilite);
      document.removeEventListener("contextmenu", surMenuContextuel);
      document.removeEventListener("dragstart", surGlisser);
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
