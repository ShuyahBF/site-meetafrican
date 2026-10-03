import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { apiClient, extractErrorMessage } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { dureeTexte } from "@/lib/inactivite";
import ChampMotDePasse from "@/components/ChampMotDePasse"; // lot 46 — œil pour voir la saisie

/** Bloc titré. */
function Bloc({ titre, children, action }) {
  return (
    <section className="rounded-2xl bg-white p-5 shadow-sm">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-lg font-bold">{titre}</h2>
        {action}
      </div>
      {children}
    </section>
  );
}

function Alerte({ children, couleur = "amber" }) {
  const styles = couleur === "rose" ? "border-rose-200 bg-rose-50 text-rose-800" : "border-amber-200 bg-amber-50 text-amber-900";
  return <p role="alert" className={`mb-3 rounded-xl border p-3 text-sm font-semibold ${styles}`}>{children}</p>;
}

function taille(o) {
  if (!o && o !== 0) return "—";
  return o > 1024 * 1024 ? `${(o / 1024 / 1024).toFixed(1)} Mo` : `${Math.max(1, Math.round(o / 1024))} Ko`;
}

const LIBELLES_ACTIONS = {
  avertissement_103: "Avertissement J+103", avertissement_110: "Avertissement de suspension",
  avertissement_112: "Avertissement J+112 (veille)", suspension: "Suspension (J+110)",
  archive_et_suppression: "Archive vérifiée + suppression (J+113)", suspension_levee: "Suspension levée (paiement)",
  aucune: "Aucune action",
};

/**
 * Sessions, sauvegardes & cycle de vie (administrateur principal) :
 * paramètres de la plateforme (grâce, sessions, inactivité, cycle de vie, frais de
 * réouverture), sauvegarde générale automatique vers R2 (alertes, liste,
 * restauration), cycle de vie du non-renouvellement (simulation, rapports,
 * membres suspendus, archives et réouverture) et sessions par compte.
 */
export default function AdminAbonnementsSessions() {
  const { user } = useAuth();
  if (user?.role !== "admin") {
    return <p className="rounded-2xl bg-white p-6 text-sm text-slate-500 shadow-sm">Cette page est réservée à l'administrateur principal.</p>;
  }
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Sessions, sauvegardes & cycle de vie</h1>
        <p className="mt-1 text-sm text-slate-500">
          Grâce après échéance impayée, sessions simultanées, déconnexion après inactivité, sauvegarde automatique
          et cycle de vie des abonnements non renouvelés.
        </p>
      </div>
      <Parametres />
      <SauvegardeAuto />
      <CycleVie />
      <SessionsParCompte />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Paramètres de la plateforme
// ---------------------------------------------------------------------------
function Parametres() {
  const [valeurs, setValeurs] = useState(null);
  const [message, setMessage] = useState("");

  useEffect(() => {
    apiClient.get("/plateforme/parametres/abonnements-sessions").then((r) => setValeurs(r.data)).catch(() => {});
  }, []);
  if (!valeurs) return null;

  const champ = (cle) => (e) => setValeurs({ ...valeurs, [cle]: e.target.type === "checkbox" ? e.target.checked : e.target.value });
  const enregistrer = async (e) => {
    e.preventDefault();
    setMessage("");
    const nombres = ["grace_jours_defaut", "sessions_max", "inactivite_secondes", "conservation_archives_jours", "frais_reouverture_montant"];
    const corps = {};
    nombres.forEach((k) => { corps[k] = Number(valeurs[k]); });
    corps.cycle_actif = !!valeurs.cycle_actif;
    corps.cycle_simulation = !!valeurs.cycle_simulation;
    corps.frais_reouverture_devise = valeurs.frais_reouverture_devise;
    try {
      const r = await apiClient.put("/plateforme/parametres/abonnements-sessions", corps);
      setValeurs(r.data);
      setMessage("Paramètres enregistrés.");
    } catch (err) {
      setMessage(extractErrorMessage(err, "Paramètres refusés"));
    }
  };

  const Nombre = ({ cle, label, aide, min, max }) => (
    <label className="text-sm font-semibold text-slate-700">
      {label}
      <input type="number" min={min} max={max} value={valeurs[cle] ?? ""} onChange={champ(cle)}
        className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2" />
      {aide && <span className="mt-0.5 block text-xs font-normal text-slate-500">{aide}</span>}
    </label>
  );

  return (
    <Bloc titre="Paramètres de la plateforme">
      <form onSubmit={enregistrer} className="grid gap-4 md:grid-cols-2">
        {Nombre({ cle: "grace_jours_defaut", label: "Jours de grâce après l'échéance (par défaut)", aide: "0 à 30 ; réglable aussi pour chaque membre (fiche membre).", min: 0, max: 30 })}
        {Nombre({ cle: "sessions_max", label: "Sessions simultanées par compte", aide: "1 à 20 ; au-delà, la session la moins récemment active est fermée.", min: 1, max: 20 })}
        {Nombre({ cle: "inactivite_secondes", label: "Déconnexion après inactivité (secondes)", aide: `0 = désactivée, sinon 60 à 86 400 (actuellement : ${dureeTexte(valeurs.inactivite_secondes)}).`, min: 0, max: 86400 })}
        {Nombre({ cle: "conservation_archives_jours", label: "Conservation des archives de membres (jours)", aide: "365 = 1 an, puis effacement automatique (archive R2 et médias).", min: 30, max: 3650 })}
        <div className="grid grid-cols-2 gap-2">
          {Nombre({ cle: "frais_reouverture_montant", label: "Frais de réouverture", aide: "Réouverture manuelle seulement.", min: 0 })}
          <label className="text-sm font-semibold text-slate-700">
            Devise
            <input value={valeurs.frais_reouverture_devise || ""} onChange={champ("frais_reouverture_devise")} maxLength={5}
              className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 uppercase" />
          </label>
        </div>
        <div className="space-y-2 text-sm">
          <label className="flex items-center gap-2 font-semibold">
            <input type="checkbox" checked={!!valeurs.cycle_actif} onChange={champ("cycle_actif")} /> Cycle de vie automatique
          </label>
          <label className="flex items-center gap-2 font-semibold">
            <input type="checkbox" checked={!!valeurs.cycle_simulation} onChange={champ("cycle_simulation")} /> Mode simulation (liste sans rien faire)
          </label>
        </div>
        <div className="md:col-span-2 flex items-center gap-3">
          <button type="submit" className="rounded-lg bg-primary px-4 py-2 text-sm font-bold text-white">Enregistrer</button>
          {message && <span className="text-sm text-slate-600">{message}</span>}
        </div>
      </form>
    </Bloc>
  );
}

// ---------------------------------------------------------------------------
// Sauvegarde générale automatique
// ---------------------------------------------------------------------------
function SauvegardeAuto() {
  const [etat, setEtat] = useState(null);
  const [message, setMessage] = useState("");
  const [restauration, setRestauration] = useState(null); // { cle, mot_de_passe, confirmation }
  const [tache, setTache] = useState(null);

  const charger = useCallback(() => {
    apiClient.get("/plateforme/sauvegardes-auto").then((r) => setEtat(r.data)).catch(() => {});
  }, []);
  useEffect(() => { charger(); }, [charger]);

  // Suivi de la restauration (même suivi que l'import complet)
  useEffect(() => {
    if (!tache || tache.statut !== "EN_COURS") return undefined;
    const t = setInterval(() => {
      apiClient.get(`/plateforme/transfert/taches/${tache.id}`).then((r) => setTache(r.data)).catch(() => {});
    }, 1500);
    return () => clearInterval(t);
  }, [tache]);

  if (!etat) return null;

  const lancer = async () => {
    setMessage("");
    try {
      await apiClient.post("/plateforme/sauvegardes-auto/lancer");
      setMessage("Sauvegarde lancée en tâche de fond (une seule par jour).");
      setTimeout(charger, 4000);
    } catch (err) {
      setMessage(extractErrorMessage(err, "Lancement impossible"));
    }
  };

  const restaurer = async (e) => {
    e.preventDefault();
    setMessage("");
    try {
      const r = await apiClient.post("/plateforme/sauvegardes-auto/restaurer", restauration);
      setTache(r.data);
      setRestauration(null);
    } catch (err) {
      setMessage(extractErrorMessage(err, "Restauration refusée"));
    }
  };

  const conf = etat.configuration;
  return (
    <Bloc titre="Sauvegarde générale automatique (R2)"
      action={<button type="button" onClick={lancer} disabled={!etat.active} className="rounded-lg bg-slate-800 px-3 py-1.5 text-sm font-bold text-white disabled:opacity-40">Sauvegarder maintenant</button>}>
      {etat.alerte && <Alerte couleur={etat.active ? "amber" : "rose"}>{etat.alerte}</Alerte>}
      <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-sm md:grid-cols-4">
        <dt className="text-slate-500">Dernière réussite</dt><dd>{etat.derniere_reussite ? formatDateTime(etat.derniere_reussite.fin) : "—"}</dd>
        <dt className="text-slate-500">Rétention</dt><dd>{etat.retention.quotidiennes} j / {etat.retention.hebdomadaires} sem. / {etat.retention.mensuelles} mois</dd>
        <dt className="text-slate-500">Stockage</dt><dd>{conf.stockage ? `${conf.stockage} · ${conf.bucket}/${conf.prefixe}` : "non configuré"}</dd>
        <dt className="text-slate-500">Phrase / jeton Cron</dt><dd>{conf.phrase ? "✅" : "❌"} / {conf.jeton ? "✅" : "❌"}</dd>
      </dl>
      <p className="mt-2 text-xs text-slate-500">
        Cron Job Render (chaque nuit) : POST /api/sauvegarde-auto/declencher avec l'en-tête X-Sauvegarde-Jeton.
        Le même appel lance ensuite le cycle de vie.
      </p>
      {message && <p className="mt-2 text-sm text-slate-600">{message}</p>}
      {etat.erreur_liste && <Alerte>{etat.erreur_liste}</Alerte>}

      {tache && (
        <p className="mt-3 rounded-xl bg-slate-50 p-3 text-sm">
          Restauration : <b>{tache.statut}</b> — {tache.etape} ({tache.progression} %)
          {tache.erreur && <span className="block text-rose-700">{tache.erreur}</span>}
          {tache.statut === "TERMINE" && <span className="block text-emerald-700">Restauration terminée : reconnectez-vous si nécessaire.</span>}
        </p>
      )}

      <h3 className="mt-4 text-sm font-bold">Sauvegardes sur R2 ({etat.sauvegardes.length})</h3>
      <div className="mt-1 divide-y divide-slate-100 text-sm">
        {etat.sauvegardes.length === 0 && <p className="py-2 text-slate-400">Aucune.</p>}
        {etat.sauvegardes.map((s) => (
          <div key={s.cle} className="flex flex-wrap items-center justify-between gap-2 py-1.5">
            <span className="font-mono text-xs">{s.cle.split("/").pop()}</span>
            <span className="text-xs text-slate-500">{taille(s.taille)}</span>
            <button type="button" className="text-xs font-bold text-rose-600"
              onClick={() => setRestauration({ cle: s.cle, mot_de_passe: "", confirmation: "" })}>Restaurer…</button>
          </div>
        ))}
      </div>
      {restauration && (
        <form onSubmit={restaurer} className="mt-3 space-y-2 rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm">
          <p className="font-semibold text-rose-800">
            Restaurer {restauration.cle.split("/").pop()} : TOUTES les données actuelles seront remplacées (mode « Remplacer »).
          </p>
          <ChampMotDePasse required placeholder="Votre mot de passe" value={restauration.mot_de_passe}
            onChange={(e) => setRestauration({ ...restauration, mot_de_passe: e.target.value })} className="w-full rounded-lg border px-3 py-2" />
          <input required placeholder="Tapez REMPLACER" value={restauration.confirmation}
            onChange={(e) => setRestauration({ ...restauration, confirmation: e.target.value })} className="w-full rounded-lg border px-3 py-2" />
          <div className="flex gap-2">
            <button type="submit" className="rounded-lg bg-rose-600 px-3 py-1.5 font-bold text-white">Restaurer</button>
            <button type="button" onClick={() => setRestauration(null)} className="px-3 py-1.5 font-semibold text-slate-600">Annuler</button>
          </div>
        </form>
      )}

      <h3 className="mt-4 text-sm font-bold">Journal</h3>
      <div className="mt-1 text-xs text-slate-600">
        {etat.journal.map((l) => (
          <p key={l.jour}>{l.jour} · <b>{l.statut}</b>{l.taille ? ` · ${taille(l.taille)}` : ""}{l.erreur ? ` · ${l.erreur}` : ""}</p>
        ))}
      </div>
    </Bloc>
  );
}

// ---------------------------------------------------------------------------
// Cycle de vie du non-renouvellement
// ---------------------------------------------------------------------------
function CycleVie() {
  const [etat, setEtat] = useState(null);
  const [simulation, setSimulation] = useState(null);
  const [message, setMessage] = useState("");
  const [reouverture, setReouverture] = useState(null); // { id, nom, mot_de_passe, frais_encaisses }

  const charger = useCallback(() => {
    apiClient.get("/plateforme/cycle-vie").then((r) => setEtat(r.data)).catch(() => {});
  }, []);
  useEffect(() => { charger(); }, [charger]);
  if (!etat) return null;

  const simuler = async () => {
    setMessage("");
    try {
      const r = await apiClient.post("/plateforme/cycle-vie/executer", { simulation: true });
      setSimulation(r.data);
    } catch (err) {
      setMessage(extractErrorMessage(err, "Simulation impossible"));
    }
  };

  const executer = async () => {
    if (!window.confirm("Exécuter le cycle de vie maintenant (avertissements, suspensions, archives et suppressions dues) ?")) return;
    try {
      await apiClient.post("/plateforme/cycle-vie/executer", { simulation: false });
      setMessage("Tâche lancée : le rapport apparaîtra ci-dessous.");
      setTimeout(charger, 4000);
    } catch (err) {
      setMessage(extractErrorMessage(err, "Lancement impossible"));
    }
  };

  const rouvrir = async (e) => {
    e.preventDefault();
    try {
      const r = await apiClient.post(`/plateforme/cycle-vie/archives/${reouverture.id}/rouvrir`, {
        mot_de_passe: reouverture.mot_de_passe, frais_encaisses: reouverture.frais_encaisses,
      });
      setMessage(`Compte rouvert (${Object.values(r.data.restaures).reduce((a, b) => a + b, 0)} documents restaurés).`);
      setReouverture(null);
      charger();
    } catch (err) {
      setMessage(extractErrorMessage(err, "Réouverture refusée"));
    }
  };

  const frais = etat.frais_reouverture;
  return (
    <Bloc titre="Cycle de vie du non-renouvellement"
      action={(
        <div className="flex gap-2">
          <button type="button" onClick={simuler} className="rounded-lg bg-white px-3 py-1.5 text-sm font-bold text-slate-700 ring-1 ring-slate-200">Simuler</button>
          <button type="button" onClick={executer} disabled={!etat.actif} className="rounded-lg bg-slate-800 px-3 py-1.5 text-sm font-bold text-white disabled:opacity-40">Exécuter maintenant</button>
        </div>
      )}>
      {!etat.actif && <Alerte>Cycle de vie automatique désactivé.</Alerte>}
      {etat.simulation && <Alerte>Mode simulation : la tâche quotidienne liste les actions sans rien faire.</Alerte>}
      {etat.sauvegarde_requise && <Alerte couleur="rose">Archives impossibles (aucune suppression ne sera faite) : {etat.sauvegarde_requise}</Alerte>}
      <p className="text-sm text-slate-600">
        J+{etat.etapes.avertissement} avertissement · J+{etat.etapes.suspension} suspension · J+{etat.etapes.veille} veille ·
        J+{etat.etapes.suppression} archive chiffrée vérifiée sur R2 puis suppression du compte. Conservation des archives :
        {" "}{etat.conservation_archives_jours} jours. Administrateurs, modérateurs et comptes de test exclus.
      </p>
      {message && <p className="mt-2 text-sm text-slate-600">{message}</p>}

      {simulation && (
        <div className="mt-3 rounded-xl bg-sky-50 p-3 text-sm">
          <p className="font-bold">Simulation : {simulation.actions.length} membre(s) concerné(s), rien n'a été fait</p>
          {simulation.actions.map((a) => (
            <p key={a.user_id}>{a.nom} · J+{a.jours} · {LIBELLES_ACTIONS[a.action] || a.action}</p>
          ))}
          {simulation.archives_effacees?.length > 0 && <p>{simulation.archives_effacees.length} archive(s) à effacer (conservation dépassée).</p>}
        </div>
      )}

      <h3 className="mt-4 text-sm font-bold">Membres suspendus ({etat.suspendus.length})</h3>
      {etat.suspendus.map((m) => (
        <p key={m.id} className="text-sm">
          <Link to={`/admin/membres/${m.id}`} className="text-primary">{m.full_name}</Link> · suspendu le {formatDateTime(m.cycle_vie?.suspendu_le)}
        </p>
      ))}

      <h3 className="mt-4 text-sm font-bold">Archives de membres ({etat.archives.length})</h3>
      <div className="divide-y divide-slate-100 text-sm">
        {etat.archives.map((a) => (
          <div key={a.id} className="flex flex-wrap items-center justify-between gap-2 py-1.5">
            <span>{a.nom} · {a.email || a.phone || "—"} · archivé le {formatDateTime(a.archive_le)} · <b>{a.statut}</b></span>
            {a.statut === "ARCHIVÉ" && (
              <button type="button" className="text-xs font-bold text-primary"
                onClick={() => setReouverture({ id: a.id, nom: a.nom, mot_de_passe: "", frais_encaisses: false })}>Rouvrir…</button>
            )}
          </div>
        ))}
      </div>
      {reouverture && (
        <form onSubmit={rouvrir} className="mt-3 space-y-2 rounded-xl border border-slate-200 bg-slate-50 p-3 text-sm">
          <p className="font-semibold">Rouvrir le compte de {reouverture.nom} depuis son archive</p>
          <p className="text-xs text-slate-500">Frais de réouverture : {frais.montant} {frais.devise} (encaissement manuel, hors site).</p>
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={reouverture.frais_encaisses}
              onChange={(e) => setReouverture({ ...reouverture, frais_encaisses: e.target.checked })} /> Frais encaissés
          </label>
          <ChampMotDePasse required placeholder="Votre mot de passe" value={reouverture.mot_de_passe}
            onChange={(e) => setReouverture({ ...reouverture, mot_de_passe: e.target.value })} className="w-full rounded-lg border px-3 py-2" />
          <div className="flex gap-2">
            <button type="submit" className="rounded-lg bg-primary px-3 py-1.5 font-bold text-white">Rouvrir</button>
            <button type="button" onClick={() => setReouverture(null)} className="px-3 py-1.5 font-semibold text-slate-600">Annuler</button>
          </div>
        </form>
      )}

      <h3 className="mt-4 text-sm font-bold">Rapports quotidiens</h3>
      <div className="text-xs text-slate-600">
        {etat.rapports.map((r) => (
          <details key={r.id || r.date} className="py-1">
            <summary>
              {formatDateTime(r.date)} · {r.statut} · {(r.actions || []).length} action(s) · {(r.erreurs || []).length} erreur(s)
            </summary>
            {(r.actions || []).map((a, i) => <p key={i}>{a.nom} · {LIBELLES_ACTIONS[a.action] || a.action}</p>)}
            {(r.erreurs || []).map((e, i) => <p key={`e${i}`} className="text-rose-700">{e.nom} · {e.erreur}</p>)}
          </details>
        ))}
      </div>
    </Bloc>
  );
}

// ---------------------------------------------------------------------------
// Sessions par compte
// ---------------------------------------------------------------------------
function SessionsParCompte() {
  const [donnees, setDonnees] = useState(null);
  useEffect(() => {
    apiClient.get("/admin/sessions/comptes").then((r) => setDonnees(r.data)).catch(() => {});
  }, []);
  if (!donnees) return null;
  return (
    <Bloc titre={`Sessions ouvertes par compte (maximum ${donnees.max})`}>
      <div className="divide-y divide-slate-100 text-sm">
        {donnees.comptes.length === 0 && <p className="text-slate-400">Aucune session ouverte.</p>}
        {donnees.comptes.map((c) => (
          <p key={c.user_id} className="flex justify-between py-1.5">
            <Link to={`/admin/membres/${c.user_id}`} className="text-primary">{c.nom || c.identifiant || c.user_id}</Link>
            <span>{c.sessions} session(s) · activité {formatDateTime(c.derniere_activite)}</span>
          </p>
        ))}
      </div>
    </Bloc>
  );
}
