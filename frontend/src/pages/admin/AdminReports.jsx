import { useEffect, useState } from "react";
import { apiClient } from "@/lib/api";

const REASON_LABEL = {
  fake_profile: "Faux profil",
  abus: "Abus",
  autre: "Autre",
};

export default function AdminReports() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState(null);

  const load = () => {
    setLoading(true);
    apiClient.get("/admin/reports", { params: { status: "open" } }).then((r) => setItems(r.data)).finally(() => setLoading(false));
  };

  useEffect(load, []);

  const review = async (item, status, deactivate) => {
    setBusyId(item.id);
    try {
      await apiClient.post(`/admin/reports/${item.id}/review`, {
        status,
        deactivate_reported_user: deactivate,
      });
      setItems((prev) => prev.filter((r) => r.id !== item.id));
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div>
      <h1 className="text-2xl font-bold">Signalements</h1>
      <p className="mt-1 text-sm text-slate-500">Faux profils et abus signalés par les membres.</p>

      {loading ? (
        <p className="mt-6 text-slate-400">Chargement…</p>
      ) : items.length === 0 ? (
        <p className="mt-6 text-sm text-slate-500">Aucun signalement ouvert. 🎉</p>
      ) : (
        <div className="mt-6 flex flex-col divide-y divide-slate-200 rounded-xl border border-slate-200 bg-white">
          {items.map((item) => (
            <div key={item.id} className="flex flex-col gap-2 p-4">
              <div className="flex items-center justify-between">
                <span className="rounded-full bg-red-100 px-3 py-1 text-xs font-bold text-red-700">
                  {REASON_LABEL[item.reason] || item.reason}
                </span>
                <span className="text-xs text-slate-400">{new Date(item.created_at).toLocaleString("fr-FR")}</span>
              </div>
              <p className="text-sm text-slate-700">
                <strong>{item.reported_user_id}</strong> signalé par {item.reporter_user_id}
              </p>
              {item.details && <p className="text-sm text-slate-500">{item.details}</p>}
              <div className="mt-2 flex flex-wrap gap-2">
                <button
                  onClick={() => review(item, "dismissed", false)}
                  disabled={busyId === item.id}
                  className="rounded-lg bg-slate-200 px-4 py-2 text-sm font-semibold text-slate-700 disabled:opacity-50"
                >
                  Classer sans suite
                </button>
                <button
                  onClick={() => review(item, "reviewed", false)}
                  disabled={busyId === item.id}
                  className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
                >
                  Marquer traité
                </button>
                <button
                  onClick={() => review(item, "reviewed", true)}
                  disabled={busyId === item.id}
                  className="rounded-lg bg-red-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
                >
                  Désactiver le compte signalé
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
