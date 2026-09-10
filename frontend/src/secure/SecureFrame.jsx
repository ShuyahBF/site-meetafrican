import { useEffect, useRef } from "react";
import { useSecureSettings } from "./SecureSettingsContext";

// Encapsule une maquette VIDAL (fichier HTML autonome) dans un <iframe> isolé.
// Le contenu brut (importé via `?raw`) n'a ni <!doctype>/<html>/<body> propres
// (habitude des artefacts Claude, qui les enveloppent à la publication) : on
// reconstruit ici un document HTML complet et minimal avant de l'injecter en
// srcDoc, sans attribut "sandbox" pour ne pas brider les scripts/fetches des
// maquettes (QR code, Google Fonts, etc.).
//
// Thème et notes VIDAL sont pilotés depuis la sidebar (SecureSettingsContext) :
// encodés dans le document au premier chargement (attributs sur <html>), puis
// répercutés sur un changement ultérieur via postMessage — pour ne pas recharger
// l'iframe (et perdre l'état du formulaire en cours) à chaque bascule du toggle.
export default function SecureFrame({ html, title }) {
  const { theme, vidalNotes } = useSecureSettings();
  const iframeRef = useRef(null);
  const themeMounted = useRef(false);
  const notesMounted = useRef(false);

  // Config d'accès au vrai backend VIDAL (voir backend/routes/vidal.py), injectée
  // en variable globale plutôt que via postMessage : les maquettes en ont besoin
  // dès leur premier script inline (recherche produit au chargement), avant tout
  // échange avec le parent. Le secret est nécessairement visible dans le bundle
  // JS (Vite expose tout VITE_* au navigateur) — pas un vrai contrôle d'accès,
  // juste un garde-fou anti-robot (voir PORTAGE-SAWALI-VIDAL.md).
  const vidalApiConfig = JSON.stringify({
    baseUrl: import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api",
    proxySecret: import.meta.env.VITE_VIDAL_PROXY_SECRET || "",
  });

  const doc = `<!doctype html><html lang="fr" data-theme="${theme}" data-vidal-notes="${vidalNotes ? "on" : "off"}"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width, initial-scale=1"/><script>window.__VIDAL_API__ = ${vidalApiConfig};</script></head><body style="margin:0">${html}<style>
    /* La maquette Posologie a un fond transparent pensé pour un futur hébergement
       dans la page d'un site hôte. Ici, dans la zone /secure, il n'y a pas de tel
       site hôte : on retombe donc sur le fond propre de la maquette (var(--bg),
       déjà correct en clair comme en sombre) plutôt que de laisser transparaître
       le gris de cette coquille de test. Sans effet sur les maquettes qui ont déjà
       leur propre fond opaque. */
    body{ background:var(--bg) !important; }
  </style><script>
    window.addEventListener('message', function(e){
      if (!e.data || typeof e.data !== 'object') return;
      if (e.data.type === 'secure-theme') document.documentElement.setAttribute('data-theme', e.data.theme);
      if (e.data.type === 'secure-vidal-notes') document.documentElement.setAttribute('data-vidal-notes', e.data.on ? 'on' : 'off');
    });
  </script></body></html>`;

  // Premier rendu : le thème/les notes sont déjà encodés dans srcDoc ci-dessus.
  // Rendus suivants (toggle sidebar après chargement) : on pousse le changement
  // par message plutôt que de reconstruire srcDoc, qui rechargerait l'iframe.
  useEffect(() => {
    if (!themeMounted.current) {
      themeMounted.current = true;
      return;
    }
    iframeRef.current?.contentWindow?.postMessage({ type: "secure-theme", theme }, "*");
  }, [theme]);

  useEffect(() => {
    if (!notesMounted.current) {
      notesMounted.current = true;
      return;
    }
    iframeRef.current?.contentWindow?.postMessage({ type: "secure-vidal-notes", on: vidalNotes }, "*");
  }, [vidalNotes]);

  return (
    <iframe
      ref={iframeRef}
      title={title}
      srcDoc={doc}
      style={{ width: "100%", height: "100%", border: "none", display: "block" }}
    />
  );
}
