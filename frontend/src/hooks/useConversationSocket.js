import { useEffect, useRef, useState } from "react";
import { WS_BASE_URL } from "@/lib/api";

const RECONNECT_DELAY_MS = 2000;

/**
 * Connexion WebSocket temps réel à une conversation. Appelle `onMessage`
 * pour chaque nouveau message reçu (envoyé par soi ou par l'autre personne
 * — le serveur diffuse aux deux participants). Se reconnecte automatiquement
 * si la connexion tombe. `connected` reflète l'état courant, pour basculer
 * sur l'envoi REST en repli si le WebSocket n'est pas disponible.
 */
export function useConversationSocket(conversationId, onMessage) {
  const [connected, setConnected] = useState(false);
  const socketRef = useRef(null);
  const onMessageRef = useRef(onMessage);
  onMessageRef.current = onMessage;

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
        try {
          const payload = JSON.parse(event.data);
          if (payload.type === "message") onMessageRef.current?.(payload.data);
        } catch {
          // message non exploitable, ignoré
        }
      };
    };

    connect();
    return () => {
      cancelled = true;
      clearTimeout(reconnectTimer);
      socketRef.current?.close();
      socketRef.current = null;
    };
  }, [conversationId]);

  const sendMessage = (text) => {
    const ws = socketRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ text }));
      return true;
    }
    return false;
  };

  return { connected, sendMessage };
}
