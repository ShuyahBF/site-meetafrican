import { useCallback, useEffect, useState } from "react";
import { apiClient, extractErrorMessage } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { dureeTexte } from "@/lib/inactivite";

const STATUTS = { aucun: "Jamais abonné", actif: "Actif", grace: "En période de grâce", expire: "Expiré (fonctions payantes coupées)" };

/**
 * Fiche membre (administrateur principal) : abonnement et grâce (délai propre au
 * membre, « Renouveler la grâce (+3 j) »), sessions ouvertes avec fermeture, et
 * durée de déconnexion après inactivité propre au membre.
 */
export default function AbonnementSessionsMembre({ userId }) {
  const [abo, setAbo] = useState(null);
  const [sessions, setSessions] = useState(null);
  const [inact, setInact] = useState(null);
  const [grace, setGrace] = useState("");
  const [duree, setDuree] = useState("");
  const [message, setMessage] = useState("");

  const charger = useCallback(() => {
    apiClient.get(`/admin/membres/${userId}/abonnement`).then((r) => {
      setAbo(r.data);
      setGrace(r.data.grace_jours_membre ?? "");
    }).catch(() => {});
    apiClient.get(`/admin/membres/${userId}/sessions`).then((r) => setSessions(r.data)).catch(() => {});
    apiClient.get(`/admin/membres/${userId}/inactivite`).then((r) => {
      setInact(r.data);
      setDuree(r.data.admin ?? "");
    }).catch(() => {});
  }, [userId]);
  useEffect(() => { charger(); }, [charger]);

  const agir = async (fonction, succes) => {
    setMessage("");
    try {
      await fonction();
      setMessage(succes);
      charger();
    } catch (err) {
      setMessage(extractErrorMessage(err, "Action refusée"));
    }
  };

  if (!abo) return null;
  const e = abo.etat;
  return (
    <section className="rounded-xl bg-white p-4 shadow-sm">
      <h2 className="mb-2 font-bold">Abonnement, sessions & inactivité</h2>
      <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-sm">
        <dt className="text-slate-500">Abonnement</dt>
        <dd className="font-semibold">{abo.suspendu ? "Compte SUSPENDU (non renouvelé)" : STATUTS[e.statut] || e.statut}</dd>
        {e.echeance && <><dt className="text-slate-500">Échéance</dt><dd>{formatDateTime(e.echeance)}</dd></>}
        {e.fin_grace && <><dt className="text-slate-500">Fin de la grâce</dt><dd>{formatDateTime(e.fin_grace)} ({e.grace_jours} j + {e.renouvellements_grace}×3 j)</dd></>}
      </dl>

      <div className="mt-3 flex flex-wrap items-end gap-2 text-sm">
        <label className="text-xs font-semibold text-slate-500">
          Délai de grâce de ce membre (0 à 30 j, vide = plateforme)
          <input type="number" min={0} max={30} value={grace} onChange={(ev) => setGrace(ev.target.value)}
            className="mt-1 block w-28 rounded-lg border border-slate-200 px-2 py-1.5" />
        </label>
        <button type="button" className="rounded-lg bg-slate-800 px-3 py-1.5 font-bold text-white"
          onClick={() => agir(() => apiClient.put(`/admin/membres/${userId}/grace`, { jours: grace === "" ? null : Number(grace) }), "Délai de grâce enregistré.")}>
          Enregistrer
        </button>
        {(e.statut === "grace" || e.statut === "expire") && (
          <button type="button" disabled={e.renouvellements_grace >= e.renouvellements_max}
            className="rounded-lg bg-rose-600 px-3 py-1.5 font-bold text-white disabled:opacity-40"
            onClick={() => agir(() => apiClient.post(`/admin/membres/${userId}/grace/renouveler`), "Grâce renouvelée (+3 jours).")}>
            Renouveler la grâce (+3 j) · {e.renouvellements_grace}/{e.renouvellements_max}
          </button>
        )}
      </div>

      {sessions && (
        <div className="mt-4">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-bold">Sessions ouvertes ({sessions.sessions.length} / {sessions.max})</h3>
            {sessions.sessions.length > 0 && (
              <button type="button" className="text-xs font-bold text-rose-600"
                onClick={() => window.confirm("Fermer toutes les sessions de ce membre ?") && agir(
                  () => apiClient.post(`/admin/membres/${userId}/sessions/fermer-toutes`), "Sessions fermées.")}>
                Tout fermer
              </button>
            )}
          </div>
          {sessions.sessions.map((s) => (
            <p key={s.id} className="flex items-center justify-between gap-2 border-b border-slate-100 py-1 text-xs last:border-0">
              <span>{s.appareil} · IP {s.ip || "—"} · ouverte {formatDateTime(s.ouverte_le)} · activité {formatDateTime(s.derniere_activite)}</span>
              <button type="button" className="font-bold text-rose-600"
                onClick={() => agir(() => apiClient.post(`/admin/membres/${userId}/sessions/${s.id}/fermer`), "Session fermée.")}>Fermer</button>
            </p>
          ))}
        </div>
      )}

      {inact && (
        <div className="mt-4 flex flex-wrap items-end gap-2 text-sm">
          <label className="text-xs font-semibold text-slate-500">
            Inactivité pour ce membre (s ; 0 = désactivée ; vide = plateforme : {dureeTexte(inact.plateforme)})
            <input type="number" min={0} max={86400} value={duree} onChange={(ev) => setDuree(ev.target.value)}
              className="mt-1 block w-36 rounded-lg border border-slate-200 px-2 py-1.5" />
          </label>
          <button type="button" className="rounded-lg bg-slate-800 px-3 py-1.5 font-bold text-white"
            onClick={() => agir(() => apiClient.put(`/admin/membres/${userId}/inactivite`, { secondes: duree === "" ? null : Number(duree) }), "Durée enregistrée.")}>
            Enregistrer
          </button>
          <span className="text-xs text-slate-500">Appliquée : {dureeTexte(inact.effective)}</span>
        </div>
      )}

      {message && <p className="mt-2 text-sm text-slate-600">{message}</p>}
      {abo.historique.length > 0 && (
        <details className="mt-3 text-xs text-slate-600">
          <summary>Journal de l'abonnement ({abo.historique.length})</summary>
          {abo.historique.map((h) => <p key={h.id}>{formatDateTime(h.date)} · {h.action} · par {h.par}</p>)}
        </details>
      )}
    </section>
  );
}
