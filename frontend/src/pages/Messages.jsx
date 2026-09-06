import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { apiClient } from "@/lib/api";
import BottomNav from "@/components/BottomNav";
import ProfilePhoto from "@/components/ProfilePhoto";

export default function Messages() {
  const [conversations, setConversations] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    apiClient
      .get("/conversations")
      .then((r) => setConversations(r.data))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="flex min-h-screen flex-col bg-background-light font-display dark:bg-background-dark">
      <header className="px-4 py-4">
        <h1 className="text-xl font-bold text-slate-900 dark:text-white">Messages</h1>
      </header>

      <main className="flex-1 px-4 pb-6">
        {loading ? (
          <p className="text-slate-400">Chargement…</p>
        ) : conversations.length === 0 ? (
          <p className="mt-8 text-center text-sm text-slate-500 dark:text-slate-400">
            Aucune conversation pour l'instant.
          </p>
        ) : (
          <div className="flex flex-col divide-y divide-slate-800/10 dark:divide-white/10">
            {conversations.map((c) => (
              <Link
                key={c.conversation_id}
                to={`/messages/${c.conversation_id}`}
                className="flex items-center gap-3 py-3"
              >
                <ProfilePhoto profile={c.other_user} showOnlineDot className="h-12 w-12 shrink-0 rounded-full" />
                <div className="min-w-0 flex-1">
                  <p className="truncate font-semibold text-slate-900 dark:text-white">
                    {c.other_user.full_name}
                  </p>
                  <p className="truncate text-sm text-slate-500 dark:text-slate-400">
                    {c.last_message ? c.last_message.text : "Dites bonjour 👋"}
                  </p>
                </div>
              </Link>
            ))}
          </div>
        )}
      </main>

      <BottomNav />
    </div>
  );
}
