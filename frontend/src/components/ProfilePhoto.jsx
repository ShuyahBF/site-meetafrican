// Photo de profil avec repli sur un buste-silhouette (homme/femme) quand
// aucune photo approuvée n'existe, et pastille de présence en ligne
// optionnelle superposée en haut à gauche.

const SILHOUETTES = {
  homme: "/images/silhouette-homme.svg",
  femme: "/images/silhouette-femme.svg",
};

export function primaryPhotoUrl(profile) {
  const approved = (profile.photos || []).filter((p) => p.status === "approved");
  const primary = approved.find((p) => p.is_primary) || approved[0];
  return primary?.url || null;
}

export default function ProfilePhoto({ profile, showOnlineDot = false, className = "", imgClassName = "" }) {
  const url = primaryPhotoUrl(profile);
  const fallback = SILHOUETTES[profile.gender] || SILHOUETTES.homme;

  return (
    <div className={`relative overflow-hidden bg-slate-200 dark:bg-white/10 ${className}`}>
      <img
        src={url || fallback}
        alt={profile.full_name || ""}
        className={`h-full w-full object-cover ${url ? "" : "object-contain p-2"} ${imgClassName}`}
      />
      {showOnlineDot && (
        <span
          className={`absolute left-2 top-2 h-3.5 w-3.5 rounded-full ring-2 ring-white dark:ring-background-dark ${
            profile.is_online ? "bg-emerald-500" : "bg-slate-400"
          }`}
          title={profile.is_online ? "En ligne" : "Hors ligne"}
        />
      )}
    </div>
  );
}
