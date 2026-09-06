import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { apiClient } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { useConversationSocket } from "@/hooks/useConversationSocket";
import UserActionsMenu from "@/components/UserActionsMenu";
import ProfilePhoto from "@/components/ProfilePhoto";
import { formatLastSeen } from "@/lib/format";

export default function Conversation() {
  const { conversationId } = useParams();
  const { user } = useAuth();
  const [messages, setMessages] = useState([]);
  const [otherUser, setOtherUser] = useState(null);
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);
  const bottomRef = useRef(null);

  const appendMessage = (message) => {
    setMessages((prev) => (prev.some((m) => m.id === message.id) ? prev : [...prev, message]));
  };

  const { connected, sendMessage: sendOverSocket } = useConversationSocket(conversationId, appendMessage);

  useEffect(() => {
    apiClient.get(`/conversations/${conversationId}/messages`).then((r) => setMessages(r.data));
  }, [conversationId]);

  // Filet de sécurité si le WebSocket n'est pas connecté (réseau restrictif,
  // reconnexion en cours…) : on retombe sur un polling classique.
  useEffect(() => {
    if (connected) return;
    const interval = setInterval(() => {
      apiClient.get(`/conversations/${conversationId}/messages`).then((r) => setMessages(r.data));
    }, 4000);
    return () => clearInterval(interval);
  }, [conversationId, connected]);

  useEffect(() => {
    apiClient.get("/conversations").then((r) => {
      const conv = r.data.find((c) => c.conversation_id === conversationId);
      if (conv) setOtherUser(conv.other_user);
    });
  }, [conversationId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const send = async (e) => {
    e.preventDefault();
    const value = text.trim();
    if (!value || sending) return;
    setSending(true);
    try {
      if (!sendOverSocket(value)) {
        const res = await apiClient.post(`/conversations/${conversationId}/messages`, { text: value });
        appendMessage(res.data);
      }
      setText("");
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="flex min-h-screen flex-col bg-background-light font-display dark:bg-background-dark">
      <header className="flex items-center gap-3 border-b border-slate-800/10 px-4 py-4 dark:border-white/10">
        <Link to="/messages" className="text-slate-500 dark:text-slate-400">
          <span className="material-symbols-outlined">arrow_back</span>
        </Link>
        {otherUser && <ProfilePhoto profile={otherUser} showOnlineDot className="h-10 w-10 shrink-0 rounded-full" />}
        <div className="flex-1 truncate">
          <h1 className="truncate text-lg font-bold text-slate-900 dark:text-white">
            {otherUser?.full_name || "Conversation"}
          </h1>
          <p className="text-xs text-slate-500 dark:text-slate-400">
            {!connected
              ? "Reconnexion…"
              : otherUser?.is_online
              ? "En ligne"
              : formatLastSeen(otherUser?.last_seen_at)}
          </p>
        </div>
        {otherUser && <UserActionsMenu targetUserId={otherUser.id} targetName={otherUser.full_name} />}
      </header>

      <main className="flex-1 space-y-2 overflow-y-auto px-4 py-4">
        {messages.map((m) => {
          const mine = m.sender_id === user?.id;
          return (
            <div key={m.id} className={`flex ${mine ? "justify-end" : "justify-start"}`}>
              <div
                className={`max-w-[75%] rounded-2xl px-4 py-2 text-sm ${
                  mine ? "bg-primary text-white" : "bg-slate-800/10 text-slate-900 dark:bg-white/10 dark:text-white"
                }`}
              >
                {m.text}
              </div>
            </div>
          );
        })}
        <div ref={bottomRef} />
      </main>

      <form onSubmit={send} className="flex items-center gap-2 border-t border-slate-800/10 p-3 dark:border-white/10">
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Votre message…"
          className="input flex-1"
        />
        <button
          type="submit"
          disabled={sending || !text.trim()}
          className="flex h-11 w-11 items-center justify-center rounded-full bg-primary text-white disabled:opacity-50"
        >
          <span className="material-symbols-outlined">send</span>
        </button>
      </form>
    </div>
  );
}
