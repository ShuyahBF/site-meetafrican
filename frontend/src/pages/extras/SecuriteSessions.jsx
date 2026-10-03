import { useCallback, useEffect, useState } from "react";
import PageShell from "@/components/PageShell";
import DerniereSauvegarde from "@/components/DerniereSauvegarde";
import { useAuth } from "@/context/AuthContext";
import { apiClient, extractErrorMessage } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { dureeTexte } from "@/lib/inactivite";

/**
 * « Sécurité & sessions » (Mon compte) : appareils connectés (navigateur, IP,
 * ouverture, dernière activité) avec « Fermer », déconnexion après inactivité
 * (le membre peut seulement réduire la durée fixée par l'administrateur) et date
 * de la dernière sauvegarde générale.
 *
 * Les blocs « Déconnexion après inactivité » et « Sauvegardes » ne sont montrés
 * qu'au SUPER-ADMINISTRATEUR (rôle « admin ») ; les membres ne voient que leurs
 * sessions. La déconnexion automatique continue malgré tout de s'appliquer à eux.
 */
export default function SecuriteSessions() {
  const { user } = useAuth();
  const superAdmin = user?.role === "admin";
  const [sessions, setSessions] = useState(null);
  const [max, setMax] = useState(5);
  const [inact, setInact] = useState(null);
  const [saisie, setSaisie] = useState("");
  const [message, setMessage] = useState("");

  const charger = useCallback(() => {
    apiClient.get("/auth/sessions").then((r) => { setSessions(r.data.sessions); setMax(r.data.max); }).catch(() => setSessions([]));
    // Réglage de l'inactivité : lu seulement pour le super-administrateur
    if (!superAdmin) return;
    apiClient.get("/auth/inactivite/reglage").then((r) => {
      setInact(r.data);
      setSaisie(r.data.membre ? String(r.data.membre) : "");
    }).catch(() => {});
  }, [superAdmin]);
  useEffect(() => { charger(); }, [charger]);

  const fermer = async (id) => {
    setMessage("");
    try {
      await apiClient.delete(`/auth/sessions/${id}`);
      charger();
    } catch (err) {
      setMessage(extractErrorMessage(err, "Fermeture impossible"));
    }
  };

  const fermerAutres = async () => {
    if (!window.confirm("Fermer toutes vos autres sessions ? Les autres appareils devront se reconnecter.")) return;
    await apiClient.post("/auth/sessions/fermer-autres").catch(() => {});
    charger();
  };

  const enregistrer = async (e) => {
    e.preventDefault();
    setMessage("");
    try {
      const secondes = saisie.trim() === "" ? null : Number(saisie);
      const r = await apiClient.put("/auth/inactivite/reglage", { secondes });
      setInact(r.data);
      setMessage("Réglage enregistré. Il s'appliquera à votre prochaine connexion.");
    } catch (err) {
      setMessage(extractErrorMessage(err, "Réglage refusé"));
    }
  };

  return (
    <PageShell title="Sécurité & sessions" subtitle={superAdmin ? "Appareils connectés et déconnexion automatique" : "Appareils connectés"}>
      <section className="mt-2">
        <h2 className="section-title">Sessions ouvertes ({sessions?.length ?? "…"} / {max})</h2>
        <p className="mb-3 text-xs text-slate-500">
          Au plus {max} appareils connectés en même temps : au-delà, la session la moins récemment utilisée est fermée.
        </p>
        <div className="card divide-y divide-slate-100">
          {sessions?.length === 0 && <p className="p-4 text-sm text-slate-400">Aucune session.</p>}
          {sessions?.map((s) => (
            <div key={s.id} className="flex items-center gap-3 px-4 py-3">
              <span className="material-symbols-outlined text-primary">devices</span>
              <div className="min-w-0 flex-1 text-sm">
                <p className="font-bold">{s.appareil} {s.courante && <span className="text-xs font-semibold text-emerald-600">· cet appareil</span>}</p>
                <p className="text-xs text-slate-500">
                  IP {s.ip || "—"} · ouverte le {formatDateTime(s.ouverte_le)} · activité {formatDateTime(s.derniere_activite)}
                </p>
              </div>
              {!s.courante && (
                <button type="button" onClick={() => fermer(s.id)} className="rounded-full border border-slate-200 px-3 py-1 text-xs font-bold text-rose-600">
                  Fermer
                </button>
              )}
            </div>
          ))}
        </div>
        {sessions?.length > 1 && (
          <button type="button" onClick={fermerAutres} className="mt-3 text-sm font-bold text-rose-600">Fermer toutes les autres sessions</button>
        )}
      </section>

      {superAdmin && inact && (
        <section className="mt-8">
          <h2 className="section-title">Déconnexion après inactivité</h2>
          <p className="text-sm text-slate-600">
            Durée appliquée : <b>{dureeTexte(inact.effective)}</b>
            {inact.plafond ? <> (maximum fixé par beAuthentik : {dureeTexte(inact.plafond)})</> : null}.
          </p>
          <form onSubmit={enregistrer} className="mt-3 flex items-end gap-2">
            <label className="flex-1 text-xs font-bold text-slate-500">
              Ma durée (secondes, {inact.min} à {inact.plafond || inact.max} ; vide = valeur de beAuthentik)
              <input type="number" min={inact.min} max={inact.plafond || inact.max} value={saisie}
                onChange={(e) => setSaisie(e.target.value)} className="input mt-1" />
            </label>
            <button type="submit" className="btn-primary">Enregistrer</button>
          </form>
        </section>
      )}
      {message && <p className="mt-3 text-sm text-slate-600">{message}</p>}

      {superAdmin && (
        <section className="mt-8">
          <h2 className="section-title">Sauvegardes</h2>
          <DerniereSauvegarde className="text-sm" />
        </section>
      )}
    </PageShell>
  );
}
