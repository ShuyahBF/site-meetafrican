import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import BoutonTikTok from "@/components/BoutonTikTok";
import { useAuth } from "@/context/AuthContext";
import { extractErrorMessage } from "@/lib/api";

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
    <div className="flex min-h-screen w-full flex-col bg-background-light px-6 py-10 font-display dark:bg-background-dark">
      <h1 className="mb-6 text-2xl font-bold text-slate-900 dark:text-white">Créer un compte</h1>

      {tiktok ? (
        <p className="mb-4 flex items-center gap-3 rounded-2xl bg-slate-50 p-3 text-sm text-slate-700">
          {tiktok.avatar_url && <img src={tiktok.avatar_url} alt="" className="h-9 w-9 rounded-full object-cover" />}
          <span>Compte TikTok <b>{tiktok.nom}</b> : complétez votre inscription (âge et e-mail ou téléphone obligatoires).</span>
        </p>
      ) : (
        <div className="mb-4"><BoutonTikTok onErreur={setError} /></div>
      )}

      <form onSubmit={submit} className="flex flex-1 flex-col gap-4">
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
          <input required type="password" minLength={8} value={form.password} onChange={update("password")} className="input" />
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
      </form>
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
