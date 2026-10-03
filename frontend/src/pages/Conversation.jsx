import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { apiClient, FOND } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { useConversationSocket } from "@/hooks/useConversationSocket";
import UserActionsMenu from "@/components/UserActionsMenu";
import ProfilePhoto from "@/components/ProfilePhoto";
import VerifiedBadge from "@/components/VerifiedBadge";
import { formatLastSeen } from "@/lib/format";
import TestBadge from "@/components/TestBadge";
import VoiceRecorder from "@/components/VoiceRecorder";
import MentionVersion from "@/components/MentionVersion";
import { bipNouveauMessage, noterBipConversation } from "@/lib/bipMessage";

// Emojis envoyables en un tap quand le champ est vide (brise-glace ludique).
const ICEBREAKERS = ["👋🏾", "😍", "😂", "🔥", "🙏🏾"];

/** "Aujourd'hui" / "Hier" / "lundi 3 mars" — séparateurs de jour. */
function dayLabel(iso) {
  const d = new Date(iso);
  const today = new Date();
  const yesterday = new Date();
  yesterday.setDate(today.getDate() - 1);
  if (d.toDateString() === today.toDateString()) return "Aujourd'hui";
  if (d.toDateString() === yesterday.toDateString()) return "Hier";
  return d.toLocaleDateString("fr-FR", { weekday: "long", day: "numeric", month: "long" });
}

// Message composé uniquement d'emojis (avec teintes de peau / jointures).
const EMOJI_ONLY_RE = /^(?:\p{Extended_Pictographic}|\p{Emoji_Modifier}|\u200d|\ufe0f)+$/u;

const timeOf = (iso) => new Date(iso).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });

/**
 * Conversation 1-à-1 en temps réel (fond blanc) : bulles en dégradé,
 * séparateurs de jour, "en train d'écrire…" animé, accusé "Vu", présence
 * ("Dans la conversation"), emojis brise-glace, repli REST si le
 * WebSocket est indisponible.
 */
export default function Conversation() {
  const { conversationId } = useParams();
  const { user } = useAuth();
  const [messages, setMessages] = useState([]);
  const [otherUser, setOtherUser] = useState(null);
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);
  const [notice, setNotice] = useState("");
  // Mes réglages (notes vocales / transcription) — voir /reglages
  const [mySettings, setMySettings] = useState({ voice_notes: true, voice_transcription: true });
  const bottomRef = useRef(null);

  const appendMessage = useCallback((message) => {
    setMessages((prev) => (prev.some((m) => m.id === message.id) ? prev : [...prev, message]));
  }, []);

  // L'autre personne a lu : tous MES messages non lus passent en "Vu".
  const applyRead = useCallback(
    ({ reader_id, read_at }) => {
      if (reader_id === user?.id) return;
      setMessages((prev) => prev.map((m) => (m.sender_id === user?.id && !m.read_at ? { ...m, read_at } : m)));
    },
    [user?.id],
  );

  // Message reçu en temps réel : bip s'il vient de l'autre personne (jamais pour
  // mes propres messages), selon mes préférences de son (voir lib/bipMessage.js)
  const recevoirMessage = useCallback((message) => {
    appendMessage(message);
    if (message.sender_id !== user?.id && bipNouveauMessage()) noterBipConversation();
  }, [appendMessage, user?.id]);

  const { connected, otherTyping, presentUserIds, sendMessage: sendOverSocket, notifyTyping, markRead } =
    useConversationSocket(conversationId, {
      onMessage: recevoirMessage,
      onRead: applyRead,
      onError: (detail) => {
        setNotice(detail);
        setTimeout(() => setNotice(""), 3000);
      },
    });

  const loadMessages = useCallback(
    () => apiClient.get(`/conversations/${conversationId}/messages`, FOND).then((r) => setMessages(r.data)),
    [conversationId],
  );

  useEffect(() => {
    loadMessages();
  }, [loadMessages]);

  // Filet de sécurité si le WebSocket n'est pas connecté (réseau restrictif,
  // reconnexion en cours…) : on retombe sur un polling classique.
  useEffect(() => {
    if (connected) return;
    const interval = setInterval(loadMessages, 4000);
    return () => clearInterval(interval);
  }, [connected, loadMessages]);

  useEffect(() => {
    apiClient.get("/me/settings").then((r) => setMySettings(r.data)).catch(() => {});
  }, []);

  // Envoi d'une note vocale (fichier audio + transcription éventuelle)
  const sendVoice = async ({ blob, duration, transcript }) => {
    setSending(true);
    try {
      const form = new FormData();
      const ext = blob.type.includes("mp4") ? "m4a" : blob.type.includes("ogg") ? "ogg" : "webm";
      form.append("file", blob, `note.${ext}`);
      form.append("duration", String(Math.min(duration, 180)));
      if (transcript) form.append("transcript", transcript);
      const res = await apiClient.post(`/conversations/${conversationId}/voice`, form, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      appendMessage(res.data);
    } catch (err) {
      setNotice(err?.response?.data?.detail || "Envoi de la note vocale impossible");
      setTimeout(() => setNotice(""), 4000);
    } finally {
      setSending(false);
    }
  };
  const canSendVoice = mySettings.voice_notes && otherUser?.accepts_voice_notes !== false;
  const [recordingVoice, setRecordingVoice] = useState(false);

  useEffect(() => {
    apiClient.get("/conversations").then((r) => {
      const conv = r.data.find((c) => c.conversation_id === conversationId);
      if (conv) setOtherUser(conv.other_user);
    });
  }, [conversationId]);

  // Accusé de lecture : dès qu'un message de l'autre est affiché et que
  // l'onglet est visible, on le marque "lu" (WebSocket, sinon REST).
  const hasUnreadFromOther = messages.some((m) => m.sender_id !== user?.id && !m.read_at);
  useEffect(() => {
    if (!hasUnreadFromOther || document.visibilityState !== "visible") return;
    if (!markRead()) apiClient.post(`/conversations/${conversationId}/read`).catch(() => {});
    // Marque localement pour ne pas renvoyer l'événement en boucle.
    const now = new Date().toISOString();
    setMessages((prev) => prev.map((m) => (m.sender_id !== user?.id && !m.read_at ? { ...m, read_at: now } : m)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasUnreadFromOther, connected]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, otherTyping]);

  const send = async (value) => {
    const body = (value ?? text).trim();
    if (!body || sending) return;
    setSending(true);
    try {
      if (!sendOverSocket(body)) {
        const res = await apiClient.post(`/conversations/${conversationId}/messages`, { text: body });
        appendMessage(res.data);
      }
      if (value === undefined) setText("");
    } finally {
      setSending(false);
    }
  };

  // Statut affiché sous le nom, du plus au moins "vivant".
  const otherInRoom = otherUser && presentUserIds.includes(otherUser.id);
  const status = !connected
    ? "Reconnexion…"
    : otherTyping
    ? "est en train d'écrire…"
    : otherInRoom
    ? "Dans la conversation"
    : otherUser?.is_online
    ? "En ligne"
    : formatLastSeen(otherUser?.last_seen_at);

  // Dernier de MES messages : c'est sous lui qu'on affiche "Vu" / "Envoyé".
  const lastMine = [...messages].reverse().find((m) => m.sender_id === user?.id);

  return (
    <div className="flex h-[100dvh] flex-col bg-white font-display text-ink">
      <header className="flex items-center gap-3 border-b border-slate-100 bg-white/90 px-3 py-3 backdrop-blur">
        <Link to="/messages" aria-label="Retour" className="flex h-10 w-10 items-center justify-center rounded-full text-slate-600 hover:bg-slate-50">
          <span className="material-symbols-outlined">arrow_back</span>
        </Link>
        {otherUser && (
          <Link to={`/profils/${otherUser.id}`} className="flex min-w-0 flex-1 items-center gap-3">
            <ProfilePhoto profile={otherUser} className="h-11 w-11 shrink-0 rounded-full" />
            <div className="min-w-0">
              <p className="flex items-center gap-1 truncate text-base font-extrabold">
                {otherUser.full_name}
                {otherUser.is_verified && <VerifiedBadge className="text-base" />}
                {otherUser.is_test_data && <TestBadge />}
              </p>
              <p className={`truncate text-xs font-semibold ${otherTyping || otherInRoom || otherUser.is_online ? "text-emerald-500" : "text-slate-400"}`}>
                {status}
              </p>
            </div>
          </Link>
        )}
        {otherUser && <UserActionsMenu targetUserId={otherUser.id} targetName={otherUser.full_name} />}
      </header>

      <main className="flex-1 overflow-y-auto bg-gradient-to-b from-white to-slate-50/60 px-4 py-4">
        {messages.length === 0 && otherUser && (
          <div className="mt-10 text-center">
            <ProfilePhoto profile={otherUser} className="mx-auto h-24 w-24 rounded-full ring-4 ring-primary/10" />
            <p className="mt-4 text-lg font-extrabold">Vous avez matché avec {otherUser.full_name.split(" ")[0]} 🎉</p>
            <p className="mt-1 text-sm text-slate-500">Brisez la glace : un simple emoji suffit.</p>
          </div>
        )}

        <div className="space-y-1.5">
          {messages.map((m, i) => {
            const mine = m.sender_id === user?.id;
            const prev = messages[i - 1];
            const newDay = !prev || new Date(prev.created_at).toDateString() !== new Date(m.created_at).toDateString();
            // Emoji seul -> affiché en grand, sans bulle (comme les messageries modernes).
            const emojiOnly = m.kind !== "voice" && EMOJI_ONLY_RE.test(m.text) && m.text.length <= 8;
            return (
              <div key={m.id}>
                {newDay && (
                  <p className="my-4 text-center text-[11px] font-bold uppercase tracking-wider text-slate-400">{dayLabel(m.created_at)}</p>
                )}
                <div className={`flex ${mine ? "justify-end" : "justify-start"}`}>
                  {m.kind === "voice" ? (
                    // Note vocale : lecteur audio + transcription (si activée dans mes réglages)
                    <div
                      className={`max-w-[80%] rounded-[1.4rem] px-3 py-2 shadow-sm ${
                        mine ? "rounded-br-md bg-gradient-to-br from-primary to-sunset text-white" : "rounded-bl-md bg-slate-100 text-ink"
                      }`}
                    >
                      <audio controls preload="metadata" src={m.audio_url} className="h-10 w-60 max-w-full" />
                      {mySettings.voice_transcription && m.transcript && (
                        <p className={`mt-1 whitespace-pre-wrap text-[13px] italic ${mine ? "text-white/90" : "text-slate-600"}`}>« {m.transcript} »</p>
                      )}
                      <span className={`mt-0.5 block text-right text-[10px] ${mine ? "text-white/70" : "text-slate-400"}`}>
                        🎤 {Math.round(m.audio_duration || 0)} s · {timeOf(m.created_at)}
                      </span>
                    </div>
                  ) : emojiOnly ? (
                    <span className="animate-pop text-5xl" title={timeOf(m.created_at)}>{m.text}</span>
                  ) : (
                    <div
                      title={timeOf(m.created_at)}
                      className={`max-w-[78%] whitespace-pre-wrap break-words px-4 py-2.5 text-[15px] leading-snug shadow-sm ${
                        mine
                          ? "rounded-[1.4rem] rounded-br-md bg-gradient-to-br from-primary to-sunset text-white"
                          : "rounded-[1.4rem] rounded-bl-md bg-slate-100 text-ink"
                      }`}
                    >
                      {m.text}
                      <span className={`ml-2 align-bottom text-[10px] ${mine ? "text-white/70" : "text-slate-400"}`}>{timeOf(m.created_at)}</span>
                    </div>
                  )}
                </div>
                {lastMine && m.id === lastMine.id && (
                  <p className="mt-1 text-right text-[11px] font-semibold text-slate-400">
                    {m.read_at ? (
                      <span className="text-primary">Vu</span>
                    ) : (
                      "Envoyé"
                    )}
                  </p>
                )}
              </div>
            );
          })}

          {/* "En train d'écrire…" : trois points qui sautillent */}
          {otherTyping && (
            <div className="flex justify-start">
              <div className="flex items-center gap-1 rounded-[1.4rem] rounded-bl-md bg-slate-100 px-4 py-3.5">
                {[0, 1, 2].map((d) => (
                  <span key={d} className="h-2 w-2 animate-typing-dot rounded-full bg-slate-400" style={{ animationDelay: `${d * 0.15}s` }} />
                ))}
              </div>
            </div>
          )}
        </div>
        <div ref={bottomRef} />
      </main>

      {notice && <p className="bg-amber-50 px-4 py-2 text-center text-xs font-semibold text-amber-700">{notice}</p>}

      <div className="pb-safe border-t border-slate-100 bg-white px-3 pt-2">
        {!text && (
          <div className="no-scrollbar mb-2 flex gap-2 overflow-x-auto">
            {ICEBREAKERS.map((e) => (
              <button key={e} onClick={() => send(e)} className="h-10 shrink-0 rounded-full bg-slate-50 px-3 text-xl transition active:scale-90">
                {e}
              </button>
            ))}
          </div>
        )}
        <form
          onSubmit={(e) => {
            e.preventDefault();
            send();
          }}
          className="flex items-center gap-2 pb-1"
        >
          {!recordingVoice && (
            <input
              value={text}
              onChange={(e) => {
                setText(e.target.value);
                if (e.target.value) notifyTyping();
              }}
              maxLength={2000}
              placeholder="Votre message…"
              className="h-12 flex-1 rounded-full bg-slate-100 px-5 text-[15px] outline-none focus:ring-2 focus:ring-primary/30"
            />
          )}
          {/* Champ vide : micro (note vocale) ; sinon bouton Envoyer */}
          {!text.trim() && canSendVoice ? (
            <VoiceRecorder
              transcribe={mySettings.voice_transcription}
              onSend={sendVoice}
              onError={(msg) => {
                setNotice(msg);
                setTimeout(() => setNotice(""), 4000);
              }}
              onRecordingChange={setRecordingVoice}
              disabled={sending}
            />
          ) : (
            <button
              type="submit"
              disabled={sending || !text.trim()}
              aria-label="Envoyer"
              className="flex h-12 w-12 items-center justify-center rounded-full bg-brand text-white shadow-lg shadow-primary/30 transition active:scale-90 disabled:opacity-40 disabled:shadow-none"
            >
              <span className="material-symbols-outlined">send</span>
            </button>
          )}
        </form>
        {/* Version et lot du déploiement en cours (règle permanente) — sous la zone de saisie */}
        <MentionVersion className="pt-1 text-[9px] leading-tight" />
      </div>
    </div>
  );
}
