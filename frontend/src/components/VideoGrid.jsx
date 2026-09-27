import { Link } from "react-router-dom";
import { formatCount } from "@/lib/format";

// Grille 3 colonnes de vignettes vidéo (profil public, "Mes Moments") —
// comme la grille d'un profil TikTok. La première image de la vidéo sert
// de vignette (preload="metadata", aucune miniature à générer côté serveur).
export default function VideoGrid({ videos, emptyText = "Aucun Moment publié pour l'instant." }) {
  if (!videos.length) {
    return <p className="rounded-2xl bg-slate-50 px-4 py-8 text-center text-sm text-slate-400">{emptyText}</p>;
  }
  return (
    <div className="grid grid-cols-3 gap-1 overflow-hidden rounded-2xl">
      {videos.map((v) => (
        <Link key={v.id} to={`/moments/${v.id}`} className="relative aspect-[9/16] bg-slate-900">
          {/* "#t=0.1" : force l'affichage de la première image sur mobile */}
          <video src={`${v.url}#t=0.1`} preload="metadata" muted playsInline className="h-full w-full object-cover" />
          <span className="absolute bottom-1.5 left-1.5 flex items-center gap-0.5 text-xs font-bold text-white drop-shadow">
            <span className="material-symbols-outlined text-sm">play_arrow</span>
            {formatCount(v.views_count)}
          </span>
        </Link>
      ))}
    </div>
  );
}
