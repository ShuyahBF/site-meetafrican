import { useEffect, useMemo, useState } from "react";
import { useAuth } from "@/context/AuthContext";

// ============================================================================
// FILIGRANE DISSUASIF (lot 49, demande du propriétaire) — posé en travers des
// photos et vidéos des membres : le PSEUDO de la personne qui regarde, avec la
// date et l'heure, répété en diagonale et discret.
// Un site web ne peut pas empêcher une capture faite par le téléphone : si une
// capture circule, elle montre QUI l'a prise et QUAND, ce qui décourage le partage.
//
// Usage : placer <Filigrane /> DANS le cadre de la photo / vidéo, qui doit être
// en position relative (le filigrane le recouvre entièrement, sans bloquer les
// clics ni les gestes : pointer-events none).
// ============================================================================

// Date et heure au format JJ/MM/AAAA HH:MM (heure de Ouagadougou = UTC)
function horodatage() {
  const d = new Date();
  const deux = (n) => String(n).padStart(2, "0");
  return `${deux(d.getUTCDate())}/${deux(d.getUTCMonth() + 1)}/${d.getUTCFullYear()} ${deux(d.getUTCHours())}:${deux(d.getUTCMinutes())}`;
}

// Échappe les caractères spéciaux pour les insérer dans le dessin SVG
function echapper(texte) {
  return String(texte).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&apos;" }[c]));
}

export default function Filigrane({ className = "" }) {
  const { user } = useAuth();
  // L'heure affichée avance chaque minute
  const [quand, setQuand] = useState(horodatage);
  useEffect(() => {
    const minuterie = setInterval(() => setQuand(horodatage()), 60000);
    return () => clearInterval(minuterie);
  }, []);

  // Pseudo du membre connecté (sinon son e-mail / téléphone) ; rien si personne n'est connecté
  const pseudo = user?.full_name || user?.username || user?.email || user?.phone || "";

  // Motif SVG répété : le texte en diagonale (-30°), blanc semi-transparent
  // avec un léger contour sombre pour rester visible sur les fonds clairs.
  const fond = useMemo(() => {
    if (!pseudo) return null;
    const texte = echapper(`${pseudo} · ${quand}`);
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="260" height="150">`
      + `<text x="130" y="80" text-anchor="middle" transform="rotate(-30 130 75)" `
      + `font-family="Arial, sans-serif" font-size="13" font-weight="700" `
      + `fill="rgba(255,255,255,0.32)" stroke="rgba(0,0,0,0.18)" stroke-width="0.5">${texte}</text></svg>`;
    return `url("data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}")`;
  }, [pseudo, quand]);

  if (!fond) return null;
  return (
    <div
      aria-hidden="true"
      className={`pointer-events-none absolute inset-0 z-[5] select-none ${className}`}
      style={{ backgroundImage: fond, backgroundRepeat: "repeat" }}
    />
  );
}
