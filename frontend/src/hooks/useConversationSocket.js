import { useEffect, useRef, useState } from "react";
import { WS_BASE_URL } from "@/lib/api";

const RECONNECT_DELAY_MS = 2000;
// Durée d'affichage de "en train d'écrire…" après le dernier signal reçu.
const TYPING_VISIBLE_MS = 3500;
// Pas plus d'un signal "je tape" toutes les 2 s (inutile d'inonder le serveur).
const TYPING_THROTTLE_MS = 2000;

/**
 * Connexion WebSocket temps réel à une conversation (protocole décrit dans
 * backend/routes/chat.py). Fournit :
 *   - connected       : état de la connexion (repli REST si false) ;
 *   - otherTyping     : l'autre personne est en train d'écrire ;
 *   - presentUserIds  : qui a la conversation ouverte en ce moment ;
 *   - sendMessage(text), notifyTyping(), markRead().
 * `handlers.onMessage(message)` et `handlers.onRead({reader_id, read_at})`
 * sont appelés à chaque événement. Reconnexion automatique.
 */
export function useConversationSocket(conversationId, handlers) {
  const [connected, setConnected] = useState(false);
  const [otherTyping, setOtherTyping] = useState(false);
  const [presentUserIds, setPresentUserIds] = useState([]);
  const socketRef = useRef(null);
  const handlersRef = useRef(handlers);
  handlersRef.current = handlers;
  const typingTimer = useRef(null);
  const lastTypingSent = useRef(0);

  useEffect(() => {
    if (!conversationId) return;
    let cancelled = false;
    let reconnectTimer = null;

    const connect = () => {
      const token = localStorage.getItem("maf_token");
      if (!token) return;
      const ws = new WebSocket(`${WS_BASE_URL}/ws/conversations/${conversationId}?token=${token}`);
      socketRef.current = ws;

      ws.onopen = () => !cancelled && setConnected(true);
      ws.onclose = () => {
        if (cancelled) return;
        setConnected(false);
        reconnectTimer = setTimeout(connect, RECONNECT_DELAY_MS);
      };
      ws.onerror = () => ws.close();
      ws.onmessage = (event) => {
        let payload;
        try {
          payload = JSON.parse(event.data);
        } catch {
          return; // message non exploitable, ignoré
        }
        switch (payload.type) {
          case "message":
            // Un message reçu met fin à l'indicateur "en train d'écrire".
            setOtherTyping(false);
            handlersRef.current?.onMessage?.(payload.data);
            break;
          case "typing":
            setOtherTyping(true);
            clearTimeout(typingTimer.current);
            typingTimer.current = setTimeout(() => setOtherTyping(false), TYPING_VISIBLE_MS);
            break;
          case "read":
            handlersRef.current?.onRead?.(payload.data);
            break;
          case "presence":
            setPresentUserIds(payload.data.user_ids || []);
            break;
          case "error":
            handlersRef.current?.onError?.(payload.data.detail);
            break;
          default:
            break;
        }
      };
    };

    connect();
    return () => {
      cancelled = true;
      clearTimeout(reconnectTimer);
      clearTimeout(typingTimer.current);
      socketRef.current?.close();
      socketRef.current = null;
    };
  }, [conversationId]);

  // Envoie un événement si la connexion est ouverte ; false sinon.
  const send = (payload) => {
    const ws = socketRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(payload));
      return true;
    }
    return false;
  };

  const sendMessage = (text) => send({ type: "message", text });
  const markRead = () => send({ type: "read" });
  const notifyTyping = () => {
    const now = Date.now();
    if (now - lastTypingSent.current < TYPING_THROTTLE_MS) return;
    lastTypingSent.current = now;
    send({ type: "typing" });
  };

  return { connected, otherTyping, presentUserIds, sendMessage, notifyTyping, markRead };
}
