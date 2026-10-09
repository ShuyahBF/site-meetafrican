import { useState } from "react";
import { Link, useLocation } from "react-router-dom";
import CreateSheet from "@/components/CreateSheet";
import { useUnreadCount } from "@/hooks/useUnreadCount";
import MentionVersion from "@/components/MentionVersion";
import SupportSawali from "@/components/SupportSawali";

// Barre de navigation du bas, façon TikTok : 4 onglets + un gros bouton
// central (un cauri sur fond blanc, à la place du ✚) pour publier une vidéo. Fond blanc, pastille rouge de
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
      {/* Bouton central "Publier" : cauri sur fond blanc. */}
      <button onClick={() => setCreateOpen(true)} aria-label="Créer et autres actions" className="relative mx-1 h-9 w-12 active:scale-95">
        {/* Fond du bouton entièrement blanc (demande du propriétaire), avec un fin
            contour gris pour qu'il reste visible sur la barre blanche */}
        <span className="absolute inset-0 flex items-center justify-center rounded-xl bg-white ring-1 ring-slate-200 shadow-sm">
          {/* Cauri à la place du « + » : dessin détouré, traits noirs sur fond transparent */}
          <img src="/images/cauri-noir.png" alt="" aria-hidden="true" className="h-auto w-9 select-none" draggable="false" />
        </span>
      </button>
      {RIGHT.map(renderItem)}
      {/* Version et lot du déploiement en cours (règle permanente), en tout
          petit sous les onglets, sur toute la largeur */}
      {/* Ligne du bas : mention de version centrée + pictogramme « Assistance SAWALI »
          (support technique de la plateforme, SAWALI lot 90) discret à droite.
          Caché si le membre n'est pas connecté ou si SAWALI n'est pas relié. */}
      <div className="relative w-full basis-full">
        <MentionVersion className="w-full pb-1 pt-0.5 text-[9px] leading-tight" />
        <SupportSawali className="absolute bottom-0.5 right-2" />
      </div>
      {createOpen && <CreateSheet onClose={() => setCreateOpen(false)} />}
    </nav>
  );
}
