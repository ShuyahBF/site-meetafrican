// Formatage des informations de présence/réactivité affichées sur les
// cartes de profil (dernière connexion, badge de réactivité).

/** "Vu à l'instant" / "Vu il y a 12 min" / "Vu hier à 14:32" / "Vu le 03/09". */
export function formatLastSeen(iso) {
  if (!iso) return "Jamais connecté(e)";
  const seen = new Date(iso);
  if (Number.isNaN(seen.getTime())) return "Jamais connecté(e)";

  const now = new Date();
  const diffMinutes = Math.floor((now - seen) / 60000);

  if (diffMinutes < 1) return "Vu à l'instant";
  if (diffMinutes < 60) return `Vu il y a ${diffMinutes} min`;
  if (diffMinutes < 24 * 60) {
    const hours = Math.floor(diffMinutes / 60);
    return `Vu il y a ${hours} h`;
  }
  const isYesterday =
    seen.getDate() === now.getDate() - 1 &&
    seen.getMonth() === now.getMonth() &&
    seen.getFullYear() === now.getFullYear();
  const time = seen.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });
  if (isYesterday) return `Vu hier à ${time}`;
  return `Vu le ${seen.toLocaleDateString("fr-FR")}`;
}

/** Badge de réactivité basé sur le temps de réponse moyen (secondes). */
export function responseBadge(avgResponseSeconds) {
  if (avgResponseSeconds == null) return null;
  if (avgResponseSeconds < 5 * 60) {
    return { label: "Très réactif·ve", className: "bg-emerald-500/90 text-white" };
  }
  if (avgResponseSeconds < 60 * 60) {
    return { label: "Réactif·ve", className: "bg-amber-500/90 text-white" };
  }
  return { label: "Répond parfois", className: "bg-slate-500/90 text-white" };
}

/** Compteurs compacts façon TikTok : 950 -> "950", 1520 -> "1,5 k", 2300000 -> "2,3 M". */
export function formatCount(n) {
  const value = Number(n) || 0;
  if (value < 1000) return String(value);
  if (value < 1_000_000) return `${(value / 1000).toFixed(value < 10_000 ? 1 : 0).replace(".", ",").replace(",0", "")} k`;
  return `${(value / 1_000_000).toFixed(1).replace(".", ",").replace(",0", "")} M`;
}

/** Date relative courte pour commentaires/messages : "à l'instant", "5 min", "3 h", "2 j", puis la date. */
export function formatRelativeShort(iso) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const minutes = Math.floor((Date.now() - d.getTime()) / 60000);
  if (minutes < 1) return "à l'instant";
  if (minutes < 60) return `${minutes} min`;
  if (minutes < 24 * 60) return `${Math.floor(minutes / 60)} h`;
  if (minutes < 7 * 24 * 60) return `${Math.floor(minutes / 1440)} j`;
  return d.toLocaleDateString("fr-FR", { day: "numeric", month: "short" });
}

/** Date et heure lisibles : "28/09/2026 à 14:05" (horodatage des vérifications). */
export function formatDateTime(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return `${d.toLocaleDateString("fr-FR")} à ${d.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" })}`;
}
