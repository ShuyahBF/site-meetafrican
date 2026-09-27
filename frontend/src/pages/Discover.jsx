import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { apiClient, extractErrorMessage } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import BottomNav from "@/components/BottomNav";
import ProfileCard from "@/components/ProfileCard";
import MatchCelebration from "@/components/MatchCelebration";

export default function Discover() {
  const { user, refresh } = useAuth();
  const [candidates, setCandidates] = useState([]);
  const [history, setHistory] = useState([]); // profils déjà vus, pour "Annuler"
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
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
    if (!current || busy) return;
    setBusy(true);
    setError("");
    try {
      const res = await apiClient.post("/swipe", { target_user_id: current.id, action });
      setHistory((prev) => [...prev, current]);
      setCandidates((prev) => prev.slice(1));
      if (res.data.matched) {
        setMatchInfo({ other_user: current });
      }
    } catch (err) {
      setError(extractErrorMessage(err, "Action impossible"));
    } finally {
      setBusy(false);
    }
  };

  const undo = async () => {
    if (busy || history.length === 0) return;
    setBusy(true);
    setError("");
    try {
      await apiClient.post("/swipe/undo");
      const restored = history[history.length - 1];
      setHistory((prev) => prev.slice(0, -1));
      setCandidates((prev) => [restored, ...prev]);
    } catch (err) {
      setError(extractErrorMessage(err, "Impossible d'annuler ce swipe"));
    } finally {
      setBusy(false);
    }
  };

  const sendHeart = async () => {
    if (!current || busy) return;
    setBusy(true);
    setError("");
    try {
      await apiClient.post(`/users/${current.id}/heart`);
      setCandidates((prev) => [
        { ...prev[0], hearts_received: (prev[0].hearts_received ?? 0) + 1 },
        ...prev.slice(1),
      ]);
    } catch (err) {
      setError(extractErrorMessage(err, "Impossible d'envoyer le coup de cœur"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex min-h-screen flex-col bg-background-light font-display dark:bg-background-dark">
      <header className="flex items-center justify-between px-5 pb-2 pt-5">
        <h1 className="text-2xl font-extrabold text-ink">Découvrir</h1>
        {/* Accès à la recherche avancée (maquette 10) */}
        <Link to="/recherche" aria-label="Recherche avancée" className="flex h-10 w-10 items-center justify-center rounded-full bg-slate-100 text-ink">
          <span className="material-symbols-outlined">tune</span>
        </Link>
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
            <button onClick={loadCandidates} className="btn-primary mt-2">
              Rafraîchir
            </button>
            <Link to="/moments" className="text-sm font-bold text-primary">Voir les Moments →</Link>
          </div>
        ) : (
          <ProfileCard
            profile={current}
            currentUserPoints={user?.points}
            busy={busy}
            onPass={() => act("pass")}
            onLike={() => act("like")}
            onHeart={sendHeart}
            onUndo={history.length > 0 ? undo : undefined}
            onSpend={refresh}
          />
        )}

        {error && <p className="mt-3 text-sm text-red-400">{error}</p>}
      </main>

      <BottomNav />

      {matchInfo && (
        <MatchCelebration otherUser={matchInfo.other_user} onClose={() => setMatchInfo(null)} />
      )}
    </div>
  );
}
