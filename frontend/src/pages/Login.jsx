import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      await login(identifier, password);
      navigate("/decouverte");
    } catch (err) {
      setError(err?.response?.data?.detail || "Identifiants invalides");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="dark flex min-h-screen w-full flex-col justify-center bg-background-light px-6 py-10 font-display dark:bg-background-dark">
      <h1 className="mb-6 text-2xl font-bold text-slate-900 dark:text-white">Se connecter</h1>

      <form onSubmit={submit} className="flex flex-col gap-4">
        <label className="flex flex-col gap-1 text-sm font-semibold text-slate-700 dark:text-slate-200">
          Email ou téléphone
          <input required value={identifier} onChange={(e) => setIdentifier(e.target.value)} className="input" />
        </label>
        <label className="flex flex-col gap-1 text-sm font-semibold text-slate-700 dark:text-slate-200">
          Mot de passe
          <input required type="password" value={password} onChange={(e) => setPassword(e.target.value)} className="input" />
        </label>

        {error && <p className="text-sm text-red-400">{error}</p>}

        <button
          type="submit"
          disabled={submitting}
          className="mt-4 h-14 w-full rounded-full bg-primary text-base font-bold text-white disabled:opacity-50"
        >
          {submitting ? "Connexion…" : "Se connecter"}
        </button>

        <p className="text-center text-sm text-slate-500 dark:text-slate-400">
          Pas encore de compte ? <Link to="/inscription" className="font-semibold text-primary">Créer un compte</Link>
        </p>
      </form>
    </div>
  );
}
