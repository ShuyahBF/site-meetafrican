import { useState } from "react";
import { Link, useLocation } from "react-router-dom";
import CreateSheet from "@/components/CreateSheet";
import { useUnreadCount } from "@/hooks/useUnreadCount";
import MentionVersion from "@/components/MentionVersion";

// Barre de navigation du bas, façon TikTok : 4 onglets + un gros bouton ✚
// central en dégradé pour publier une vidéo. Fond blanc, pastille rouge de
// messages non lus.
const LEFT = [
  { to: "/moments", icon: "play_circle", label: "Moments" },
  { to: "/decouverte", icon: "local_fire_department", label: "Découvrir" },
];
const RIGHT = [
  { to: "/messages", icon: "chat_bubble", label: "Messages", badge: true },
  { to: "/profil", icon: "person", label: "Profil" },
];

export default function BottomNav() {
  const { pathname } = useLocation();
  const unread = useUnreadCount();
  // Le bouton ✚ ouvre le tiroir des actions (publier, me suivre, support…)
  const [createOpen, setCreateOpen] = useState(false);

  const renderItem = (item) => {
    const active = pathname.startsWith(item.to);
    return (
      <Link
        key={item.to}
        to={item.to}
        className={`relative flex w-16 flex-col items-center gap-0.5 text-[11px] font-semibold transition ${
          active ? "text-ink" : "text-slate-400"
        }`}
      >
        <span className={`material-symbols-outlined text-[26px] ${active ? "icon-filled" : ""}`}>{item.icon}</span>
        {item.label}
        {item.badge && unread > 0 && (
          <span className="absolute -top-1 right-2 min-w-[18px] rounded-full bg-primary px-1 text-center text-[10px] font-bold leading-[18px] text-white ring-2 ring-white">
            {unread > 99 ? "99+" : unread}
          </span>
        )}
      </Link>
    );
  };

  return (
    // flex-wrap : la mention de version passe sur sa propre ligne, sous les onglets
    <nav className="pb-safe sticky bottom-0 z-40 flex flex-wrap items-center justify-around border-t border-slate-100 bg-white pt-2">
      {LEFT.map(renderItem)}
      {/* Bouton ✚ "Publier" : double pastille décalée rose/orange (clin
          d'œil au bouton de création TikTok). */}
      <button onClick={() => setCreateOpen(true)} aria-label="Créer et autres actions" className="relative mx-1 h-9 w-12 active:scale-95">
        <span className="absolute inset-y-0 left-0 w-10 rounded-xl bg-sunset" />
        <span className="absolute inset-y-0 right-0 w-10 rounded-xl bg-primary" />
        <span className="absolute inset-y-0 left-1 right-1 flex items-center justify-center rounded-xl bg-ink text-white">
          <span className="material-symbols-outlined text-xl">add</span>
        </span>
      </button>
      {RIGHT.map(renderItem)}
      {/* Version et lot du déploiement en cours (règle permanente), en tout
          petit sous les onglets, sur toute la largeur */}
      <MentionVersion className="w-full basis-full pb-1 pt-0.5 text-[9px] leading-tight" />
      {createOpen && <CreateSheet onClose={() => setCreateOpen(false)} />}
    </nav>
  );
}
