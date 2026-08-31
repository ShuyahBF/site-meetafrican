import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { apiClient, extractErrorMessage } from "@/lib/api";
import BottomNav from "@/components/BottomNav";

function primaryPhotoUrl(candidate) {
  const approved = (candidate.photos || []).filter((p) => p.status === "approved");
  const primary = approved.find((p) => p.is_primary) || approved[0];
  return primary?.url || null;
}

export default function Discover() {
  const [candidates, setCandidates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [swiping, setSwiping] = useState(false);
  const [matchInfo, setMatchInfo] = useState(null); // { other_user }
  const [error, setError] = useState("");

  const loadCandidates = () => {
    setLoading(true);
    apiClient
      .get("/discover")
      .then((r) => setCandidates(r.data))
      .catch(() => setError("Impossible de charger les profils"))
      .finally(() => setLoading(false));
  };

  useEffect(loadCandidates, []);

  const current = candidates[0];

  const act = async (action) => {
    if (!current || swiping) return;
    setSwiping(true);
    setError("");
    try {
      const res = await apiClient.post("/swipe", { target_user_id: current.id, action });
      setCandidates((prev) => prev.slice(1));
      if (res.data.matched) {
        setMatchInfo({ other_user: current });
      }
    } catch (err) {
      setError(extractErrorMessage(err, "Action impossible"));
    } finally {
      setSwiping(false);
    }
  };

  return (
    <div className="flex min-h-screen flex-col bg-background-light font-display dark:bg-background-dark">
      <header className="flex items-center justify-between px-4 py-4">
        <h1 className="text-xl font-bold text-slate-900 dark:text-white">Découvrir</h1>
      </header>

      <main className="flex flex-1 flex-col items-center justify-center px-4">
        {loading ? (
          <p className="text-slate-400">Chargement…</p>
        ) : !current ? (
          <div className="flex flex-col items-center gap-3 text-center">
            <span className="material-symbols-outlined text-5xl text-primary">favorite</span>
            <p className="text-lg font-bold text-slate-900 dark:text-white">Plus de profils pour le moment</p>
            <p className="max-w-xs text-sm text-slate-500 dark:text-slate-400">
              Revenez plus tard pour découvrir de nouvelles personnes.
            </p>
            <button onClick={loadCandidates} className="mt-2 rounded-full bg-primary px-5 py-2 text-sm font-bold text-white">
              Rafraîchir
            </button>
          </div>
        ) : (
          <div className="w-full max-w-sm overflow-hidden rounded-2xl bg-white shadow-xl dark:bg-white/5">
            <div className="aspect-[3/4] w-full bg-slate-800/10">
              {primaryPhotoUrl(current) ? (
                <img src={primaryPhotoUrl(current)} alt={current.full_name} className="h-full w-full object-cover" />
              ) : (
                <div className="flex h-full w-full items-center justify-center text-slate-400">
                  <span className="material-symbols-outlined text-6xl">person</span>
                </div>
              )}
            </div>
            <div className="p-4">
              <p className="text-lg font-bold text-slate-900 dark:text-white">
                {current.full_name}{current.age ? `, ${current.age}` : ""}
              </p>
              {current.city && <p className="text-sm text-slate-500 dark:text-slate-400">{current.city}</p>}
              {current.bio && <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">{current.bio}</p>}
            </div>
          </div>
        )}

        {error && <p className="mt-3 text-sm text-red-400">{error}</p>}

        {current && (
          <div className="mt-6 flex items-center gap-6">
            <button
              onClick={() => act("pass")}
              disabled={swiping}
              className="flex h-16 w-16 items-center justify-center rounded-full border-2 border-slate-300 text-slate-500 disabled:opacity-50 dark:border-white/20 dark:text-white"
            >
              <span className="material-symbols-outlined text-2xl">close</span>
            </button>
            <button
              onClick={() => act("like")}
              disabled={swiping}
              className="flex h-16 w-16 items-center justify-center rounded-full bg-primary text-white disabled:opacity-50"
            >
              <span className="material-symbols-outlined text-2xl">favorite</span>
            </button>
          </div>
        )}
      </main>

      <BottomNav />

      {matchInfo && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-6">
          <div className="w-full max-w-sm rounded-2xl bg-background-dark p-6 text-center">
            <span className="material-symbols-outlined text-5xl text-primary">favorite</span>
            <h2 className="mt-3 text-2xl font-bold text-primary">C'est un Match !</h2>
            <p className="mt-2 text-white">
              Vous vous plaisez mutuellement avec {matchInfo.other_user.full_name} !
            </p>
            <Link
              to="/messages"
              onClick={() => setMatchInfo(null)}
              className="mt-5 block rounded-full bg-primary px-5 py-3 text-sm font-bold text-white"
            >
              Envoyer un message
            </Link>
            <button onClick={() => setMatchInfo(null)} className="mt-3 text-sm text-slate-300">
              Continuer à swiper
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
