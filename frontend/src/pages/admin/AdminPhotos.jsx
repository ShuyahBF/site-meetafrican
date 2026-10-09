import { useEffect, useState } from "react";
import { apiClient } from "@/lib/api";
import { formatDateTime } from "@/lib/format";

export default function AdminPhotos() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState(null);
  const [decisions, setDecisions] = useState([]);   // dernières décisions de l'IA (que l'on peut forcer)

  const load = () => {
    setLoading(true);
    apiClient.get("/admin/photos/pending").then((r) => setItems(r.data)).finally(() => setLoading(false));
    apiClient.get("/admin/photos/decisions-ia").then((r) => setDecisions(r.data)).catch(() => setDecisions([]));
  };

  useEffect(load, []);

  const review = async (item, approve) => {
    setBusyId(item.id);
    try {
      await apiClient.post(`/admin/photos/${item.user_id}/${item.id}/review`, null, { params: { approve } });
      setItems((prev) => prev.filter((p) => p.id !== item.id));
      apiClient.get("/admin/photos/decisions-ia").then((r) => setDecisions(r.data)).catch(() => {});
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div>
      <h1 className="text-2xl font-bold">Modération des photos</h1>
      <p className="mt-1 text-sm text-slate-500">
        Administrateurs et modérateurs. L'IA valide ou refuse seule ; ici, vous tranchez les doutes (photos que l'IA
        n'a pas pu juger, refus d'office pour plus de 2 visages) et vous pouvez forcer n'importe quelle décision de
        l'IA (en bas). À droite : ce que verront les membres qui n'ont pas matché (bandeau noir ou masque sanitaire,
        au choix dans Paramètres). Chaque décision est horodatée.
      </p>

      {loading ? (
        <p className="mt-6 text-slate-400">Chargement…</p>
      ) : items.length === 0 ? (
        <p className="mt-6 text-sm text-slate-500">Aucune photo en attente. 🎉</p>
      ) : (
        <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {items.map((item) => (
            <div key={item.id} className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
              {/* 09/10/2026 — photo d'origine et version masquée (bande des yeux au nez) côte à côte */}
              <div className="grid grid-cols-2 gap-px bg-slate-200">
                <figure className="bg-white">
                  <img src={item.url} alt="Photo d'origine" className="aspect-square w-full object-cover" />
                  <figcaption className="px-2 py-1 text-center text-[11px] text-slate-500">Photo d'origine</figcaption>
                </figure>
                <figure className="bg-white">
                  {item.masked_url
                    ? <img src={item.masked_url} alt="Photo masquée" className="aspect-square w-full object-cover" />
                    : <div className="grid aspect-square w-full place-items-center text-[11px] text-slate-400">Aperçu indisponible</div>}
                  <figcaption className="px-2 py-1 text-center text-[11px] text-slate-500">Vue par les autres (masquée)</figcaption>
                </figure>
              </div>
              <div className="p-3">
                <p className="font-semibold">{item.full_name}</p>
                <p className="text-xs text-slate-400">
                  Envoyée le {formatDateTime(item.created_at)}
                  {item.faces_detected != null && <> · {item.faces_detected} visage(s) détecté(s)</>}
                </p>
                {item.pending_human_review && (
                  <p className="mt-1 inline-block rounded-full bg-red-50 px-2 py-0.5 text-[11px] font-bold text-red-600">
                    Refusée automatiquement — à confirmer
                  </p>
                )}
                {item.moderation_notes && (
                  <p className="mt-1 text-xs text-slate-500">
                    Avis : {item.moderation_notes}
                    {item.ai_checked_at && <> (IA, le {formatDateTime(item.ai_checked_at)})</>}
                  </p>
                )}
                <div className="mt-3 flex gap-2">
                  <button
                    onClick={() => review(item, true)}
                    disabled={busyId === item.id}
                    className="flex-1 rounded-lg bg-emerald-600 py-2 text-sm font-semibold text-white disabled:opacity-50"
                  >
                    Approuver
                  </button>
                  <button
                    onClick={() => review(item, false)}
                    disabled={busyId === item.id}
                    className="flex-1 rounded-lg bg-red-600 py-2 text-sm font-semibold text-white disabled:opacity-50"
                  >
                    Refuser
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* 09/10/2026 — « L'Admin ne force que s'il le veut » : dernières décisions de l'IA, à inverser si besoin */}
      <h2 className="mt-10 text-lg font-bold">Décisions de l'IA</h2>
      <p className="mt-1 text-sm text-slate-500">Les plus récentes d'abord. Forcer la décision inverse si l'IA s'est trompée.</p>
      {decisions.length === 0 ? (
        <p className="mt-4 text-sm text-slate-500">Aucune décision de l'IA pour l'instant.</p>
      ) : (
        <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
          {decisions.map((d) => (
            <div key={d.id} className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
              <img src={d.url} alt={d.full_name || "Photo"} className="aspect-square w-full object-cover" />
              <div className="p-2 text-xs">
                <p className="truncate font-semibold">{d.full_name}</p>
                <p className={`mt-0.5 inline-block rounded-full px-2 py-0.5 text-[11px] font-bold ${
                  d.status === "approved" ? "bg-emerald-50 text-emerald-700" : "bg-red-50 text-red-600"}`}>
                  {d.status === "approved" ? "Approuvée" : "Refusée"}{d.reviewed_by ? " (forcé)" : " par l'IA"}
                </p>
                {d.moderation_notes && <p className="mt-1 line-clamp-2 text-slate-500">{d.moderation_notes}</p>}
                <p className="mt-1 text-slate-400">{formatDateTime(d.ai_checked_at || d.created_at)}</p>
                <button
                  onClick={() => review(d, d.status !== "approved")}
                  disabled={busyId === d.id}
                  className={`mt-2 w-full rounded-lg py-1.5 font-semibold text-white disabled:opacity-50 ${
                    d.status === "approved" ? "bg-red-600" : "bg-emerald-600"}`}
                >
                  {d.status === "approved" ? "Forcer le refus" : "Forcer l'approbation"}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
