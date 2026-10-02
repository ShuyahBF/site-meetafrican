import { useCallback, useEffect, useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { apiClient, extractErrorMessage } from "@/lib/api";
import { formatDateTime } from "@/lib/format";

const STATUTS = {
  ENVOYE: "bg-emerald-50 text-emerald-700",
  ECHEC: "bg-rose-50 text-rose-700",
  NON_CONFIGURE: "bg-slate-100 text-slate-600",
};

const REGIONS = { "api.zeptomail.com": ".com (monde)", "api.zeptomail.eu": ".eu (Europe)", "api.zeptomail.in": ".in (Inde)" };
const SECURITES = { starttls: "STARTTLS (port 587)", ssl: "SSL (port 465)", aucune: "Aucune" };

/** Champ texte libellé. */
function Champ({ label, aide, ...props }) {
  return (
    <label className="text-sm font-semibold text-slate-700">
      {label}
      <input {...props} className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 font-normal" />
      {aide && <span className="mt-0.5 block text-xs font-normal text-slate-500">{aide}</span>}
    </label>
  );
}

/**
 * Envoi des e-mails de la plateforme (administrateur principal) : choix du service
 * (Resend, ZeptoMail, Brevo, SMTP ou Désactivé), essai avec les réglages enregistrés,
 * journal des modifications et des derniers envois. Les e-mails s'ajoutent aux
 * messages WhatsApp / SMS (alertes, rapports, avertissements du cycle de vie).
 * Les clés et mots de passe ne sont jamais renvoyés par le serveur.
 */
export default function AdminEnvoiEmails() {
  const { user } = useAuth();
  const [reglages, setReglages] = useState(null);
  const [form, setForm] = useState(null);
  const [journal, setJournal] = useState({ modifications: [], envois: [] });
  const [message, setMessage] = useState("");
  const [essai, setEssai] = useState({ destinataire: "", resultat: null, enCours: false });

  const charger = useCallback(async () => {
    const [r, j] = await Promise.all([
      apiClient.get("/plateforme/parametres/email"),
      apiClient.get("/plateforme/parametres/email/journal"),
    ]);
    setReglages(r.data);
    setForm({ ...r.data, cle_api: "", smtp_mot_de_passe: "" });
    setJournal(j.data);
  }, []);

  useEffect(() => {
    if (user?.role === "admin") charger().catch(() => {});
  }, [user, charger]);

  if (user?.role !== "admin") {
    return <p className="rounded-2xl bg-white p-6 text-sm text-slate-500 shadow-sm">Cette page est réservée à l'administrateur principal.</p>;
  }
  if (!form) return null;

  const champ = (cle) => (e) => setForm({ ...form, [cle]: e.target.type === "checkbox" ? e.target.checked : e.target.value });
  const fournisseur = form.fournisseur;
  const aCle = ["resend", "zeptomail", "brevo"].includes(fournisseur);
  const choix = reglages.choix.find((c) => c.valeur === fournisseur);

  const enregistrer = async (e) => {
    e.preventDefault();
    setMessage("");
    const corps = {
      fournisseur, actif: !!form.actif, expediteur: form.expediteur || "", nom_expediteur: form.nom_expediteur || "",
    };
    if (aCle && form.cle_api) corps.cle_api = form.cle_api;           // vide = clé conservée
    if (fournisseur === "zeptomail") corps.zeptomail_hote = form.zeptomail_hote;
    if (fournisseur === "smtp") {
      Object.assign(corps, {
        smtp_hote: form.smtp_hote || "", smtp_port: Number(form.smtp_port) || 587,
        smtp_securite: form.smtp_securite, smtp_utilisateur: form.smtp_utilisateur || "",
      });
      if (form.smtp_mot_de_passe) corps.smtp_mot_de_passe = form.smtp_mot_de_passe; // vide = conservé
    }
    try {
      await apiClient.put("/plateforme/parametres/email", corps);
      await charger();
      setMessage("Réglages enregistrés.");
    } catch (err) {
      setMessage(extractErrorMessage(err, "Réglages refusés"));
    }
  };

  const envoyerEssai = async () => {
    setEssai({ ...essai, resultat: null, enCours: true });
    try {
      const r = await apiClient.post("/plateforme/parametres/email/essai", { destinataire: essai.destinataire || null });
      setEssai({ ...essai, resultat: r.data, enCours: false });
      charger().catch(() => {});
    } catch (err) {
      setEssai({ ...essai, resultat: { statut: "ECHEC", erreur: extractErrorMessage(err, "Essai impossible") }, enCours: false });
    }
  };

  const enVigueur = reglages.en_vigueur;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Envoi des e-mails</h1>
        <p className="mt-1 text-sm text-slate-500">
          Service utilisé pour les e-mails de la plateforme : alertes et rapports de la sauvegarde automatique et du cycle
          de vie (aux administrateurs), avertissements J+103, J+110 et J+112 (aux membres qui ont une adresse). Ces
          e-mails s'ajoutent aux messages WhatsApp et SMS, ils ne les remplacent jamais.
        </p>
      </div>

      <section className="rounded-2xl bg-white p-5 shadow-sm">
        <p className={`mb-4 rounded-xl border p-3 text-sm font-semibold ${enVigueur.pret ? "border-emerald-200 bg-emerald-50 text-emerald-800" : "border-amber-200 bg-amber-50 text-amber-900"}`}>
          En vigueur : {reglages.choix.find((c) => c.valeur === enVigueur.fournisseur)?.nom || enVigueur.fournisseur}
          {enVigueur.source === "variables d'environnement" && " (variables d'environnement, rien n'est réglé ici)"}
          {enVigueur.pret ? " — prêt." : ` — aucun e-mail envoyé (${enVigueur.motif}).`}
        </p>

        <form onSubmit={enregistrer} className="grid gap-4 md:grid-cols-2">
          <label className="text-sm font-semibold text-slate-700">
            Service d'envoi
            <select value={fournisseur} onChange={champ("fournisseur")} className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 font-normal">
              {reglages.choix.map((c) => <option key={c.valeur} value={c.valeur}>{c.nom}</option>)}
            </select>
            {choix?.texte && fournisseur !== "desactive" && (
              <span className="mt-0.5 block text-xs font-normal text-slate-500">
                {choix.lien ? <a href={choix.lien} target="_blank" rel="noreferrer" className="text-primary underline">{choix.texte}</a> : choix.texte}
              </span>
            )}
          </label>
          <label className="flex items-center gap-2 self-end pb-2 text-sm font-semibold">
            <input type="checkbox" checked={!!form.actif} onChange={champ("actif")} disabled={fournisseur === "desactive"} /> Envoi actif
          </label>

          {fournisseur === "smtp" && (
            <p role="alert" className="md:col-span-2 rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm font-semibold text-amber-900">
              {reglages.avertissement_smtp}
            </p>
          )}

          {fournisseur !== "desactive" && (
            <>
              <Champ label="Adresse d'expéditeur" type="email" value={form.expediteur || ""} onChange={champ("expediteur")}
                aide="Sur un domaine validé chez le fournisseur (ex. notifications@beauthentik.net)." />
              <Champ label="Nom affiché" value={form.nom_expediteur || ""} onChange={champ("nom_expediteur")} maxLength={60} />
            </>
          )}

          {aCle && (
            <Champ label="Clé API" type="password" autoComplete="new-password" value={form.cle_api} onChange={champ("cle_api")}
              placeholder={reglages.a_cle?.[fournisseur] ? "•••••••• (enregistrée)" : ""}
              aide={reglages.a_cle?.[fournisseur] ? "Laisser vide pour conserver la clé enregistrée." : "Aucune clé enregistrée."} />
          )}
          {fournisseur === "zeptomail" && (
            <label className="text-sm font-semibold text-slate-700">
              Région
              <select value={form.zeptomail_hote} onChange={champ("zeptomail_hote")} className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 font-normal">
                {reglages.zeptomail_hotes.map((h) => <option key={h} value={h}>{REGIONS[h] || h}</option>)}
              </select>
            </label>
          )}

          {fournisseur === "smtp" && (
            <>
              <Champ label="Serveur SMTP" value={form.smtp_hote || ""} onChange={champ("smtp_hote")} placeholder="smtp.exemple.net" />
              <div className="grid grid-cols-2 gap-2">
                <Champ label="Port" type="number" min={1} max={65535} value={form.smtp_port || ""} onChange={champ("smtp_port")}
                  aide="Le port 25 est bloqué par Render." />
                <label className="text-sm font-semibold text-slate-700">
                  Sécurité
                  <select value={form.smtp_securite} onChange={champ("smtp_securite")} className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 font-normal">
                    {reglages.smtp_securites.map((s) => <option key={s} value={s}>{SECURITES[s] || s}</option>)}
                  </select>
                </label>
              </div>
              <Champ label="Utilisateur" value={form.smtp_utilisateur || ""} onChange={champ("smtp_utilisateur")} autoComplete="off" />
              <Champ label="Mot de passe" type="password" autoComplete="new-password" value={form.smtp_mot_de_passe} onChange={champ("smtp_mot_de_passe")}
                placeholder={reglages.a_mot_de_passe_smtp ? "•••••••• (enregistré)" : ""}
                aide={reglages.a_mot_de_passe_smtp ? "Laisser vide pour conserver le mot de passe enregistré." : undefined} />
            </>
          )}

          <div className="md:col-span-2 flex flex-wrap items-center gap-3">
            <button type="submit" className="rounded-lg bg-primary px-4 py-2 text-sm font-bold text-white">Enregistrer</button>
            {message && <span className="text-sm text-slate-600">{message}</span>}
            {reglages.modifie_le && (
              <span className="text-xs text-slate-400">Modifié le {formatDateTime(reglages.modifie_le)} par {reglages.modifie_par}</span>
            )}
          </div>
        </form>
      </section>

      <section className="rounded-2xl bg-white p-5 shadow-sm">
        <h2 className="mb-1 text-lg font-bold">Envoyer un essai</h2>
        <p className="mb-3 text-sm text-slate-500">Utilise les réglages ENREGISTRÉS (enregistrez d'abord vos changements).</p>
        <div className="flex flex-wrap items-end gap-3">
          <Champ label="Destinataire" type="email" value={essai.destinataire} placeholder={user?.email || ""}
            onChange={(e) => setEssai({ ...essai, destinataire: e.target.value })} />
          <button type="button" onClick={envoyerEssai} disabled={essai.enCours}
            className="rounded-lg border border-primary px-4 py-2 text-sm font-bold text-primary disabled:opacity-50">
            {essai.enCours ? "Envoi…" : "Envoyer un essai"}
          </button>
        </div>
        {essai.resultat && (
          <p role="status" className={`mt-3 rounded-xl p-3 text-sm font-semibold ${STATUTS[essai.resultat.statut] || ""}`}>
            {essai.resultat.statut === "ENVOYE"
              ? `E-mail d'essai envoyé à ${essai.resultat.destinataire}.`
              : `${essai.resultat.statut === "ECHEC" ? "Échec" : "Non envoyé"} : ${essai.resultat.erreur}`}
          </p>
        )}
      </section>

      <section className="rounded-2xl bg-white p-5 shadow-sm">
        <h2 className="mb-3 text-lg font-bold">Journal des modifications</h2>
        {journal.modifications.length === 0 ? (
          <p className="text-sm text-slate-500">Aucune modification.</p>
        ) : (
          <ul className="divide-y divide-slate-100 text-sm">
            {journal.modifications.map((m) => (
              <li key={m.id} className="py-2">
                <span className="font-semibold">{formatDateTime(m.date)}</span> — {m.par} —{" "}
                {reglages.choix.find((c) => c.valeur === m.fournisseur)?.nom || m.fournisseur}
                <span className="text-slate-500"> ({[...m.champs, ...(m.secret_modifie ? ["secret modifié"] : [])].join(", ") || "—"})</span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="rounded-2xl bg-white p-5 shadow-sm">
        <h2 className="mb-3 text-lg font-bold">Derniers e-mails</h2>
        {journal.envois.length === 0 ? (
          <p className="text-sm text-slate-500">Aucun e-mail pour l'instant.</p>
        ) : (
          <ul className="divide-y divide-slate-100 text-sm">
            {journal.envois.map((e) => (
              <li key={e.id} className="flex flex-wrap items-center gap-2 py-2">
                <span className={`rounded-full px-2 py-0.5 text-xs font-bold ${STATUTS[e.statut] || ""}`}>{e.statut}</span>
                <span className="font-semibold">{formatDateTime(e.date)}</span>
                <span className="break-all">{e.destinataire}</span>
                <span className="text-slate-500">— {e.sujet}</span>
                {e.erreur && <span className="w-full text-xs text-rose-700">{e.erreur}</span>}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
