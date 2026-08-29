import { useEffect, useState } from "react";
import { apiClient, extractErrorMessage } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";

const ROLE_LABEL = { user: "Membre", moderator: "Modérateur", admin: "Admin" };
const VERIF_LABEL = {
  unverified: "Non vérifié", pending: "En attente", verified: "Vérifié", rejected: "Refusé",
};

export default function AdminUsers() {
  const { user: me } = useAuth();
  const isSuperAdmin = me?.role === "admin";

  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const pageSize = 20;
  const [search, setSearch] = useState("");
  const [roleFilter, setRoleFilter] = useState("");
  const [activeFilter, setActiveFilter] = useState("");
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState(null);

  const load = () => {
    setLoading(true);
    apiClient
      .get("/admin/users", {
        params: {
          search: search || undefined,
          role: roleFilter || undefined,
          is_active: activeFilter === "" ? undefined : activeFilter === "true",
          page,
          page_size: pageSize,
        },
      })
      .then((r) => {
        setItems(r.data.items);
        setTotal(r.data.total);
      })
      .finally(() => setLoading(false));
  };

  useEffect(load, [page, roleFilter, activeFilter]);

  const submitSearch = (e) => {
    e.preventDefault();
    setPage(1);
    load();
  };

  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  return (
    <div>
      <h1 className="text-2xl font-bold">Comptes</h1>
      <p className="mt-1 text-sm text-slate-500">Recherche, activation/désactivation, gestion des rôles.</p>

      <form onSubmit={submitSearch} className="mt-4 flex flex-wrap gap-2">
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Nom, email ou téléphone…"
          className="admin-input max-w-xs"
        />
        <select value={roleFilter} onChange={(e) => { setRoleFilter(e.target.value); setPage(1); }} className="admin-input max-w-[180px]">
          <option value="">Tous les rôles</option>
          <option value="user">Membre</option>
          <option value="moderator">Modérateur</option>
          <option value="admin">Admin</option>
        </select>
        <select value={activeFilter} onChange={(e) => { setActiveFilter(e.target.value); setPage(1); }} className="admin-input max-w-[180px]">
          <option value="">Actif et inactif</option>
          <option value="true">Actifs seulement</option>
          <option value="false">Désactivés seulement</option>
        </select>
        <button type="submit" className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-white">
          Rechercher
        </button>
      </form>

      {loading ? (
        <p className="mt-6 text-slate-400">Chargement…</p>
      ) : (
        <>
          <div className="mt-6 overflow-x-auto rounded-xl border border-slate-200 bg-white">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500">
                  <th className="px-4 py-3">Nom</th>
                  <th className="px-4 py-3">Contact</th>
                  <th className="px-4 py-3">Rôle</th>
                  <th className="px-4 py-3">Vérification</th>
                  <th className="px-4 py-3">Statut</th>
                  <th className="px-4 py-3"></th>
                </tr>
              </thead>
              <tbody>
                {items.map((u) => (
                  <tr key={u.id} className="border-b border-slate-100 last:border-0">
                    <td className="px-4 py-3 font-semibold">{u.full_name}</td>
                    <td className="px-4 py-3 text-slate-500">{u.email || u.phone || "—"}</td>
                    <td className="px-4 py-3">{ROLE_LABEL[u.role]}</td>
                    <td className="px-4 py-3">{VERIF_LABEL[u.verification_status]}</td>
                    <td className="px-4 py-3">
                      <span className={u.is_active ? "text-emerald-600" : "text-red-500"}>
                        {u.is_active ? "Actif" : "Désactivé"}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <button onClick={() => setSelected(u.id)} className="text-sm font-semibold text-primary">
                        Détails
                      </button>
                    </td>
                  </tr>
                ))}
                {items.length === 0 && (
                  <tr><td colSpan={6} className="px-4 py-6 text-center text-slate-400">Aucun compte trouvé.</td></tr>
                )}
              </tbody>
            </table>
          </div>

          <div className="mt-4 flex items-center justify-between text-sm text-slate-500">
            <span>{total} compte(s)</span>
            <div className="flex gap-2">
              <button disabled={page <= 1} onClick={() => setPage((p) => p - 1)} className="rounded-lg border border-slate-200 px-3 py-1 disabled:opacity-40">
                Précédent
              </button>
              <span>Page {page} / {totalPages}</span>
              <button disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)} className="rounded-lg border border-slate-200 px-3 py-1 disabled:opacity-40">
                Suivant
              </button>
            </div>
          </div>
        </>
      )}

      {selected && (
        <UserDetailModal
          userId={selected}
          isSuperAdmin={isSuperAdmin}
          onClose={() => setSelected(null)}
          onChanged={load}
        />
      )}
    </div>
  );
}

function UserDetailModal({ userId, isSuperAdmin, onClose, onChanged }) {
  const [detail, setDetail] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const load = () => {
    apiClient.get(`/admin/users/${userId}`).then((r) => setDetail(r.data));
  };

  useEffect(load, [userId]);

  const toggleActive = async () => {
    setBusy(true);
    setError("");
    try {
      await apiClient.put(`/admin/users/${userId}/status`, { is_active: !detail.user.is_active });
      load();
      onChanged();
    } catch (err) {
      setError(extractErrorMessage(err, "Action impossible"));
    } finally {
      setBusy(false);
    }
  };

  const changeRole = async (role) => {
    setBusy(true);
    setError("");
    try {
      await apiClient.put(`/admin/users/${userId}/role`, { role });
      load();
      onChanged();
    } catch (err) {
      setError(extractErrorMessage(err, "Action impossible"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="max-h-[85vh] w-full max-w-lg overflow-y-auto rounded-xl bg-white p-6">
        {!detail ? (
          <p className="text-slate-400">Chargement…</p>
        ) : (
          <>
            <div className="flex items-start justify-between">
              <div>
                <h2 className="text-xl font-bold">{detail.user.full_name}</h2>
                <p className="text-sm text-slate-500">{detail.user.email || detail.user.phone}</p>
              </div>
              <button onClick={onClose} className="text-slate-400">
                <span className="material-symbols-outlined">close</span>
              </button>
            </div>

            {detail.photos?.length > 0 && (
              <div className="mt-4 flex gap-2 overflow-x-auto">
                {detail.photos.map((p) => (
                  <img key={p.id} src={p.url} alt="" className="h-20 w-20 shrink-0 rounded-lg object-cover" />
                ))}
              </div>
            )}

            <div className="mt-4 grid grid-cols-2 gap-3 text-sm">
              <Info label="Rôle" value={ROLE_LABEL[detail.user.role]} />
              <Info label="Statut" value={detail.user.is_active ? "Actif" : "Désactivé"} />
              <Info label="Vérification" value={VERIF_LABEL[detail.user.verification_status]} />
              <Info label="Points" value={detail.user.points} />
              <Info label="Note moyenne" value={detail.rating_average ? `${detail.rating_average} / 5 (${detail.rating_count})` : "Aucune"} />
              <Info label="Abonnement" value={detail.active_subscription ? "Actif" : "Aucun"} />
            </div>

            {detail.reports.length > 0 && (
              <div className="mt-4">
                <h3 className="text-sm font-bold uppercase tracking-wide text-slate-500">
                  Signalements ({detail.reports.length})
                </h3>
                <ul className="mt-2 flex flex-col gap-1">
                  {detail.reports.map((r) => (
                    <li key={r.id} className="text-sm text-slate-600">
                      <span className="font-semibold">{r.reason}</span> — {r.status}
                      {r.details && <span className="text-slate-400"> · {r.details}</span>}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {error && <p className="mt-3 text-sm text-red-500">{error}</p>}

            <div className="mt-6 flex flex-col gap-3 border-t border-slate-100 pt-4">
              <button
                onClick={toggleActive}
                disabled={busy}
                className={`rounded-lg py-2 text-sm font-semibold text-white disabled:opacity-50 ${detail.user.is_active ? "bg-red-600" : "bg-emerald-600"}`}
              >
                {detail.user.is_active ? "Désactiver le compte" : "Réactiver le compte"}
              </button>

              {isSuperAdmin && (
                <label className="flex items-center justify-between text-sm font-semibold text-slate-600">
                  Rôle
                  <select
                    value={detail.user.role}
                    onChange={(e) => changeRole(e.target.value)}
                    disabled={busy}
                    className="admin-input ml-3 max-w-[180px]"
                  >
                    <option value="user">Membre</option>
                    <option value="moderator">Modérateur</option>
                    <option value="admin">Admin</option>
                  </select>
                </label>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function Info({ label, value }) {
  return (
    <div>
      <p className="text-xs uppercase tracking-wide text-slate-400">{label}</p>
      <p className="font-semibold text-slate-800">{value}</p>
    </div>
  );
}
