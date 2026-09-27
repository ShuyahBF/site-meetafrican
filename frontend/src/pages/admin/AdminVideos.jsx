import { useEffect, useState } from "react";
import { apiClient, extractErrorMessage } from "@/lib/api";

const FILTERS = [
  { value: "reported", label: "Signalées" },
  { value: "removed", label: "Retirées" },
  { value: "published", label: "Publiées" },
  { value: "all", label: "Toutes" },
];

const REASON_LABELS = {
  faux_profil: "Faux profil",
  contenu_choquant: "Contenu choquant",
  harcelement: "Harcèlement",
  spam: "Spam / arnaque",
  autre: "Autre",
};

// Modération des vidéos du fil "Moments" : les plus signalées d'abord.
// Au-delà de 3 signalements, une vidéo est déjà retirée automatiquement
// (backend/routes/videos.py) — ici l'équipe confirme ou rétablit.
export default function AdminVideos() {
  const [filter, setFilter] = useState("reported");
  const [videos, setVideos] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState(null);
  const [error, setError] = useState("");

  const load = () => {
    setLoading(true);
    apiClient
      .get("/admin/videos", { params: { status: filter } })
      .then((r) => setVideos(r.data))
      .finally(() => setLoading(false));
  };

  useEffect(load, [filter]);

  const moderate = async (video, action) => {
    setBusyId(video.id);
    setError("");
    try {
      await apiClient.post(`/admin/videos/${video.id}/moderate`, { action });
      load();
    } catch (err) {
      setError(extractErrorMessage(err, "Action impossible"));
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div>
      <h1 className="text-2xl font-bold">Vidéos (Moments)</h1>
      <div className="mt-4 flex flex-wrap gap-2">
        {FILTERS.map((f) => (
          <button
            key={f.value}
            onClick={() => setFilter(f.value)}
            className={`rounded-full px-4 py-1.5 text-sm font-semibold ${
              filter === f.value ? "bg-primary text-white" : "bg-white text-slate-600 ring-1 ring-slate-200"
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>
      {error && <p className="mt-3 text-sm text-red-500">{error}</p>}

      {loading ? (
        <p className="mt-6 text-slate-400">Chargement…</p>
      ) : videos.length === 0 ? (
        <p className="mt-6 text-slate-500">Aucune vidéo dans cette catégorie.</p>
      ) : (
        <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {videos.map((v) => (
            <div key={v.id} className="overflow-hidden rounded-xl bg-white shadow-sm ring-1 ring-slate-200">
              <video src={v.url} controls preload="metadata" className="aspect-[9/16] max-h-80 w-full bg-black object-contain" />
              <div className="space-y-1 p-4 text-sm">
                <p className="font-semibold">{v.author?.full_name || "Auteur supprimé"}</p>
                {v.caption && <p className="text-slate-600">{v.caption}</p>}
                <p className="text-xs text-slate-500">
                  {v.views_count} vues · {v.likes_count} J'aime · {v.comments_count} commentaires
                </p>
                <p className={`text-xs font-semibold ${v.status === "removed" ? "text-red-500" : "text-emerald-600"}`}>
                  {v.status === "removed" ? `Retirée — ${v.removed_reason || ""}` : "Publiée"}
                </p>
                {v.reports_count > 0 && (
                  <p className="text-xs text-amber-600">
                    {v.reports_count} signalement(s) : {v.report_reasons.map((r) => REASON_LABELS[r] || r).join(", ")}
                  </p>
                )}
                <div className="flex gap-2 pt-2">
                  {v.status === "published" ? (
                    <button
                      onClick={() => moderate(v, "remove")}
                      disabled={busyId === v.id}
                      className="flex-1 rounded-lg bg-red-600 py-2 text-sm font-semibold text-white disabled:opacity-50"
                    >
                      Retirer
                    </button>
                  ) : (
                    <button
                      onClick={() => moderate(v, "restore")}
                      disabled={busyId === v.id}
                      className="flex-1 rounded-lg bg-emerald-600 py-2 text-sm font-semibold text-white disabled:opacity-50"
                    >
                      Rétablir
                    </button>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
