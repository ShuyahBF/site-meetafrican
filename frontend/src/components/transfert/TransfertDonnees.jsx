// Section « Sauvegarde / transfert des données » (administrateur principal) :
// export COMPLET de la base dans un fichier chiffré (.baexport) et import de
// ce fichier, pour changer de cluster MongoDB Atlas en quelques clics.
// Chaque action exige le mot de passe de l'administrateur et une phrase
// secrète (jamais conservée : sans elle, le fichier est illisible).
import { useCallback, useEffect, useRef, useState } from "react";
import { API_BASE_URL, apiClient, extractErrorMessage } from "@/lib/api";
import {
  AvertissementPhrase, BarreProgression, Champ, EXTENSION, Fenetre, PHRASE_MIN, RapportImport,
  dateHeure, tailleLisible, useSuiviTache,
} from "./commun";
import ChampMotDePasse from "@/components/ChampMotDePasse"; // lot 46 — œil pour voir la saisie

const MOT_REMPLACER = "REMPLACER";
const BOUTON_DANGER = "inline-flex h-12 items-center justify-center rounded-full bg-rose-600 px-6 text-sm font-bold text-white shadow-lg shadow-rose-600/30 disabled:opacity-50";

// Libellés du journal des opérations
const ACTIONS = {
  export: "Export", import: "Import", telechargement_export: "Téléchargement",
  restauration_initiale: "Restauration initiale",
};
const STATUTS = {
  DEMARRE: { libelle: "Démarré", classe: "bg-slate-100 text-slate-700" },
  TERMINE: { libelle: "Terminé", classe: "bg-emerald-100 text-emerald-800" },
  ECHEC: { libelle: "Échec", classe: "bg-rose-100 text-rose-700" },
  MOT_DE_PASSE_REFUSE: { libelle: "Mot de passe refusé", classe: "bg-amber-100 text-amber-800" },
};

function Pastille({ statut }) {
  const s = STATUTS[statut] || { libelle: statut || "—", classe: "bg-slate-100 text-slate-700" };
  return <span className={`whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-semibold ${s.classe}`}>{s.libelle}</span>;
}

function Erreur({ texte }) {
  return texte ? <p className="rounded-xl bg-rose-50 p-3 text-sm font-semibold text-rose-700">{texte}</p> : null;
}

// ---------------------------------------------------------------------------
// Fenêtre « Exporter toutes les données »
// ---------------------------------------------------------------------------
function FenetreExport({ tacheInitiale, onFermer, onFini }) {
  const [form, setForm] = useState({ mot_de_passe: "", phrase: "", phrase_confirmation: "", note: false });
  const [envoi, setEnvoi] = useState(false);
  const [erreur, setErreur] = useState("");
  const [tacheId, setTacheId] = useState(tacheInitiale?.id || null);
  const [jeton, setJeton] = useState(tacheInitiale?.jeton_telechargement || null);
  const [telecharge, setTelecharge] = useState(false);
  const tache = useSuiviTache(tacheId);
  const onFiniRef = useRef(onFini);
  onFiniRef.current = onFini;
  const statut = tache?.statut;
  useEffect(() => { if (statut && statut !== "EN_COURS") onFiniRef.current?.(); }, [statut]);

  const maj = (champ, valeur) => setForm((f) => ({ ...f, [champ]: valeur }));
  const phraseOk = form.phrase.length >= PHRASE_MIN;
  const identiques = form.phrase === form.phrase_confirmation;
  const pret = form.mot_de_passe && phraseOk && identiques && form.note;

  async function lancer(e) {
    e.preventDefault();
    if (!pret) return;
    setEnvoi(true);
    setErreur("");
    try {
      const { data } = await apiClient.post("/plateforme/transfert/export", {
        mot_de_passe: form.mot_de_passe, phrase: form.phrase, phrase_confirmation: form.phrase_confirmation });
      setForm({ mot_de_passe: "", phrase: "", phrase_confirmation: "", note: true }); // rien ne reste dans la page
      setJeton(data.jeton_telechargement);
      setTacheId(data.id);
    } catch (err) {
      setErreur(extractErrorMessage(err, "L'export n'a pas pu démarrer"));
    } finally {
      setEnvoi(false);
    }
  }

  const lien = tache && jeton
    ? `${API_BASE_URL}/plateforme/transfert/taches/${tache.id}/fichier?jeton=${encodeURIComponent(jeton)}` : null;

  return (
    <Fenetre titre="Exporter toutes les données" onFermer={onFermer}>
      {!tacheId ? (
        <form onSubmit={lancer} className="space-y-4">
          <p className="text-sm text-slate-600">
            Toutes les données du site (membres, profils, messages, vidéos, abonnements, paiements, réglages…)
            sont regroupées dans <b>un seul fichier chiffré</b>, à télécharger sur votre ordinateur.
            Les photos et vidéos restent sur Cloudflare R2 : le fichier contient leurs adresses.
          </p>
          <AvertissementPhrase />
          <Champ label="Phrase secrète" aide={`${form.phrase.length} caractère(s) — au moins ${PHRASE_MIN}`}>
            <ChampMotDePasse className={`admin-input ${form.phrase && !phraseOk ? "border-rose-400" : ""}`} autoComplete="new-password"
              value={form.phrase} onChange={(e) => maj("phrase", e.target.value)} />
          </Champ>
          <Champ label="Retapez la phrase secrète" aide={form.phrase_confirmation && !identiques ? "Les deux phrases ne sont pas identiques" : null}>
            <ChampMotDePasse className={`admin-input ${form.phrase_confirmation && !identiques ? "border-rose-400" : ""}`} autoComplete="new-password"
              value={form.phrase_confirmation} onChange={(e) => maj("phrase_confirmation", e.target.value)} />
          </Champ>
          <label className="flex items-start gap-2 text-sm">
            <input type="checkbox" className="mt-1" checked={form.note} onChange={(e) => maj("note", e.target.checked)} />
            <span>J'ai noté ma phrase secrète en lieu sûr. Je sais qu'elle ne pourra pas être retrouvée.</span>
          </label>
          <Champ label="Votre mot de passe (administrateur)" aide="Demandé à chaque export, par sécurité.">
            <ChampMotDePasse className="admin-input" autoComplete="current-password" value={form.mot_de_passe}
              onChange={(e) => maj("mot_de_passe", e.target.value)} />
          </Champ>
          <Erreur texte={erreur} />
          <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
            <button type="button" className="btn-ghost" onClick={onFermer}>Annuler</button>
            <button className="btn-primary" disabled={!pret || envoi}>{envoi ? "Démarrage…" : "Lancer l'export"}</button>
          </div>
        </form>
      ) : !tache || tache.statut === "EN_COURS" ? (
        <BarreProgression tache={tache} />
      ) : tache.statut === "ECHEC" ? (
        <div className="space-y-4">
          <Erreur texte={`❌ ${tache.erreur}`} />
          <button type="button" className="btn-ghost w-full" onClick={onFermer}>Fermer</button>
        </div>
      ) : (
        <div className="space-y-4">
          <div className="rounded-xl bg-emerald-50 p-3 text-sm text-emerald-900">
            <p className="font-bold">✅ Export terminé</p>
            <p>{tache.rapport?.documents?.toLocaleString("fr-FR")} élément(s) dans {tache.rapport?.collections?.length} collection(s) · {tailleLisible(tache.taille)}</p>
          </div>
          {tache.fichier_disponible && !telecharge && lien ? (
            <>
              <a className="btn-primary w-full" href={lien} onClick={() => setTelecharge(true)}>
                ⬇ Télécharger « {tache.fichier_nom} »
              </a>
              <p className="text-xs text-slate-500">
                Le fichier ne peut être téléchargé <b>qu'une seule fois</b> : il est effacé du serveur juste après
                (ou au bout d'une heure). Rangez-le en lieu sûr, par exemple sur une clé USB et dans votre Google Drive.
              </p>
            </>
          ) : (
            <p className="rounded-xl bg-slate-50 p-3 text-sm text-slate-700">
              Le fichier a été envoyé à votre navigateur puis effacé du serveur. Vérifiez qu'il se trouve bien dans
              vos téléchargements. S'il manque, relancez simplement un export.
            </p>
          )}
          <button type="button" className="btn-ghost w-full" onClick={onFermer}>Fermer</button>
        </div>
      )}
    </Fenetre>
  );
}

// ---------------------------------------------------------------------------
// Fenêtre « Importer »
// ---------------------------------------------------------------------------
function FenetreImport({ tacheInitiale, onFermer, onFini }) {
  const [form, setForm] = useState({ fichier: null, phrase: "", mot_de_passe: "", mode: "vide", confirmation: "" });
  const [envoi, setEnvoi] = useState(null); // pourcentage d'envoi du fichier (null = pas d'envoi)
  const [erreur, setErreur] = useState("");
  const [tacheId, setTacheId] = useState(tacheInitiale?.id || null);
  const tache = useSuiviTache(tacheId);
  const onFiniRef = useRef(onFini);
  onFiniRef.current = onFini;
  const statut = tache?.statut;
  useEffect(() => { if (statut && statut !== "EN_COURS") onFiniRef.current?.(); }, [statut]);

  const maj = (champ, valeur) => setForm((f) => ({ ...f, [champ]: valeur }));
  const remplacer = form.mode === "remplacer";
  const pret = form.fichier && form.phrase && form.mot_de_passe && (!remplacer || form.confirmation.trim() === MOT_REMPLACER);

  async function lancer(e) {
    e.preventDefault();
    if (!pret) return;
    const formulaire = new FormData();
    formulaire.append("fichier", form.fichier);
    formulaire.append("phrase", form.phrase);
    formulaire.append("mot_de_passe", form.mot_de_passe);
    formulaire.append("mode", form.mode);
    formulaire.append("confirmation", form.confirmation.trim());
    setErreur("");
    setEnvoi(0);
    try {
      const { data } = await apiClient.post("/plateforme/transfert/import", formulaire, {
        timeout: 0, // gros fichier : pas de limite de durée pour l'envoi
        onUploadProgress: (p) => p.total && setEnvoi(Math.round((p.loaded * 100) / p.total)),
      });
      setForm((f) => ({ ...f, phrase: "", mot_de_passe: "" }));
      setTacheId(data.id);
    } catch (err) {
      setErreur(extractErrorMessage(err, "L'import n'a pas pu démarrer"));
    } finally {
      setEnvoi(null);
    }
  }

  return (
    <Fenetre titre="Importer des données" onFermer={onFermer} large>
      {envoi != null ? (
        <BarreProgression envoi={envoi} />
      ) : !tacheId ? (
        <form onSubmit={lancer} className="space-y-4">
          <p className="text-sm text-slate-600">
            Choisissez un fichier <b>{EXTENSION}</b> créé avec le bouton « Exporter toutes les données ».
            Le fichier est d'abord entièrement vérifié : s'il est abîmé ou si la phrase secrète est fausse,
            rien n'est modifié.
          </p>
          <Champ label={`Fichier à importer (${EXTENSION})`}>
            <input type="file" accept={`${EXTENSION},application/octet-stream`} className="admin-input"
              onChange={(e) => maj("fichier", e.target.files?.[0] || null)} />
          </Champ>
          <Champ label="Phrase secrète choisie lors de l'export">
            <ChampMotDePasse className="admin-input" autoComplete="off" value={form.phrase} onChange={(e) => maj("phrase", e.target.value)} />
          </Champ>

          <fieldset className="space-y-2">
            <legend className="mb-1 text-sm font-semibold text-slate-700">Que faire des données déjà présentes ?</legend>
            <label className={`flex items-start gap-2 rounded-xl border p-3 text-sm ${!remplacer ? "border-primary bg-primary/5" : "border-slate-200"}`}>
              <input type="radio" name="mode" className="mt-1" checked={!remplacer} onChange={() => maj("mode", "vide")} />
              <span><b>Base vide uniquement</b> (recommandé) — l'import est refusé si la nouvelle base contient déjà des
                membres ou d'autres données. Seuls les éléments créés automatiquement au démarrage du serveur
                (compte administrateur d'amorçage, formules et cadeaux par défaut, compteurs) sont remplacés.</span>
            </label>
            <label className={`flex items-start gap-2 rounded-xl border p-3 text-sm ${remplacer ? "border-rose-400 bg-rose-50" : "border-slate-200"}`}>
              <input type="radio" name="mode" className="mt-1" checked={remplacer} onChange={() => maj("mode", "remplacer")} />
              <span><b>Remplacer</b> — chaque type de données présent dans le fichier est d'abord <b>effacé</b> de la base,
                puis remplacé par le contenu du fichier. Tout ce qui a été saisi entre-temps est perdu.</span>
            </label>
          </fieldset>
          {remplacer && (
            <Champ label={`Pour confirmer, tapez ${MOT_REMPLACER}`}>
              <input className={`admin-input font-mono ${form.confirmation && form.confirmation.trim() !== MOT_REMPLACER ? "border-rose-400" : ""}`}
                value={form.confirmation} onChange={(e) => maj("confirmation", e.target.value)} placeholder={MOT_REMPLACER} autoComplete="off" />
            </Champ>
          )}

          <div className="rounded-xl border border-sky-200 bg-sky-50 p-3 text-sm text-sky-900">
            <p className="font-bold">ℹ️ Après l'import, reconnectez-vous</p>
            <p className="mt-1">
              Les comptes sont ceux du fichier : connectez-vous avec l'<b>e-mail et le mot de passe de l'administrateur
              de l'ancienne base</b>. Le compte créé au démarrage de ce serveur est remplacé.
            </p>
          </div>

          <Champ label="Votre mot de passe (administrateur)" aide="Celui avec lequel vous êtes connecté maintenant.">
            <ChampMotDePasse className="admin-input" autoComplete="current-password" value={form.mot_de_passe}
              onChange={(e) => maj("mot_de_passe", e.target.value)} />
          </Champ>
          <Erreur texte={erreur} />
          <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
            <button type="button" className="btn-ghost" onClick={onFermer}>Annuler</button>
            <button className={remplacer ? BOUTON_DANGER : "btn-primary"} disabled={!pret}>
              {remplacer ? "Remplacer les données" : "Lancer l'import"}
            </button>
          </div>
        </form>
      ) : !tache || tache.statut === "EN_COURS" ? (
        <BarreProgression tache={tache} />
      ) : tache.statut === "ECHEC" ? (
        <div className="space-y-4">
          <Erreur texte={`❌ ${tache.erreur}`} />
          <button type="button" className="btn-ghost w-full" onClick={onFermer}>Fermer</button>
        </div>
      ) : (
        <div className="space-y-4">
          <RapportImport tache={tache} />
          <p className="text-sm font-semibold">Reconnectez-vous maintenant avec les identifiants de l'administrateur de l'ancienne base.</p>
          <button type="button" className="btn-primary w-full" onClick={() => {
            localStorage.removeItem("maf_token");
            window.location.assign("/connexion");
          }}>Aller à la page de connexion</button>
        </div>
      )}
    </Fenetre>
  );
}

// ---------------------------------------------------------------------------
// Section affichée dans la page « Données & maintenance »
// ---------------------------------------------------------------------------
export default function TransfertDonnees() {
  const [etat, setEtat] = useState(null); // {base, collections, documents, tache_en_cours, historique}
  const [erreur, setErreur] = useState("");
  const [fenetre, setFenetre] = useState(null); // "export" | "import" | null

  // `silencieux` : après un import, la session peut être devenue invalide (comptes remplacés)
  const charger = useCallback(async (silencieux = false) => {
    try {
      const { data } = await apiClient.get("/plateforme/transfert");
      setEtat(data);
      setErreur("");
    } catch (err) {
      if (!silencieux) setErreur(extractErrorMessage(err, "Impossible de lire l'état de la base"));
    }
  }, []);
  useEffect(() => { charger(); }, [charger]);

  const enCours = etat?.tache_en_cours;
  return (
    <section className="space-y-4 rounded-2xl bg-white p-5 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="text-lg font-bold">💾 Sauvegarde / transfert des données</h2>
          <p className="text-sm text-slate-500">
            Pour déménager tout le site vers une nouvelle base MongoDB (par exemple quand le cluster Atlas gratuit est plein) :
          </p>
          <ol className="mt-1 list-inside list-decimal text-sm text-slate-600">
            <li>ici, <b>Exporter toutes les données</b> et télécharger le fichier ;</li>
            <li>dans Render (service <code className="rounded bg-slate-100 px-1 font-mono">meetafrican-backend</code>), remplacer <code className="rounded bg-slate-100 px-1 font-mono">MONGO_URL</code> par l'adresse de la nouvelle base ;</li>
            <li>revenir ici, se connecter, puis <b>Importer</b> le fichier (ou, si la nouvelle base n'a aucun compte, utiliser « Restaurer une sauvegarde » sur la page de connexion).</li>
          </ol>
        </div>
        <div className="flex w-full flex-col gap-2 sm:w-auto">
          <button type="button" className="btn-primary" disabled={!etat || (enCours && enCours.type !== "export")} onClick={() => setFenetre("export")}>
            ⬇ Exporter toutes les données
          </button>
          <button type="button" className="btn-ghost" disabled={!etat || (enCours && enCours.type !== "import")} onClick={() => setFenetre("import")}>
            ⬆ Importer
          </button>
        </div>
      </div>

      <Erreur texte={erreur} />
      {etat && (
        <p className="rounded-xl bg-slate-50 p-3 text-sm text-slate-700">
          Base actuelle : <b className="font-mono">{etat.base}</b> · {etat.collections} collection(s) · environ {etat.documents.toLocaleString("fr-FR")} élément(s)
          {enCours && <span className="ml-2 font-semibold text-primary">· {enCours.type === "export" ? "Export" : "Import"} en cours ({enCours.progression} %)</span>}
        </p>
      )}

      {etat?.historique?.length > 0 && (
        <details className="text-sm">
          <summary className="cursor-pointer font-semibold text-slate-700">Journal des exports et imports</summary>
          <ul className="mt-2 divide-y divide-slate-100">
            {etat.historique.map((h) => (
              <li key={h.id} className="flex flex-wrap items-center gap-2 py-2">
                <span className="w-32 shrink-0 text-slate-500">{dateHeure(h.date)}</span>
                <span className="font-semibold">{ACTIONS[h.action] || h.action}</span>
                <Pastille statut={h.statut} />
                <span className="text-slate-500">{h.email}</span>
                {h.documents != null && <span className="text-slate-500">· {h.documents.toLocaleString("fr-FR")} élément(s)</span>}
                {h.mode && <span className="text-slate-500">· mode « {h.mode === "remplacer" ? "Remplacer" : "Base vide"} »</span>}
                {h.erreur && <span className="w-full text-xs text-rose-700">{h.erreur}</span>}
              </li>
            ))}
          </ul>
        </details>
      )}

      {fenetre === "export" && (
        <FenetreExport tacheInitiale={enCours?.type === "export" ? enCours : null} onFermer={() => { setFenetre(null); charger(); }} onFini={() => charger(true)} />
      )}
      {fenetre === "import" && (
        <FenetreImport tacheInitiale={enCours?.type === "import" ? enCours : null} onFermer={() => { setFenetre(null); charger(true); }} onFini={() => charger(true)} />
      )}
    </section>
  );
}
