import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { extractErrorMessage } from "@/lib/api";
import GoogleAuthButton from "@/components/GoogleAuthButton";

export default function Register() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({
    full_name: "", email: "", phone: "", password: "", gender: "homme", birthdate: "",
  });
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const update = (key) => (e) => setForm({ ...form, [key]: e.target.value });

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      await register(form);
      navigate("/decouverte");
    } catch (err) {
      setError(extractErrorMessage(err, "Erreur lors de l'inscription"));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="flex min-h-screen w-full flex-col bg-background-light px-6 py-10 font-display dark:bg-background-dark">
      <h1 className="mb-6 text-2xl font-bold text-slate-900 dark:text-white">Créer un compte</h1>

      <div className="mb-6 flex flex-col gap-3">
        <GoogleAuthButton label="S'inscrire avec Google" />
        <div className="my-1 flex items-center gap-3 text-xs uppercase tracking-wider text-slate-400 dark:text-slate-500">
          <span className="h-px flex-1 bg-slate-300 dark:bg-white/10" />
          ou avec un email
          <span className="h-px flex-1 bg-slate-300 dark:bg-white/10" />
        </div>
      </div>

      <form onSubmit={submit} className="flex flex-1 flex-col gap-4" data-testid="register-form">
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
          <select value={form.gender} onChange={update("gender")} className="input">
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
