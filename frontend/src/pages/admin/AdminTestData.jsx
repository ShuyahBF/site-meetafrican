import { useEffect, useState } from "react";
import { apiClient, extractErrorMessage } from "@/lib/api";

const RUNNING = ["running", "purging"];

/**
 * Données de test : génère une centaine de profils fictifs (photos,
 * vidéos, swipes, matchs, conversations…) tous marqués « test », et les
 * supprime d'un clic — y compris les traces laissées par de vrais membres
 * sur ces profils. Avancement rafraîchi toutes les 3 s pendant l'opération.
 */
export default function AdminTestData() {
  const [data, setData] = useState(null);
  const [count, setCount] = useState(100);
  const [videos, setVideos] = useState(30);
  const [error, setError] = useState("");

  const load = () => apiClient.get("/admin/test-data").then((r) => setData(r.data)).catch(() => {});

  useEffect(() => {
    load();
  }, []);

  const running = RUNNING.includes(data?.job?.status);
  useEffect(() => {
    if (!running) return;
    const t = setInterval(load, 3000);
    return () => clearInterval(t);
  }, [running]);

  const generate = async () => {
    setError("");
    try {
      await apiClient.post("/admin/test-data/generate", { count: Number(count), videos: Number(videos) });
      load();
    } catch (err) {
      setError(extractErrorMessage(err, "Génération impossible"));
    }
  };

  const purge = async () => {
    if (!window.confirm("Supprimer DÉFINITIVEMENT toutes les données de test (comptes, photos, vidéos, matchs, messages…) ?")) return;
    setError("");
    try {
      await apiClient.delete("/admin/test-data");
      load();
    } catch (err) {
      setError(extractErrorMessage(err, "Suppression impossible"));
    }
  };

  if (!data) return <p className="text-slate-400">Chargement…</p>;
  const { job, counts, credentials } = data;

  return (
    <div>
      <h1 className="text-2xl font-bold">Données de test</h1>
      <p className="mt-1 text-sm text-slate-500">
        Profils fictifs pour tester le site. Tout ce qui est généré est marqué « test » (badge visible sur les
        profils) et n'est jamais compté dans les compteurs publics de la page d'accueil.
      </p>

      <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
        {[["Comptes", counts.users], ["Vidéos", counts.videos], ["Matchs", counts.matches], ["Messages", counts.messages]].map(([label, n]) => (
          <div key={label} className="rounded-xl bg-white p-4 shadow-sm ring-1 ring-slate-200">
            <p className="text-2xl font-bold">{n}</p>
            <p className="text-xs text-slate-500">{label} de test</p>
          </div>
        ))}
      </div>

      {job?.status && job.status !== "idle" && (
        <div className={`mt-6 rounded-xl p-4 text-sm ${job.status === "failed" ? "bg-red-50 text-red-700" : running ? "bg-amber-50 text-amber-800" : "bg-emerald-50 text-emerald-800"}`}>
          <p className="font-semibold">
            {running ? "⏳ " : job.status === "failed" ? "❌ " : "✅ "}
            {job.step}
            {running && job.total > 1 ? ` — ${job.progress}/${job.total}` : ""}
          </p>
          {job.error && <p className="mt-1">{job.error}</p>}
          {job.summary && (
            <p className="mt-1 text-xs opacity-80">
              {Object.entries(job.summary).map(([k, v]) => `${k} : ${v}`).join(" · ")}
            </p>
          )}
        </div>
      )}

      {error && <p className="mt-4 text-sm text-red-600">{error}</p>}

      <div className="mt-6 rounded-xl bg-white p-5 shadow-sm ring-1 ring-slate-200">
        <h2 className="font-bold">Générer</h2>
        <div className="mt-3 flex flex-wrap items-end gap-3">
          <label className="text-sm">
            <span className="block text-xs text-slate-500">Nombre de comptes (moitié hommes / femmes)</span>
            <input type="number" min={2} max={300} value={count} onChange={(e) => setCount(e.target.value)} className="admin-input w-40" />
          </label>
          <label className="text-sm">
            <span className="block text-xs text-slate-500">Nombre de vidéos</span>
            <input type="number" min={0} max={100} value={videos} onChange={(e) => setVideos(e.target.value)} className="admin-input w-40" />
          </label>
          <button onClick={generate} disabled={running} className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">
            Générer les données de test
          </button>
        </div>
        <p className="mt-2 text-xs text-slate-400">
          Comptes variés (âges, villes d'Afrique et de la diaspora, centres d'intérêt), photos, vidéos floutées,
          swipes, matchs, conversations, commentaires, demandes « Voir en clair ». Compter quelques minutes.
        </p>
      </div>

      <div className="mt-6 rounded-xl bg-white p-5 shadow-sm ring-1 ring-slate-200">
        <h2 className="font-bold">Se connecter avec un compte de test</h2>
        <p className="mt-1 text-sm">
          Mot de passe commun : <code className="rounded bg-slate-100 px-1.5 py-0.5">{credentials.password}</code>
        </p>
        {credentials.sample_accounts.length > 0 ? (
          <ul className="mt-2 space-y-1 text-sm">
            {credentials.sample_accounts.map((a) => (
              <li key={a.email} className="font-mono text-xs">{a.email} <span className="font-sans text-slate-400">({a.full_name}, {a.gender})</span></li>
            ))}
          </ul>
        ) : (
          <p className="mt-2 text-sm text-slate-400">Aucun compte de test pour l'instant.</p>
        )}
      </div>

      <div className="mt-6 rounded-xl border border-red-200 bg-red-50/40 p-5">
        <h2 className="font-bold text-red-700">Tout supprimer</h2>
        <p className="mt-1 text-sm text-slate-600">
          Supprime tous les comptes, photos, vidéos, matchs, conversations et interactions de test, ainsi que les
          traces laissées par de vrais membres sur ces profils. Les vrais comptes et les paiements réels ne sont
          jamais touchés.
        </p>
        <button onClick={purge} disabled={running || counts.users === 0} className="mt-3 rounded-lg bg-red-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">
          Supprimer toutes les données de test
        </button>
      </div>
    </div>
  );
}
