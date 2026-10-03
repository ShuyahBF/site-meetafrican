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
        {/* Lot 53 — liste COMPLÈTE des comptes de test (pour se connecter avec des profils
            différents sur plusieurs appareils), filtrable, avec copie de l'e-mail en un clic */}
        {credentials.sample_accounts.length > 0 ? (
          <ListeComptesTest comptes={credentials.sample_accounts} />
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


/**
 * Lot 53 — tableau de tous les comptes de test : filtre (nom, e-mail, ville) et
 * sexe, bouton « Copier » de l'e-mail. Ligne cliquée = sélectionnée (règle 3).
 */
function ListeComptesTest({ comptes }) {
  const [filtre, setFiltre] = useState("");
  const [sexe, setSexe] = useState("");
  const [selection, setSelection] = useState(null);
  const [copie, setCopie] = useState("");
  const texte = filtre.trim().toLowerCase();
  const visibles = comptes.filter((a) =>
    (!sexe || a.gender === sexe)
    && (!texte || `${a.full_name} ${a.email} ${a.city || ""}`.toLowerCase().includes(texte)));

  // Copie l'e-mail dans le presse-papiers (pour le coller sur l'autre appareil)
  const copier = async (email) => {
    try {
      await navigator.clipboard.writeText(email);
      setCopie(email);
      setTimeout(() => setCopie(""), 1500);
    } catch {
      window.prompt("Copiez l'e-mail :", email);
    }
  };

  return (
    <div className="mt-3">
      <div className="flex flex-wrap items-center gap-2">
        <input value={filtre} onChange={(e) => setFiltre(e.target.value)} placeholder="Rechercher (nom, e-mail, ville)…" className="admin-input w-64" />
        <select value={sexe} onChange={(e) => setSexe(e.target.value)} className="admin-input w-40">
          <option value="">Hommes et femmes</option>
          <option value="homme">Hommes</option>
          <option value="femme">Femmes</option>
        </select>
        <span className="text-xs text-slate-500">{visibles.length} / {comptes.length} compte{comptes.length > 1 ? "s" : ""}</span>
      </div>
      <div className="mt-2 max-h-[28rem] overflow-auto rounded-lg ring-1 ring-slate-200">
        <table className="w-full text-left text-xs">
          <thead className="sticky top-0 bg-slate-50 uppercase text-slate-500">
            <tr><th className="px-2 py-2">Nom</th><th className="px-2 py-2">E-mail (identifiant)</th><th className="px-2 py-2">Sexe</th><th className="px-2 py-2">Ville</th><th className="px-2 py-2">Vérifié</th><th /></tr>
          </thead>
          <tbody>
            {visibles.map((a) => (
              <tr key={a.email} onClick={() => setSelection(a.email)} aria-selected={selection === a.email}
                className={`cursor-pointer border-t border-slate-100 ${selection === a.email ? "ligne-selectionnee" : ""}`}>
                <td className="px-2 py-1.5 font-semibold">{a.full_name}</td>
                <td className="px-2 py-1.5 font-mono">{a.email}</td>
                <td className="px-2 py-1.5">{a.gender === "homme" ? "Homme" : "Femme"}</td>
                <td className="px-2 py-1.5">{a.city || "—"}</td>
                <td className="px-2 py-1.5">{a.verification_status === "verified" ? "Oui" : "Non"}</td>
                <td className="px-2 py-1.5 text-right">
                  <button type="button" onClick={(e) => { e.stopPropagation(); copier(a.email); }}
                    className="rounded-md bg-slate-100 px-2 py-1 font-bold text-slate-700 hover:bg-slate-200">
                    {copie === a.email ? "Copié ✓" : "Copier"}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
