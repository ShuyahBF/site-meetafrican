import { useEffect, useState } from "react";
import { apiClient } from "@/lib/api";

export default function AdminVerifications() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState(null);
  const [decisions, setDecisions] = useState([]);   // dernières décisions de l'IA (que l'on peut forcer)

  const chargerDecisions = () =>
    apiClient.get("/admin/verification/decisions-ia").then((r) => setDecisions(r.data)).catch(() => setDecisions([]));

  const load = () => {
    setLoading(true);
    apiClient.get("/admin/verification/pending").then((r) => setItems(r.data)).finally(() => setLoading(false));
    chargerDecisions();
  };

  useEffect(load, []);

  const review = async (item, approve) => {
    setBusyId(item.id);
    try {
      await apiClient.post(`/admin/verification/${item.id}/review`, null, { params: { approve } });
      setItems((prev) => prev.filter((p) => p.id !== item.id));
      chargerDecisions();
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div>
      <h1 className="text-2xl font-bold">Vérification d'identité</h1>
      <p className="mt-1 text-sm text-slate-500">
        L'IA valide ou refuse seule les pièces d'identité. Ici : celles qu'elle n'a pas pu juger (doute), ou soumises
        alors que l'IA était désactivée. En bas, vous pouvez forcer n'importe quelle décision de l'IA.
      </p>

      {loading ? (
        <p className="mt-6 text-slate-400">Chargement…</p>
      ) : items.length === 0 ? (
        <p className="mt-6 text-sm text-slate-500">Aucune vérification en attente. 🎉</p>
      ) : (
        <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {items.map((item) => (
            <div key={item.id} className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
              <img src={item.document_view_url} alt="" className="aspect-[4/3] w-full object-cover" />
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

      {/* 09/10/2026 — « L'Admin ne force que s'il le veut » : dernières décisions de l'IA, à inverser si besoin */}
      <h2 className="mt-10 text-lg font-bold">Décisions de l'IA</h2>
      <p className="mt-1 text-sm text-slate-500">Les plus récentes d'abord. Forcer la décision inverse si l'IA s'est trompée.</p>
      {decisions.length === 0 ? (
        <p className="mt-4 text-sm text-slate-500">Aucune décision de l'IA en attente de contrôle.</p>
      ) : (
        <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {decisions.map((d) => (
            <div key={d.id} className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
              <img src={d.document_view_url} alt="" className="aspect-[4/3] w-full object-cover" />
              <div className="p-2 text-xs">
                <p className="truncate font-semibold">{d.full_name || d.user_id}</p>
                <p className={`mt-0.5 inline-block rounded-full px-2 py-0.5 text-[11px] font-bold ${
                  d.status === "verified" ? "bg-emerald-50 text-emerald-700" : "bg-red-50 text-red-600"}`}>
                  {d.status === "verified" ? "Validée par l'IA" : "Refusée par l'IA"}
                </p>
                {d.ai_reason && <p className="mt-1 line-clamp-2 text-slate-500">{d.ai_reason}</p>}
                <button
                  onClick={() => review(d, d.status !== "verified")}
                  disabled={busyId === d.id}
                  className={`mt-2 w-full rounded-lg py-1.5 font-semibold text-white disabled:opacity-50 ${
                    d.status === "verified" ? "bg-red-600" : "bg-emerald-600"}`}
                >
                  {d.status === "verified" ? "Forcer le refus" : "Forcer la validation"}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
