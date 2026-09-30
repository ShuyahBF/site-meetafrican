import { useEffect, useState } from "react";
import { apiClient, extractErrorMessage } from "@/lib/api";

// Bouton « Continuer avec TikTok » (TikTok Login Kit). Affiché seulement si
// TikTok est configuré côté serveur. beAuthentik ne lit que le nom et la photo
// du compte TikTok, et ne publie jamais rien sur TikTok.
export default function BoutonTikTok({ onErreur }) {
  const [actif, setActif] = useState(false);
  const [attente, setAttente] = useState(false);

  useEffect(() => {
    apiClient.get("/auth/tiktok/config").then((r) => setActif(r.data.actif)).catch(() => setActif(false));
  }, []);

  if (!actif) return null;

  // Départ vers la page d'autorisation de TikTok
  const demarrer = async () => {
    setAttente(true);
    try {
      const r = await apiClient.get("/auth/tiktok/start");
      window.location.href = r.data.url;
    } catch (err) {
      onErreur?.(extractErrorMessage(err, "Connexion avec TikTok indisponible"));
      setAttente(false);
    }
  };

  return (
    <button type="button" onClick={demarrer} disabled={attente}
      className="flex h-14 w-full items-center justify-center gap-2 rounded-full bg-black text-base font-bold text-white disabled:opacity-50">
      <span aria-hidden="true">♪</span> {attente ? "Redirection…" : "Continuer avec TikTok"}
    </button>
  );
}
