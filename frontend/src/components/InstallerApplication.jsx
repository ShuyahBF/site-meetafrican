import { useEffect, useState } from "react";
import ModalShell from "@/components/ModalShell";

// Bouton « Installer l'application » (Android / PWA). Chrome propose l'installation par l'événement « beforeinstallprompt »
// (gardé par main.jsx dans window.__baInvite) ; sinon on affiche les gestes à faire dans une petite fenêtre (ModalShell, max-w-sm).
// Le bouton disparaît quand le site tourne déjà comme application installée.
export default function InstallerApplication({ className = "" }) {
  const [invite, setInvite] = useState(() => window.__baInvite || null);
  const [aide, setAide] = useState(false);
  const [installee, setInstallee] = useState(
    () => !!(window.matchMedia?.("(display-mode: standalone)").matches || window.navigator.standalone === true),
  );

  useEffect(() => {
    const surInvite = () => setInvite(window.__baInvite || null);
    const surInstallation = () => { window.__baInvite = null; setInvite(null); setInstallee(true); };
    window.addEventListener("ba-invite", surInvite);
    window.addEventListener("appinstalled", surInstallation);
    return () => { window.removeEventListener("ba-invite", surInvite); window.removeEventListener("appinstalled", surInstallation); };
  }, []);

  if (installee) return null;

  // Chrome propose l'installation directe ; sinon on montre la marche à suivre
  const cliquer = async () => {
    if (!invite) { setAide(true); return; }
    invite.prompt();
    try { await invite.userChoice; } catch { /* choix ignoré */ }
    window.__baInvite = null; setInvite(null);
  };

  const estIphone = /iphone|ipad|ipod/i.test(navigator.userAgent);
  return (
    <>
      <button type="button" onClick={cliquer} data-testid="bouton-installer"
        className={`inline-flex items-center justify-center gap-1 text-sm font-semibold text-primary ${className}`}>
        <span className="material-symbols-outlined text-base">install_mobile</span> Installer l'application
      </button>
      {aide && (
        <ModalShell onClose={() => setAide(false)}>
          <h2 className="text-lg font-extrabold">Installer beAuthentik</h2>
          {estIphone ? (
            <ol className="mt-3 list-decimal space-y-1 pl-5 text-sm">
              <li>Ouvrez ce site dans <b>Safari</b>.</li>
              <li>Touchez le bouton <b>Partager</b> (carré avec une flèche vers le haut).</li>
              <li>Choisissez <b>Sur l'écran d'accueil</b>.</li>
            </ol>
          ) : (
            <>
              <p className="mt-3 text-sm">Sur Android, avec <b>Chrome</b> :</p>
              <ol className="mt-1 list-decimal space-y-1 pl-5 text-sm">
                <li>Touchez le menu <b>⋮</b> en haut à droite.</li>
                <li>Choisissez <b>Installer l'application</b> (ou <b>Ajouter à l'écran d'accueil</b>).</li>
                <li>Confirmez : l'icône beAuthentik apparaît sur votre écran d'accueil.</li>
              </ol>
            </>
          )}
        </ModalShell>
      )}
    </>
  );
}
