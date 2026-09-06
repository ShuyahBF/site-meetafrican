import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { apiClient } from "@/lib/api";
import BottomNav from "@/components/BottomNav";
import ProfilePhoto from "@/components/ProfilePhoto";

export default function Matches() {
  const [matches, setMatches] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    apiClient
      .get("/matches")
      .then((r) => setMatches(r.data))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="flex min-h-screen flex-col bg-background-light font-display dark:bg-background-dark">
      <header className="px-4 py-4">
        <h1 className="text-xl font-bold text-slate-900 dark:text-white">Mes matchs</h1>
      </header>

      <main className="flex-1 px-4 pb-6">
        {loading ? (
          <p className="text-slate-400">Chargement…</p>
        ) : matches.length === 0 ? (
          <p className="mt-8 text-center text-sm text-slate-500 dark:text-slate-400">
            Pas encore de match. Continuez à découvrir des profils !
          </p>
        ) : (
          <div className="grid grid-cols-3 gap-3">
            {matches.map((m) => (
              <Link
                key={m.match_id}
                to={m.conversation_id ? `/messages/${m.conversation_id}` : "/matchs"}
                className="flex flex-col items-center gap-1"
              >
                <ProfilePhoto
                  profile={m.other_user}
                  showOnlineDot
                  className="aspect-square w-full rounded-xl"
                />
                <p className="truncate text-xs font-semibold text-slate-800 dark:text-white">
                  {m.other_user.full_name}
                </p>
              </Link>
            ))}
          </div>
        )}
      </main>

      <BottomNav />
    </div>
  );
}
