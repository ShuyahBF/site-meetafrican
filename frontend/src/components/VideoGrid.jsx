import { Link } from "react-router-dom";
import { formatCount } from "@/lib/format";
import Filigrane from "@/components/Filigrane"; // lot 49 — filigrane dissuasif anti-capture

// Grille 3 colonnes de vignettes vidéo (profil public, "Mes Moments") —
// comme la grille d'un profil TikTok. La vignette est l'image FLOUTÉE
// produite par le serveur ; un cadenas signale les vidéos que le visiteur
// ne peut voir qu'en version floutée. L'auteur voit aussi ses vidéos en
// cours de traitement ou en échec.
export default function VideoGrid({ videos, emptyText = "Aucun Moment publié pour l'instant." }) {
  if (!videos.length) {
    return <p className="rounded-2xl bg-slate-50 px-4 py-8 text-center text-sm text-slate-400">{emptyText}</p>;
  }
  return (
    <div className="grid grid-cols-3 gap-1 overflow-hidden rounded-2xl">
      {videos.map((v) => {
        // En traitement : tuile animée, non cliquable.
        if (v.status === "processing") {
          return (
            <div key={v.id} className="flex aspect-[9/16] flex-col items-center justify-center gap-2 bg-gradient-to-b from-primary/10 to-sunset/10 text-center">
              <span className="h-7 w-7 animate-spin rounded-full border-[3px] border-primary/20 border-t-primary" />
              <span className="px-2 text-[11px] font-bold text-primary">Traitement…</span>
            </div>
          );
        }
        // Échec : message lisible, l'auteur peut republier.
        if (v.status === "failed") {
          return (
            <div key={v.id} className="flex aspect-[9/16] flex-col items-center justify-center gap-1 bg-red-50 p-2 text-center">
              <span className="material-symbols-outlined text-red-400">error</span>
              <span className="text-[10px] font-semibold leading-tight text-red-500">{v.failure_reason || "Échec du traitement"}</span>
            </div>
          );
        }
        return (
          <Link key={v.id} to={`/moments/${v.id}`} className="relative aspect-[9/16] bg-slate-900">
            {v.poster_url ? (
              <img src={v.poster_url} alt="" loading="lazy" className="h-full w-full object-cover" />
            ) : (
              <video src={`${v.url}#t=0.1`} preload="metadata" muted playsInline className="h-full w-full object-cover" />
            )}
            {/* Lot 49 — filigrane dissuasif sur la vignette */}
            <Filigrane />
            {!v.is_clear && (
              <span className="absolute right-1.5 top-1.5 flex h-6 w-6 items-center justify-center rounded-full bg-black/40 text-white">
                <span className="material-symbols-outlined icon-filled text-sm">lock</span>
              </span>
            )}
            <span className="absolute bottom-1.5 left-1.5 flex items-center gap-0.5 text-xs font-bold text-white drop-shadow">
              <span className="material-symbols-outlined text-sm">play_arrow</span>
              {formatCount(v.views_count)}
            </span>
          </Link>
        );
      })}
    </div>
  );
}
