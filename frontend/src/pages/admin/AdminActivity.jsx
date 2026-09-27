import { useEffect, useState } from "react";
import { apiClient } from "@/lib/api";

const PAGE_SIZE = 100;

const fmtDate = (iso) =>
  new Date(iso).toLocaleString("fr-FR", { day: "2-digit", month: "2-digit", year: "2-digit", hour: "2-digit", minute: "2-digit" });

/**
 * Journal d'activité : chaque action des membres (inscription, connexion,
 * abonnement, paiement, publication, message, J'aime…) avec l'adresse IP
 * de son auteur. Filtres par membre, IP ou type d'action ; un clic sur un
 * membre affiche toutes les IP qu'il a utilisées.
 */
export default function AdminActivity() {
  const [filters, setFilters] = useState({ q: "", ip: "", action: "" });
  const [applied, setApplied] = useState(filters);
  const [data, setData] = useState({ total: 0, items: [] });
  const [skip, setSkip] = useState(0);
  const [loading, setLoading] = useState(true);
  const [summary, setSummary] = useState(null); // synthèse IP d'un membre

  useEffect(() => {
    setLoading(true);
    const params = { limit: PAGE_SIZE, skip };
    Object.entries(applied).forEach(([k, v]) => v.trim() && (params[k] = v.trim()));
    apiClient
      .get("/admin/activity", { params })
      .then((r) => setData(r.data))
      .finally(() => setLoading(false));
  }, [applied, skip]);

  const search = (e) => {
    e.preventDefault();
    setSkip(0);
    setApplied(filters);
  };

  const filterBy = (key, value) => {
    const next = { q: "", ip: "", action: "", [key]: value };
    setFilters(next);
    setSkip(0);
    setApplied(next);
  };

  const openSummary = async (userId) => {
    const r = await apiClient.get(`/admin/activity/user/${userId}`);
    setSummary(r.data);
  };

  return (
    <div>
      <h1 className="text-2xl font-bold">Activité & adresses IP</h1>
      <p className="mt-1 text-sm text-slate-500">
        Toutes les actions des membres avec leur adresse IP. Conservation automatique : 12 mois.
      </p>

      <form onSubmit={search} className="mt-4 grid gap-2 sm:grid-cols-4">
        <input className="admin-input" placeholder="Membre (nom, email, tél.)" value={filters.q} onChange={(e) => setFilters({ ...filters, q: e.target.value })} />
        <input className="admin-input font-mono" placeholder="Adresse IP" value={filters.ip} onChange={(e) => setFilters({ ...filters, ip: e.target.value })} />
        <input className="admin-input" placeholder="Action (ex. Paiement)" value={filters.action} onChange={(e) => setFilters({ ...filters, action: e.target.value })} />
        <button className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-white">Rechercher</button>
      </form>

      <p className="mt-4 text-sm text-slate-500">{data.total} action(s)</p>
      <div className="mt-2 overflow-x-auto rounded-xl bg-white shadow-sm ring-1 ring-slate-200">
        <table className="w-full text-left text-sm">
          <thead className="bg-slate-50 text-xs uppercase text-slate-500">
            <tr>
              <th className="px-3 py-2">Date</th>
              <th className="px-3 py-2">Membre</th>
              <th className="px-3 py-2">Action</th>
              <th className="px-3 py-2">Adresse IP</th>
              <th className="px-3 py-2">Résultat</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {loading ? (
              <tr><td colSpan={5} className="px-3 py-6 text-center text-slate-400">Chargement…</td></tr>
            ) : data.items.length === 0 ? (
              <tr><td colSpan={5} className="px-3 py-6 text-center text-slate-400">Aucune action.</td></tr>
            ) : (
              data.items.map((item) => (
                <tr key={item.id} className="align-top">
                  <td className="whitespace-nowrap px-3 py-2 text-slate-500">{fmtDate(item.created_at)}</td>
                  <td className="px-3 py-2">
                    {item.user ? (
                      <button onClick={() => openSummary(item.user.id)} className="text-left font-semibold text-primary hover:underline">
                        {item.user.full_name}
                        {item.user.is_test_data && <span className="ml-1 rounded bg-amber-100 px-1 text-[10px] text-amber-700">TEST</span>}
                        <span className="block text-xs font-normal text-slate-400">{item.user.email || item.user.phone}</span>
                      </button>
                    ) : (
                      <span className="text-slate-400">Visiteur non connecté</span>
                    )}
                  </td>
                  <td className="px-3 py-2">
                    <button onClick={() => filterBy("action", item.action)} className="text-left hover:underline">{item.action}</button>
                  </td>
                  <td className="px-3 py-2">
                    <button onClick={() => filterBy("ip", item.ip || "")} className="font-mono text-xs hover:underline">{item.ip || "—"}</button>
                  </td>
                  <td className="px-3 py-2">
                    {item.status_code ? (
                      <span className={`rounded px-1.5 py-0.5 text-xs font-semibold ${item.status_code < 400 ? "bg-emerald-50 text-emerald-700" : "bg-red-50 text-red-600"}`}>
                        {item.status_code < 400 ? "OK" : `Échec ${item.status_code}`}
                      </span>
                    ) : (
                      <span className="text-xs text-slate-400">{item.method || ""}</span>
                    )}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <div className="mt-3 flex justify-between">
        <button disabled={skip === 0} onClick={() => setSkip(Math.max(0, skip - PAGE_SIZE))} className="text-sm font-semibold text-slate-500 disabled:opacity-40">← Plus récentes</button>
        <button disabled={skip + PAGE_SIZE >= data.total} onClick={() => setSkip(skip + PAGE_SIZE)} className="text-sm font-semibold text-slate-500 disabled:opacity-40">Plus anciennes →</button>
      </div>

      {summary && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={(e) => e.target === e.currentTarget && setSummary(null)}>
          <div className="w-full max-w-lg rounded-xl bg-white p-5 shadow-2xl">
            <p className="text-lg font-bold">{summary.user?.full_name}</p>
            <p className="text-sm text-slate-500">{summary.user?.email}</p>
            <div className="mt-3 grid grid-cols-2 gap-2 text-sm">
              <div className="rounded-lg bg-slate-50 p-2">
                <p className="text-xs text-slate-400">IP d'inscription</p>
                <p className="font-mono">{summary.user?.registration_ip || "—"}</p>
              </div>
              <div className="rounded-lg bg-slate-50 p-2">
                <p className="text-xs text-slate-400">Dernière connexion</p>
                <p className="font-mono">{summary.user?.last_login_ip || "—"}</p>
                {summary.user?.last_login_at && <p className="text-xs text-slate-400">{fmtDate(summary.user.last_login_at)}</p>}
              </div>
            </div>
            <p className="mt-4 text-xs font-bold uppercase text-slate-400">Adresses IP utilisées</p>
            <ul className="mt-1 max-h-64 divide-y divide-slate-100 overflow-y-auto text-sm">
              {summary.ips.map((row) => (
                <li key={row.ip || "none"} className="flex items-center justify-between py-2">
                  <button onClick={() => { setSummary(null); filterBy("ip", row.ip || ""); }} className="font-mono text-primary hover:underline">{row.ip || "—"}</button>
                  <span className="text-xs text-slate-500">{row.count} action(s) · dernière le {fmtDate(row.last)}</span>
                </li>
              ))}
            </ul>
            <button onClick={() => setSummary(null)} className="mt-4 w-full rounded-lg bg-slate-100 py-2 text-sm font-semibold">Fermer</button>
          </div>
        </div>
      )}
    </div>
  );
}
