import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import BoutonTikTok from "@/components/BoutonTikTok";
import { useAuth } from "@/context/AuthContext";
import { extractErrorMessage } from "@/lib/api";
import ChampMotDePasse from "@/components/ChampMotDePasse"; // lot 46 — œil pour voir la saisie
import MentionVersion from "@/components/MentionVersion";
import EtatServeur from "@/components/EtatServeur"; // lot 46 — état du serveur sous le formulaire

export default function Register() {
  const { register } = useAuth();
  const navigate = useNavigate();
  // Arrivée depuis « Continuer avec TikTok » : nom pré-rempli + code de liaison
  const tiktok = useLocation().state?.tiktok || null;
  const [form, setForm] = useState({
    full_name: tiktok?.nom || "", email: "", phone: "", password: "", gender: "homme", birthdate: "",
  });
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const update = (key) => (e) => setForm({ ...form, [key]: e.target.value });

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      await register({ ...form, tiktok_lien: tiktok?.lien || null });
      navigate("/moments");
    } catch (err) {
      setError(extractErrorMessage(err, "Erreur lors de l'inscription"));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    // Lot 69 — même cadre que la page de connexion : carte de largeur limitée, CENTRÉE, logo en tête,
    // état du serveur et version en pied de carte.
    <div className="flex min-h-screen w-full items-center justify-center bg-background-light px-4 py-10 font-display dark:bg-background-dark">
      <div className="w-full max-w-sm rounded-3xl bg-white p-6 shadow-xl ring-1 ring-slate-100 dark:bg-slate-900 dark:ring-white/10">
      {/* Logo beAuthentik en tête de carte */}
      <div className="mb-4 flex flex-col items-center gap-2">
        <img src="/icone-beauthentik.svg" alt="beAuthentik" className="h-16 w-16" />
        <h1 className="text-center text-2xl font-bold text-slate-900 dark:text-white">Créer un compte</h1>
      </div>

      {tiktok ? (
        <p className="mb-4 flex items-center gap-3 rounded-2xl bg-slate-50 p-3 text-sm text-slate-700">
          {tiktok.avatar_url && <img src={tiktok.avatar_url} alt="" className="h-9 w-9 rounded-full object-cover" />}
          <span>Compte TikTok <b>{tiktok.nom}</b> : complétez votre inscription (âge et e-mail ou téléphone obligatoires).</span>
        </p>
      ) : (
        <div className="mb-4"><BoutonTikTok onErreur={setError} /></div>
      )}

      <form onSubmit={submit} className="flex flex-col gap-4">
        <Field label="Nom complet">
          <input required value={form.full_name} onChange={update("full_name")} className="input" />
        </Field>
        <Field label="Email">
          <input type="email" value={form.email} onChange={update("email")} className="input" />
        </Field>
        <Field label="Téléphone">
          <input value={form.phone} onChange={update("phone")} className="input" placeholder="+226 ..." />
        </Field>
        <Field label="Mot de passe">
          <ChampMotDePasse required minLength={8} value={form.password} onChange={update("password")} className="input" />
        </Field>
        <Field label="Date de naissance">
          <input required type="date" value={form.birthdate} onChange={update("birthdate")} className="input" />
        </Field>
        <Field label="Genre">
          <select value={form.gender} onChange={update("gender")} className="input select">
            <option value="homme">Homme</option>
            <option value="femme">Femme</option>
          </select>
        </Field>

        {error && <p className="text-sm text-red-400">{error}</p>}

        <button
          type="submit"
          disabled={submitting}
          className="mt-4 h-14 w-full rounded-full bg-primary text-base font-bold text-white disabled:opacity-50"
        >
          {submitting ? "Création…" : "Créer mon compte"}
        </button>

        {/* Acceptation des conditions : enregistrée côté serveur à l'inscription (date + version). */}
        <p className="text-center text-xs leading-relaxed text-slate-500">
          En créant un compte, vous certifiez avoir 18 ans ou plus et acceptez nos{" "}
          <Link to="/cgu" className="font-semibold text-primary underline">conditions générales d'utilisation</Link> et notre{" "}
          <Link to="/confidentialite" className="font-semibold text-primary underline">politique de confidentialité et de service</Link>.
        </p>

        <p className="text-center text-sm text-slate-500 dark:text-slate-400">
          Déjà un compte ? <Link to="/connexion" className="font-semibold text-primary">Se connecter</Link>
        </p>
        {/* Retour à la page d'accueil du site (comme sur la connexion) */}
        <p className="text-center text-sm">
          <Link to="/" className="inline-flex items-center gap-1 font-semibold text-primary">
            <span className="material-symbols-outlined text-base">arrow_back</span> Retour à l'accueil
          </Link>
        </p>
      </form>

      {/* État du serveur, puis version du déploiement en cours (règle permanente) */}
      <EtatServeur className="mt-6" />
      <MentionVersion className="mt-2" />
      </div>
    </div>
  );
}

function Field({ label, children }) {
  return (
    <label className="flex flex-col gap-1 text-sm font-semibold text-slate-700 dark:text-slate-200">
      {label}
      {children}
    </label>
  );
}
