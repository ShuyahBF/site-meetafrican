"""Hub WebSocket partagé par le chat privé (conversations 1-à-1) et les
salons de discussion publics.

Chaque connexion est rattachée à un "canal" (ex. "conv:<id>" ou
"room:<slug>") et à l'utilisateur authentifié qui l'a ouverte — ce qui
permet, en plus de diffuser les messages, de savoir QUI est présent dans un
canal (liste des connectés d'un salon, "en ligne dans la conversation").

Registre en mémoire : suffisant pour un seul process backend (cas actuel,
cf. render.yaml). Si le service est un jour déployé sur plusieurs instances,
remplacer par un pub/sub partagé (Redis, etc.) pour que les diffusions
traversent les process.
"""
from __future__ import annotations

import time
from collections import deque
from typing import Deque, Dict, Iterable, List, Optional, Set, Tuple

from fastapi import WebSocket


class ChannelHub:
    def __init__(self) -> None:
        # canal -> {websocket: user_id}
        self._channels: Dict[str, Dict[WebSocket, str]] = {}

    async def connect(self, channel: str, ws: WebSocket, user_id: str) -> None:
        """Accepte la connexion et l'enregistre dans le canal."""
        await ws.accept()
        self._channels.setdefault(channel, {})[ws] = user_id

    def disconnect(self, channel: str, ws: WebSocket) -> None:
        """Retire la connexion ; supprime le canal s'il devient vide."""
        conns = self._channels.get(channel)
        if conns is not None:
            conns.pop(ws, None)
            if not conns:
                self._channels.pop(channel, None)

    def user_ids(self, channel: str) -> Set[str]:
        """Utilisateurs distincts connectés au canal (un même utilisateur
        peut avoir plusieurs onglets ouverts : il n'est compté qu'une fois)."""
        return set(self._channels.get(channel, {}).values())

    def is_connected(self, channel: str, user_id: str) -> bool:
        return user_id in self.user_ids(channel)

    async def send(
        self,
        channel: str,
        event_type: str,
        data: dict,
        exclude_user: Optional[str] = None,
    ) -> None:
        """Diffuse {type, data} à toutes les connexions du canal, sauf
        (optionnellement) celles d'un utilisateur donné — utile pour
        l'indicateur "en train d'écrire", inutile à renvoyer à son auteur.
        Une connexion morte est simplement retirée du registre."""
        payload = {"type": event_type, "data": data}
        for ws, uid in list(self._channels.get(channel, {}).items()):
            if exclude_user and uid == exclude_user:
                continue
            try:
                await ws.send_json(payload)
            except Exception:  # noqa: BLE001
                self.disconnect(channel, ws)

    async def close_user(self, channel: str, user_id: str, code: int = 4403) -> None:
        """Ferme de force toutes les connexions d'un utilisateur dans un canal
        (ex. utilisateur rendu muet/exclu d'un salon par un modérateur)."""
        for ws, uid in list(self._channels.get(channel, {}).items()):
            if uid == user_id:
                self.disconnect(channel, ws)
                try:
                    await ws.close(code=code)
                except Exception:  # noqa: BLE001
                    pass

    def channels_with_prefix(self, prefix: str) -> Iterable[Tuple[str, int]]:
        """(canal, nombre d'utilisateurs distincts) pour chaque canal actif
        commençant par `prefix` — alimente les compteurs "X en ligne" de la
        liste des salons."""
        for channel, conns in self._channels.items():
            if channel.startswith(prefix):
                yield channel, len(set(conns.values()))


class RateLimiter:
    """Anti-flood simple par utilisateur : au plus `max_events` sur une
    fenêtre glissante de `window_seconds`. En mémoire, même limite que le
    hub (un seul process)."""

    def __init__(self, max_events: int, window_seconds: float) -> None:
        self.max_events = max_events
        self.window_seconds = window_seconds
        self._events: Dict[str, Deque[float]] = {}

    def allow(self, key: str) -> bool:
        """True si l'événement est autorisé (et le comptabilise), False si la
        limite est atteinte."""
        now = time.monotonic()
        events = self._events.setdefault(key, deque())
        # Purge des événements sortis de la fenêtre glissante.
        while events and now - events[0] > self.window_seconds:
            events.popleft()
        if len(events) >= self.max_events:
            return False
        events.append(now)
        return True


hub = ChannelHub()


def conversation_channel(conversation_id: str) -> str:
    return f"conv:{conversation_id}"


def room_channel(slug: str) -> str:
    return f"room:{slug}"


def online_counts_by_room() -> Dict[str, int]:
    """{slug: nombre de connectés} pour tous les salons actifs."""
    prefix = "room:"
    return {channel[len(prefix):]: count for channel, count in hub.channels_with_prefix(prefix)}


__all__: List[str] = [
    "ChannelHub", "RateLimiter", "hub", "conversation_channel", "room_channel", "online_counts_by_room",
]
