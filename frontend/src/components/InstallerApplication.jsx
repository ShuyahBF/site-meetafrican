import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { estInstallee } from "@/lib/installation";

// Bouton « Installer l'application » (Android / PWA). Chrome propose l'installation directe par l'événement « beforeinstallprompt »
// (gardé par main.jsx dans window.__baInvite) ; sinon on ouvre la page d'installation guidée (/installer, étapes illustrées).
// Le bouton disparaît quand le site tourne déjà comme application installée.
export default function InstallerApplication({ className = "" }) {
  const navigate = useNavigate();
  const [invite, setInvite] = useState(() => window.__baInvite || null);
  const [installee, setInstallee] = useState(() => estInstallee(window));

  useEffect(() => {
    const surInvite = () => setInvite(window.__baInvite || null);
    const surInstallation = () => { window.__baInvite = null; setInvite(null); setInstallee(true); };
    window.addEventListener("ba-invite", surInvite);
    window.addEventListener("appinstalled", surInstallation);
    return () => { window.removeEventListener("ba-invite", surInvite); window.removeEventListener("appinstalled", surInstallation); };
  }, []);

  if (installee) return null;

  // Installation directe si Chrome l'a proposée ; sinon page guidée
  const cliquer = async () => {
    if (!invite) { navigate("/installer"); return; }
    invite.prompt();
    try { await invite.userChoice; } catch { /* choix ignoré */ }
    window.__baInvite = null; setInvite(null);
  };

  return (
    <button type="button" onClick={cliquer} data-testid="bouton-installer"
      className={`inline-flex items-center justify-center gap-1 text-sm font-semibold text-primary ${className}`}>
      <span className="material-symbols-outlined text-base">install_mobile</span> Installer l'application
    </button>
  );
}
