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
