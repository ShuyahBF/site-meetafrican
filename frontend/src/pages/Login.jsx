import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import BoutonTikTok from "@/components/BoutonTikTok";
import { AvisMaintenance } from "@/components/MaintenancePlateforme";
import { useAuth } from "@/context/AuthContext";
import { apiClient, extractErrorMessage, MOTIF_DECONNEXION_KEY } from "@/lib/api";
import MentionVersion from "@/components/MentionVersion";
import EtatServeur from "@/components/EtatServeur"; // lot 46 — état du serveur sous le formulaire
import ChampMotDePasse from "@/components/ChampMotDePasse"; // lot 46 — œil pour voir la saisie

// Messages du retour de TikTok (?tiktok_erreur=…)
const ERREURS_TIKTOK = {
  refuse: "Connexion avec TikTok annulée.",
  invalide: "La connexion avec TikTok a expiré. Recommencez.",
  echec: "La connexion avec TikTok a échoué. Recommencez.",
};

export default function Login() {
  const { login, loginWithToken } = useAuth();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  // Compte TikTok pas encore lié : { nom, avatar_url, lien }
  const [tiktok, setTiktok] = useState(null);
  // Nouvelle base sans aucun compte (changement de cluster) : lien vers la restauration
  const [restaurationPossible, setRestaurationPossible] = useState(false);
  // Motif d'une déconnexion forcée (session fermée, inactivité), affiché une fois
  const [motif] = useState(() => {
    try {
      const m = sessionStorage.getItem(MOTIF_DECONNEXION_KEY);
      sessionStorage.removeItem(MOTIF_DECONNEXION_KEY);
      return m;
    } catch {
      return null;
    }
  });

  useEffect(() => {
    apiClient.get("/plateforme/transfert/restauration-initiale")
      .then((r) => setRestaurationPossible(!!r.data.disponible))
      .catch(() => setRestaurationPossible(false));
  }, []);

  const allerAccueil = (u) => navigate(u.role === "admin" || u.role === "moderator" ? "/admin" : "/moments");

  // Retour de TikTok : ?tiktok=<code à usage unique> ou ?tiktok_erreur=<motif>
  useEffect(() => {
    const code = params.get("tiktok");
    const erreur = params.get("tiktok_erreur");
    if (!code && !erreur) return;
    setParams({}, { replace: true });
    if (erreur) {
      setError(ERREURS_TIKTOK[erreur] || ERREURS_TIKTOK.echec);
      return;
    }
    apiClient.post("/auth/tiktok/finaliser", { code })
      .then((r) => {
        if (r.data.access_token) allerAccueil(loginWithToken(r.data));
        else setTiktok(r.data.inscription);
      })
      .catch((err) => setError(extractErrorMessage(err, ERREURS_TIKTOK.echec)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      // Si un compte TikTok attend d'être lié, il l'est à cette connexion
      allerAccueil(await login(identifier, password, tiktok?.lien || null));
    } catch (err) {
      setError(extractErrorMessage(err, "Identifiants invalides"));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    // Lot 46 — page CENTRÉE (comme Ster) : une carte de largeur limitée au milieu de l'écran,
    // logo en tête, formulaire, puis état du serveur et version en pied de carte.
    <div className="flex min-h-screen w-full items-center justify-center bg-background-light px-4 py-10 font-display dark:bg-background-dark">
      <div className="w-full max-w-sm rounded-3xl bg-white p-6 shadow-xl ring-1 ring-slate-100 dark:bg-slate-900 dark:ring-white/10">
      {/* Logo beAuthentik en tête de carte */}
      <div className="mb-4 flex flex-col items-center gap-2">
        <img src="/icone-beauthentik.svg" alt="beAuthentik" className="h-16 w-16" />
        <h1 className="text-center text-2xl font-bold text-slate-900 dark:text-white">Se connecter</h1>
      </div>

      {motif && (
        <div role="alert" className="mb-6 rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm font-semibold text-amber-900">{motif}</div>
      )}

      {/* Maintenance annoncée ou en cours (connexions suspendues) */}
      <AvisMaintenance />

      {restaurationPossible && (
        <div className="mb-6 rounded-2xl border border-sky-200 bg-sky-50 p-4 text-sm text-sky-900">
          <p className="font-bold">Base de données neuve</p>
          <p className="mt-1">Aucun compte n'existe encore sur ce serveur. Administrateur : rechargez la sauvegarde de l'ancienne base.</p>
          <Link to="/restauration-initiale" className="mt-2 inline-block font-semibold text-primary underline">Restaurer une sauvegarde</Link>
        </div>
      )}

      {/* Compte TikTok reconnu mais pas encore lié à un compte beAuthentik */}
      {tiktok && (
        <div className="mb-6 rounded-2xl bg-slate-50 p-4 text-sm text-slate-700">
          <div className="mb-3 flex items-center gap-3">
            {tiktok.avatar_url && <img src={tiktok.avatar_url} alt="" className="h-10 w-10 rounded-full object-cover" />}
            <p>Compte TikTok <b>{tiktok.nom}</b> reconnu.</p>
          </div>
          <Link to="/inscription" state={{ tiktok }} className="block h-12 w-full rounded-full bg-primary text-center font-bold leading-[3rem] text-white">
            Nouveau ? Terminer mon inscription
          </Link>
          <p className="mt-3 text-center text-xs text-slate-500">Déjà membre ? Connectez-vous ci-dessous : votre compte TikTok sera lié.</p>
        </div>
      )}

      <form onSubmit={submit} className="flex flex-col gap-4">
        <label className="flex flex-col gap-1 text-sm font-semibold text-slate-700 dark:text-slate-200">
          Email ou téléphone
          <input required value={identifier} onChange={(e) => setIdentifier(e.target.value)} className="input" />
        </label>
        <label className="flex flex-col gap-1 text-sm font-semibold text-slate-700 dark:text-slate-200">
          Mot de passe
          <ChampMotDePasse required value={password} onChange={(e) => setPassword(e.target.value)} className="input" />
        </label>

        {error && <p className="text-sm text-red-400">{error}</p>}

        <button
          type="submit"
          disabled={submitting}
          className="mt-4 h-14 w-full rounded-full bg-primary text-base font-bold text-white disabled:opacity-50"
        >
          {submitting ? "Connexion…" : "Se connecter"}
        </button>

        {!tiktok && (
          <>
            <p className="text-center text-xs font-semibold uppercase tracking-widest text-slate-400">ou</p>
            <BoutonTikTok onErreur={setError} />
          </>
        )}

        <p className="text-center text-sm text-slate-500 dark:text-slate-400">
          Pas encore de compte ? <Link to="/inscription" className="font-semibold text-primary">Créer un compte</Link>
        </p>
        <p className="text-center text-xs text-slate-400">
          <Link to="/cgu" className="underline">Conditions d'utilisation</Link> · <Link to="/confidentialite" className="underline">Confidentialité</Link>
        </p>
      </form>

      {/* Lot 46 — état du serveur, puis version et lot du déploiement en cours (règle permanente) */}
      <EtatServeur className="mt-6" />
      <MentionVersion className="mt-2" />
      </div>
    </div>
  );
}
