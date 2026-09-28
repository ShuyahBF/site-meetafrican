import { useCallback, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { apiClient } from "@/lib/api";
import { formatDateTime } from "@/lib/format";

// Types d'événements (filtre) et leur pastille de couleur
const TYPES = [
  { key: "", label: "Tout" },
  { key: "inscription", label: "Inscriptions", color: "bg-sky-100 text-sky-700" },
  { key: "activite", label: "Activité", color: "bg-slate-100 text-slate-600" },
  { key: "paiement", label: "Paiements", color: "bg-emerald-100 text-emerald-700" },
  { key: "moment", label: "Moments", color: "bg-pink-100 text-pink-700" },
  { key: "verification", label: "Vérifications", color: "bg-indigo-100 text-indigo-700" },
  { key: "signalement", label: "Signalements", color: "bg-red-100 text-red-700" },
  { key: "support", label: "Support", color: "bg-amber-100 text-amber-700" },
  { key: "temoignage", label: "Témoignages", color: "bg-yellow-100 text-yellow-700" },
  { key: "suivi", label: "Me suivre", color: "bg-teal-100 text-teal-700" },
];
const COLOR = Object.fromEntries(TYPES.map((t) => [t.key, t.color]));
const LABEL = Object.fromEntries(TYPES.map((t) => [t.key, t.label]));

/**
 * Chronologie : tout ce qui se passe sur le site, du plus récent au plus
 * ancien, avec le nom du membre. Un clic sur un nom ouvre sa fiche en
 * lecture seule, en invisible (aucune trace dans son historique).
 */
export default function AdminTimeline() {
  // ?user=<id> : historique d'un seul membre (depuis sa fiche)
  const [params, setParams] = useSearchParams();
  const onlyUser = params.get("user");
  const [type, setType] = useState("");
  const [q, setQ] = useState("");
  const [search, setSearch] = useState("");
  const [items, setItems] = useState([]);
  const [next, setNext] = useState(null);
  const [loading, setLoading] = useState(false);

  // Chargement (page 1, ou page suivante avec le curseur "before")
  const load = useCallback(
    async (before) => {
      setLoading(true);
      try {
        const r = await apiClient.get("/admin/timeline", {
          params: { type: type || undefined, q: search || undefined, user_id: onlyUser || undefined, before: before || undefined, limit: 100 },
        });
        setItems((prev) => (before ? [...prev, ...r.data.items] : r.data.items));
        setNext(r.data.next_before);
      } finally {
        setLoading(false);
      }
    },
    [type, search, onlyUser],
  );
  useEffect(() => {
    load();
  }, [load]);

  return (
    <div>
      <h1 className="text-2xl font-bold">Chronologie</h1>
      <p className="mt-1 text-sm text-slate-500">
        Inscriptions, activité, paiements, Moments, vérifications, signalements… du plus récent au plus ancien. Cliquez sur
        un membre pour ouvrir sa fiche en invisible.
      </p>

      {onlyUser && (
        <p className="mt-3 flex items-center gap-2 text-sm">
          <span className="rounded-full bg-primary/10 px-3 py-1 font-bold text-primary">Historique d'un seul membre</span>
          <button onClick={() => setParams({})} className="text-slate-500 underline">Tout afficher</button>
        </p>
      )}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          setSearch(q.trim());
        }}
        className="mt-4 flex flex-wrap gap-2"
      >
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Nom, email ou téléphone d'un membre"
          className="min-w-[240px] flex-1 rounded-lg border border-slate-200 px-3 py-2 text-sm"
        />
        <button className="rounded-lg bg-primary px-4 py-2 text-sm font-bold text-white">Rechercher</button>
        {search && (
          <button type="button" onClick={() => { setQ(""); setSearch(""); }} className="rounded-lg bg-slate-100 px-4 py-2 text-sm font-bold text-slate-600">
            Effacer
          </button>
        )}
      </form>

      <div className="mt-3 flex flex-wrap gap-1.5">
        {TYPES.map((t) => (
          <button
            key={t.key}
            onClick={() => setType(t.key)}
            className={`rounded-full px-3 py-1 text-xs font-bold ${type === t.key ? "bg-ink text-white" : "bg-white text-slate-600"}`}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className="mt-4 overflow-x-auto rounded-xl bg-white shadow-sm">
        <table className="w-full text-left text-sm">
          <thead className="bg-slate-50 text-xs uppercase text-slate-500">
            <tr>
              <th className="px-3 py-2">Date et heure</th>
              <th className="px-3 py-2">Type</th>
              <th className="px-3 py-2">Membre</th>
              <th className="px-3 py-2">Événement</th>
              <th className="px-3 py-2">IP</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {items.map((e, i) => (
              <tr key={`${e.type}-${e.at}-${i}`} className="align-top">
                <td className="whitespace-nowrap px-3 py-2 text-xs">{formatDateTime(e.at)}</td>
                <td className="px-3 py-2">
                  <span className={`rounded-full px-2 py-0.5 text-[11px] font-bold ${COLOR[e.type] || ""}`}>{LABEL[e.type]}</span>
                </td>
                <td className="px-3 py-2">
                  {e.user ? (
                    <Link to={`/admin/membres/${e.user.id}`} className="font-semibold text-primary hover:underline">
                      {e.user.full_name}
                    </Link>
                  ) : (
                    <span className="text-slate-400">—</span>
                  )}
                  {e.user?.is_test_data && <span className="ml-1 text-[10px] font-bold text-amber-600">TEST</span>}
                </td>
                <td className="px-3 py-2">
                  <p className="font-semibold">{e.title}</p>
                  <p className="text-xs text-slate-500">
                    {Object.entries(e.details || {})
                      .map(([k, v]) => `${k} : ${v}`)
                      .join(" · ")}
                  </p>
                </td>
                <td className="px-3 py-2 font-mono text-xs">{e.ip || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {!loading && items.length === 0 && <p className="px-4 py-6 text-center text-sm text-slate-400">Aucun événement.</p>}
      </div>
      {next && (
        <button onClick={() => load(next)} disabled={loading} className="mt-4 w-full rounded-lg bg-white py-2 text-sm font-bold text-slate-600 shadow-sm">
          {loading ? "Chargement…" : "Voir plus ancien"}
        </button>
      )}
    </div>
  );
}
