import { useEffect, useState } from "react";
import { apiClient } from "@/lib/api";

export default function AdminVerifications() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState(null);

  const load = () => {
    setLoading(true);
    apiClient.get("/admin/verification/pending").then((r) => setItems(r.data)).finally(() => setLoading(false));
  };

  useEffect(load, []);

  const review = async (item, approve) => {
    setBusyId(item.id);
    try {
      await apiClient.post(`/admin/verification/${item.id}/review`, null, { params: { approve } });
      setItems((prev) => prev.filter((p) => p.id !== item.id));
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div>
      <h1 className="text-2xl font-bold">Vérification d'identité</h1>
      <p className="mt-1 text-sm text-slate-500">
        Pièces d'identité que l'IA n'a pas pu valider automatiquement, ou soumises alors que l'IA était désactivée.
      </p>

      {loading ? (
        <p className="mt-6 text-slate-400">Chargement…</p>
      ) : items.length === 0 ? (
        <p className="mt-6 text-sm text-slate-500">Aucune vérification en attente. 🎉</p>
      ) : (
        <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {items.map((item) => (
            <div key={item.id} className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
              <img src={item.document_url} alt="" className="aspect-[4/3] w-full object-cover" />
              <div className="p-3">
                <p className="text-xs text-slate-400">Utilisateur : {item.user_id}</p>
                {item.ai_reason && <p className="mt-1 text-xs text-slate-500">Note IA : {item.ai_reason}</p>}
                <div className="mt-3 flex gap-2">
                  <button
                    onClick={() => review(item, true)}
                    disabled={busyId === item.id}
                    className="flex-1 rounded-lg bg-emerald-600 py-2 text-sm font-semibold text-white disabled:opacity-50"
                  >
                    Valider
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
