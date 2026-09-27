import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { apiClient, extractErrorMessage } from "@/lib/api";
import BottomSheet from "@/components/BottomSheet";
import VerifiedBadge from "@/components/VerifiedBadge";
import { formatRelativeShort } from "@/lib/format";

// Réactions rapides en un tap au-dessus du champ de saisie (comme les
// emojis suggérés de TikTok) — publier devient un geste, pas une corvée.
const QUICK_REACTIONS = ["🔥", "😍", "👏🏾", "😂", "💯", "🙌🏾"];

// Tiroir blanc des commentaires d'une vidéo. `onCountChange(delta)` permet
// au fil de mettre à jour le compteur de la vidéo sans recharger.
export default function CommentsSheet({ video, onClose, onCountChange }) {
  const [comments, setComments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    apiClient
      .get(`/videos/${video.id}/comments`)
      .then((r) => setComments(r.data))
      .finally(() => setLoading(false));
  }, [video.id]);

  const send = async (value) => {
    const body = (value ?? text).trim();
    if (!body || sending) return;
    setSending(true);
    setError("");
    try {
      const res = await apiClient.post(`/videos/${video.id}/comments`, { text: body });
      setComments((prev) => [res.data, ...prev]);
      setText("");
      onCountChange?.(1);
    } catch (err) {
      setError(extractErrorMessage(err, "Commentaire non envoyé"));
    } finally {
      setSending(false);
    }
  };

  const remove = async (commentId) => {
    await apiClient.delete(`/videos/${video.id}/comments/${commentId}`);
    setComments((prev) => prev.filter((c) => c.id !== commentId));
    onCountChange?.(-1);
  };

  // Peut supprimer : l'auteur du commentaire ou l'auteur de la vidéo.
  const canDelete = (c) => c.is_mine || video.is_mine;

  return (
    <BottomSheet title={`${comments.length} commentaire${comments.length > 1 ? "s" : ""}`} onClose={onClose}>
      <div className="flex h-[55dvh] flex-col">
        <div className="flex-1 space-y-4 overflow-y-auto px-5 py-2">
          {loading ? (
            <p className="py-10 text-center text-sm text-slate-400">Chargement…</p>
          ) : comments.length === 0 ? (
            <div className="py-10 text-center">
              <p className="text-3xl">💬</p>
              <p className="mt-2 text-sm font-bold text-ink">Soyez le premier à commenter</p>
              <p className="text-xs text-slate-400">Un petit mot fait toujours plaisir.</p>
            </div>
          ) : (
            comments.map((c) => (
              <div key={c.id} className="flex gap-3">
                <Link to={`/profils/${c.author.id}`} className="h-9 w-9 shrink-0 overflow-hidden rounded-full bg-slate-100">
                  {c.author.avatar_url ? (
                    <img src={c.author.avatar_url} alt="" className="h-full w-full object-cover" />
                  ) : (
                    <span className="flex h-full w-full items-center justify-center bg-brand text-sm font-bold text-white">
                      {c.author.full_name?.[0]}
                    </span>
                  )}
                </Link>
                <div className="min-w-0 flex-1">
                  <p className="text-xs font-bold text-slate-500">
                    {c.author.full_name} {c.author.is_verified && <VerifiedBadge className="text-xs" />}
                    {c.author.id === video.user_id && (
                      <span className="ml-1 rounded bg-primary/10 px-1.5 py-0.5 text-[10px] font-extrabold text-primary">Auteur</span>
                    )}
                  </p>
                  <p className="break-words text-sm text-ink">{c.text}</p>
                  <p className="mt-0.5 text-[11px] text-slate-400">
                    {formatRelativeShort(c.created_at)}
                    {canDelete(c) && (
                      <button onClick={() => remove(c.id)} className="ml-3 font-semibold hover:text-red-500">
                        Supprimer
                      </button>
                    )}
                  </p>
                </div>
              </div>
            ))
          )}
        </div>

        <div className="border-t border-slate-100 px-4 pb-4 pt-2">
          <div className="no-scrollbar mb-2 flex gap-2 overflow-x-auto">
            {QUICK_REACTIONS.map((emoji) => (
              <button
                key={emoji}
                onClick={() => send(emoji)}
                disabled={sending}
                className="h-9 shrink-0 rounded-full bg-slate-50 px-3 text-lg transition active:scale-90"
              >
                {emoji}
              </button>
            ))}
          </div>
          {error && <p className="mb-1 text-xs text-red-500">{error}</p>}
          <form
            onSubmit={(e) => {
              e.preventDefault();
              send();
            }}
            className="flex items-center gap-2"
          >
            <input
              value={text}
              onChange={(e) => setText(e.target.value)}
              maxLength={500}
              placeholder="Ajouter un commentaire…"
              className="h-11 flex-1 rounded-full bg-slate-100 px-4 text-sm text-ink outline-none focus:ring-2 focus:ring-primary/30"
            />
            <button
              type="submit"
              disabled={sending || !text.trim()}
              aria-label="Envoyer"
              className="flex h-11 w-11 items-center justify-center rounded-full bg-brand text-white disabled:opacity-40"
            >
              <span className="material-symbols-outlined text-xl">arrow_upward</span>
            </button>
          </form>
        </div>
      </div>
    </BottomSheet>
  );
}
