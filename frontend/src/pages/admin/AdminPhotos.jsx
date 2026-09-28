import { useEffect, useState } from "react";
import { apiClient } from "@/lib/api";
import { formatDateTime } from "@/lib/format";

export default function AdminPhotos() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState(null);

  const load = () => {
    setLoading(true);
    apiClient.get("/admin/photos/pending").then((r) => setItems(r.data)).finally(() => setLoading(false));
  };

  useEffect(load, []);

  const review = async (item, approve) => {
    setBusyId(item.id);
    try {
      await apiClient.post(`/admin/photos/${item.user_id}/${item.id}/review`, null, { params: { approve } });
      setItems((prev) => prev.filter((p) => p.id !== item.id));
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div>
      <h1 className="text-2xl font-bold">Modération des photos</h1>
      <p className="mt-1 text-sm text-slate-500">
        Photos que l'IA n'a pas pu trancher, et photos refusées d'office (plus de 2 visages) soumises quand même à
        une revue humaine. Chaque décision est horodatée.
      </p>

      {loading ? (
        <p className="mt-6 text-slate-400">Chargement…</p>
      ) : items.length === 0 ? (
        <p className="mt-6 text-sm text-slate-500">Aucune photo en attente. 🎉</p>
      ) : (
        <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {items.map((item) => (
            <div key={item.id} className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
              <img src={item.url} alt="" className="aspect-square w-full object-cover" />
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
                    Raison : {item.moderation_notes}
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
    </div>
  );
}
