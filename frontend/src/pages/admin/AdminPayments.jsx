import { useEffect, useState } from "react";
import { apiClient } from "@/lib/api";

export default function AdminPayments() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState(null);

  const load = () => {
    setLoading(true);
    apiClient.get("/subscriptions/payment-proofs/pending").then((r) => setItems(r.data)).finally(() => setLoading(false));
  };

  useEffect(load, []);

  const review = async (item, approve) => {
    setBusyId(item.id);
    try {
      await apiClient.post(`/subscriptions/payment-proofs/${item.id}/review`, null, { params: { approve } });
      setItems((prev) => prev.filter((p) => p.id !== item.id));
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div>
      <h1 className="text-2xl font-bold">Preuves de paiement</h1>
      <p className="mt-1 text-sm text-slate-500">
        Paiements locaux confirmés par capture d'écran, en attente de validation manuelle.
      </p>

      {loading ? (
        <p className="mt-6 text-slate-400">Chargement…</p>
      ) : items.length === 0 ? (
        <p className="mt-6 text-sm text-slate-500">Aucune preuve en attente. 🎉</p>
      ) : (
        <div className="mt-6 flex flex-col divide-y divide-slate-200 rounded-xl border border-slate-200 bg-white">
          {items.map((item) => (
            <div key={item.id} className="flex items-center gap-4 p-4">
              <a href={item.screenshot_url} target="_blank" rel="noreferrer" className="text-sm font-semibold text-primary underline">
                Voir la capture
              </a>
              <div className="flex-1 text-xs text-slate-500">
                Utilisateur {item.user_id} · Formule {item.plan_id}
              </div>
              <div className="flex gap-2">
                <button
                  onClick={() => review(item, true)}
                  disabled={busyId === item.id}
                  className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
                >
                  Approuver
                </button>
                <button
                  onClick={() => review(item, false)}
                  disabled={busyId === item.id}
                  className="rounded-lg bg-red-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
                >
                  Refuser
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
