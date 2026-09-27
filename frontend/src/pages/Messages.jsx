import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { apiClient } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import BottomNav from "@/components/BottomNav";
import ProfilePhoto from "@/components/ProfilePhoto";
import VerifiedBadge from "@/components/VerifiedBadge";
import VideoAccessRequests from "@/components/VideoAccessRequests";
import { formatRelativeShort } from "@/lib/format";
import TestBadge from "@/components/TestBadge";

const REFRESH_MS = 15000;

/**
 * Boîte de réception (fond blanc) :
 *   - en haut, la rangée "Nouveaux matchs" (avatars cerclés du dégradé de
 *     la marque, comme les stories) — les matchs sans message encore ;
 *   - puis les conversations, triées par dernier message, avec pastille de
 *     non-lus et texte en gras tant que ce n'est pas lu.
 */
export default function Messages() {
  const { user } = useAuth();
  const [conversations, setConversations] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const load = () =>
      apiClient
        .get("/conversations")
        .then((r) => setConversations(r.data))
        .finally(() => setLoading(false));
    load();
    const t = setInterval(load, REFRESH_MS);
    return () => clearInterval(t);
  }, []);

  const newMatches = conversations.filter((c) => !c.last_message);
  const threads = conversations.filter((c) => c.last_message);

  return (
    <div className="flex min-h-[100dvh] flex-col bg-white font-display text-ink">
      <header className="flex items-center justify-between px-5 pb-2 pt-5">
        <h1 className="text-2xl font-extrabold">Messages</h1>
        <Link to="/recherche" aria-label="Rechercher des profils" className="flex h-10 w-10 items-center justify-center rounded-full bg-slate-100">
          <span className="material-symbols-outlined">person_search</span>
        </Link>
      </header>

      <main className="flex-1 pb-6">
        {/* Demandes "Voir mes Moments en clair" à traiter */}
        <VideoAccessRequests mode="pending" />
        {loading ? (
          <div className="flex justify-center py-20">
            <span className="h-9 w-9 animate-spin rounded-full border-4 border-slate-100 border-t-primary" />
          </div>
        ) : conversations.length === 0 ? (
          <div className="px-8 py-20 text-center">
            <p className="text-6xl">💌</p>
            <p className="mt-4 text-lg font-extrabold">Pas encore de conversation</p>
            <p className="mt-1 text-sm text-slate-500">Likez des profils ou des Moments : dès que c'est réciproque, vous pourrez discuter ici.</p>
            <Link to="/moments" className="btn-primary mt-6">Explorer les Moments</Link>
          </div>
        ) : (
          <>
            {newMatches.length > 0 && (
              <section className="mt-2">
                <h2 className="section-title px-5">Nouveaux matchs</h2>
                <div className="no-scrollbar flex gap-4 overflow-x-auto px-5 pb-2">
                  {newMatches.map((c) => (
                    <Link key={c.conversation_id} to={`/messages/${c.conversation_id}`} className="flex w-16 shrink-0 flex-col items-center gap-1.5">
                      {/* Anneau en dégradé + liseré blanc, façon "story" */}
                      <span className="relative block rounded-full bg-brand p-[3px]">
                        <span className="block rounded-full bg-white p-[2px]">
                          <ProfilePhoto profile={c.other_user} className="h-16 w-16 rounded-full" />
                        </span>
                        {c.other_user.is_online && (
                          <span className="absolute bottom-0.5 right-0.5 h-4 w-4 rounded-full bg-emerald-500 ring-[3px] ring-white" />
                        )}
                      </span>
                      <span className="w-full truncate text-center text-xs font-bold">{c.other_user.full_name.split(" ")[0]}</span>
                    </Link>
                  ))}
                </div>
              </section>
            )}

            {threads.length > 0 && (
              <section className="mt-4">
                <h2 className="section-title px-5">Discussions</h2>
                <div className="flex flex-col">
                  {threads.map((c) => {
                    const unread = c.unread_count > 0;
                    const fromMe = c.last_message.sender_id === user?.id;
                    return (
                      <Link
                        key={c.conversation_id}
                        to={`/messages/${c.conversation_id}`}
                        className="flex items-center gap-3 px-5 py-3 transition hover:bg-slate-50"
                      >
                        <span className="relative shrink-0">
                          <ProfilePhoto profile={c.other_user} className="h-14 w-14 rounded-full" />
                          {c.other_user.is_online && (
                            <span className="absolute bottom-0 right-0 h-3.5 w-3.5 rounded-full bg-emerald-500 ring-[3px] ring-white" />
                          )}
                        </span>
                        <div className="min-w-0 flex-1">
                          <p className="flex items-center gap-1 truncate font-extrabold">
                            {c.other_user.full_name}
                            {c.other_user.is_verified && <VerifiedBadge className="text-sm" />}
                            {c.other_user.is_test_data && <TestBadge />}
                          </p>
                          <p className={`truncate text-sm ${unread ? "font-bold text-ink" : "text-slate-500"}`}>
                            {fromMe && <span className="text-slate-400">Vous : </span>}
                            {c.last_message.text}
                          </p>
                        </div>
                        <div className="flex shrink-0 flex-col items-end gap-1.5">
                          <span className={`text-[11px] font-semibold ${unread ? "text-primary" : "text-slate-400"}`}>
                            {formatRelativeShort(c.last_message.created_at)}
                          </span>
                          {unread && (
                            <span className="min-w-[20px] rounded-full bg-brand px-1.5 text-center text-[11px] font-bold leading-5 text-white">
                              {c.unread_count}
                            </span>
                          )}
                        </div>
                      </Link>
                    );
                  })}
                </div>
              </section>
            )}
          </>
        )}
      </main>

      <BottomNav />
    </div>
  );
}
