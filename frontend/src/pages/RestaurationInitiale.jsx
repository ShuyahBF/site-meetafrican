// Restauration initiale (page PUBLIQUE /restauration-initiale).
// Sur le NOUVEAU cluster MongoDB, la base est vide : si aucun compte n'existe
// (ADMIN_BOOTSTRAP_EMAIL non défini dans Render), personne ne peut se
// connecter pour cliquer sur « Importer » dans l'administration. Cette page
// (lien affiché sur la page de connexion UNIQUEMENT quand la base ne contient
// aucun compte) permet de recharger la sauvegarde.
//
// Sécurité (contrôlée par le serveur, voir backend/transfert_donnees.py) :
// possible seulement si la base n'a AUCUN compte, si le fichier a été produit
// par un serveur au même JWT_SECRET (signature), si la phrase secrète
// l'ouvre, et si l'e-mail / mot de passe sont ceux d'un administrateur actif
// CONTENU DANS la sauvegarde — rien n'est écrit avant ces vérifications.
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { apiClient, extractErrorMessage } from "@/lib/api";
import { BarreProgression, Champ, EXTENSION, PHRASE_MIN, RapportImport, useSuiviTache } from "@/components/transfert/commun";

export default function RestaurationInitiale() {
  const [disponibilite, setDisponibilite] = useState(null);
  const [form, setForm] = useState({ fichier: null, identifiant: "", mot_de_passe: "", phrase: "" });
  const [erreur, setErreur] = useState("");
  const [envoi, setEnvoi] = useState(null);
  const [tacheId, setTacheId] = useState(null);
  const tache = useSuiviTache(tacheId);

  useEffect(() => {
    apiClient.get("/plateforme/transfert/restauration-initiale")
      .then((r) => setDisponibilite(r.data))
      .catch(() => setDisponibilite({ disponible: false, motif: "Serveur injoignable pour le moment : réessayez dans une minute." }));
  }, []);

  const maj = (champ, valeur) => setForm((f) => ({ ...f, [champ]: valeur }));
  const pret = form.fichier && form.identifiant.trim() && form.mot_de_passe && form.phrase.length >= PHRASE_MIN;

  async function lancer(e) {
    e.preventDefault();
    if (!pret) return;
    const formulaire = new FormData();
    formulaire.append("fichier", form.fichier);
    formulaire.append("phrase", form.phrase);
    formulaire.append("identifiant", form.identifiant.trim());
    formulaire.append("mot_de_passe", form.mot_de_passe);
    setErreur("");
    setEnvoi(0);
    try {
      const { data } = await apiClient.post("/plateforme/transfert/restauration-initiale", formulaire, {
        timeout: 0,
        onUploadProgress: (p) => p.total && setEnvoi(Math.round((p.loaded * 100) / p.total)),
      });
      setForm((f) => ({ ...f, phrase: "", mot_de_passe: "" }));
      setTacheId(data.id);
    } catch (err) {
      setErreur(extractErrorMessage(err, "La restauration n'a pas pu démarrer"));
    } finally {
      setEnvoi(null);
    }
  }

  function recommencer() {
    setTacheId(null);
    setErreur("");
  }

  return (
    <div className="flex min-h-screen w-full items-start justify-center bg-background-light px-4 py-10 font-display text-ink sm:items-center">
      <div className="w-full max-w-xl space-y-4 rounded-2xl bg-white p-6 shadow-[0_4px_24px_rgba(18,6,11,0.08)] ring-1 ring-slate-100">
        <div>
          <h1 className="text-2xl font-bold">Restaurer une sauvegarde</h1>
          <p className="mt-1 text-sm text-slate-500">
            Pour une <b>nouvelle base de données sans aucun compte</b> (changement de cluster MongoDB) : rechargez ici
            le fichier <b>{EXTENSION}</b> exporté depuis l'ancienne base, avec la phrase secrète choisie lors de l'export
            et l'e-mail (ou téléphone) et le mot de passe de l'<b>administrateur de l'ancienne base</b>.
          </p>
        </div>

        {!disponibilite ? (
          <p className="text-sm text-slate-500">Vérification…</p>
        ) : envoi != null ? (
          <BarreProgression envoi={envoi} />
        ) : tacheId && (!tache || tache.statut === "EN_COURS") ? (
          <BarreProgression tache={tache} />
        ) : tache?.statut === "ECHEC" ? (
          <div className="space-y-4">
            <p className="rounded-xl bg-rose-50 p-3 text-sm font-semibold text-rose-700">❌ {tache.erreur}</p>
            <button type="button" className="btn-ghost w-full" onClick={recommencer}>Recommencer</button>
          </div>
        ) : tache?.statut === "TERMINE" ? (
          <div className="space-y-4">
            <RapportImport tache={tache} />
            <p className="text-sm font-semibold">Connectez-vous maintenant avec les identifiants de l'administrateur de l'ancienne base.</p>
            <Link to="/connexion" className="btn-primary w-full">Aller à la page de connexion</Link>
          </div>
        ) : !disponibilite.disponible ? (
          <div className="space-y-4">
            <p className="rounded-xl bg-amber-50 p-3 text-sm text-amber-900">{disponibilite.motif}</p>
            <Link to="/connexion" className="btn-ghost w-full">Retour à la connexion</Link>
          </div>
        ) : (
          <form onSubmit={lancer} className="space-y-4">
            <Champ label={`Fichier de sauvegarde (${EXTENSION})`}>
              <input type="file" accept={`${EXTENSION},application/octet-stream`} className="admin-input"
                onChange={(e) => maj("fichier", e.target.files?.[0] || null)} />
            </Champ>
            <Champ label="Phrase secrète choisie lors de l'export">
              <input className="admin-input" type="password" autoComplete="off" value={form.phrase} onChange={(e) => maj("phrase", e.target.value)} />
            </Champ>
            <Champ label="E-mail ou téléphone de l'administrateur (ancienne base)">
              <input className="admin-input" autoComplete="username" value={form.identifiant} onChange={(e) => maj("identifiant", e.target.value)} />
            </Champ>
            <Champ label="Mot de passe de cet administrateur" aide="Vérifié dans la sauvegarde avant toute écriture.">
              <input className="admin-input" type="password" autoComplete="current-password" value={form.mot_de_passe}
                onChange={(e) => maj("mot_de_passe", e.target.value)} />
            </Champ>
            <p className="rounded-xl bg-slate-50 p-3 text-xs text-slate-600">
              Le fichier est entièrement vérifié avant d'écrire quoi que ce soit. Il doit avoir été produit par un serveur
              beAuthentik utilisant la même clé <code className="font-mono">JWT_SECRET</code> (ne la changez pas dans Render).
            </p>
            {erreur && <p className="rounded-xl bg-rose-50 p-3 text-sm font-semibold text-rose-700">{erreur}</p>}
            <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
              <Link to="/connexion" className="btn-ghost">Annuler</Link>
              <button className="btn-primary" disabled={!pret}>Restaurer la sauvegarde</button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
