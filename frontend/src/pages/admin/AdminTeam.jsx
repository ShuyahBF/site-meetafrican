import { useEffect, useState } from "react";
import { apiClient, extractErrorMessage } from "@/lib/api";

const ROLE_LABEL = { admin: "Administrateur", moderator: "Modérateur" };

/**
 * Équipe de modération (administrateur principal uniquement) :
 * désigner un modérateur à partir de l'email de son compte, ou lui retirer
 * ce rôle. Les modérateurs traitent les photos "à revoir", les vidéos, les
 * vérifications et les signalements. Les comptes de l'équipe ne sont jamais
 * visibles des membres sur le site.
 */
export default function AdminTeam() {
  const [team, setTeam] = useState([]);
  const [email, setEmail] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  // Chargement de la liste de l'équipe
  const load = () => apiClient.get("/admin/team").then((r) => setTeam(r.data));
  useEffect(() => {
    load();
  }, []);

  // Ajout d'un modérateur par email (le compte doit déjà exister)
  const add = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await apiClient.post("/admin/team", { email: email.trim() });
      setEmail("");
      await load();
    } catch (err) {
      setError(extractErrorMessage(err, "Ajout impossible"));
    } finally {
      setBusy(false);
    }
  };

  // Retrait du rôle modérateur (le compte redevient un membre normal)
  const remove = async (member) => {
    if (!window.confirm(`Retirer le rôle de modérateur à ${member.full_name} ?`)) return;
    await apiClient.delete(`/admin/team/${member.id}`);
    await load();
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Équipe de modération</h1>
        <p className="mt-1 text-sm text-slate-500">
          Les modérateurs traitent les photos que l'IA n'a pas pu trancher, les vidéos, les vérifications d'identité et
          les signalements. Les comptes de l'équipe ne sont jamais visibles des membres.
        </p>
      </div>

      <form onSubmit={add} className="flex flex-wrap gap-2 rounded-2xl bg-white p-4 shadow-sm">
        <input
          type="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="Email du compte à désigner comme modérateur"
          className="min-w-[240px] flex-1 rounded-xl border border-slate-200 px-4 py-2 text-sm outline-none focus:border-primary"
        />
        <button disabled={busy} className="rounded-xl bg-primary px-4 py-2 text-sm font-bold text-white disabled:opacity-50">
          {busy ? "Ajout…" : "Ajouter un modérateur"}
        </button>
        {error && <p className="w-full text-sm font-semibold text-rose-600">{error}</p>}
        <p className="w-full text-xs text-slate-400">La personne doit d'abord créer un compte sur le site avec cet email.</p>
      </form>

      <div className="overflow-hidden rounded-2xl bg-white shadow-sm">
        {team.map((m) => (
          <div key={m.id} className="flex items-center justify-between border-b border-slate-100 px-4 py-3 last:border-0">
            <div>
              <p className="font-semibold">{m.full_name}</p>
              <p className="text-xs text-slate-500">
                {m.email || "—"} · {ROLE_LABEL[m.role] || m.role}
              </p>
            </div>
            {m.role === "moderator" && (
              <button onClick={() => remove(m)} className="text-sm font-semibold text-rose-600 hover:underline">
                Retirer
              </button>
            )}
          </div>
        ))}
        {team.length === 0 && <p className="px-4 py-6 text-center text-sm text-slate-400">Aucun membre dans l'équipe.</p>}
      </div>
    </div>
  );
}
