import { Link, useLocation } from "react-router-dom";

const ITEMS = [
  { to: "/decouverte", icon: "favorite", label: "Découvrir" },
  { to: "/matchs", icon: "local_fire_department", label: "Matchs" },
  { to: "/messages", icon: "chat_bubble", label: "Messages" },
  { to: "/profil", icon: "person", label: "Profil" },
];

export default function BottomNav() {
  const { pathname } = useLocation();
  return (
    <nav className="sticky bottom-0 flex items-center justify-around border-t border-slate-800/10 bg-background-light py-3 dark:border-white/10 dark:bg-background-dark">
      {ITEMS.map((item) => {
        const active = pathname.startsWith(item.to);
        return (
          <Link
            key={item.to}
            to={item.to}
            className={`flex flex-col items-center gap-1 text-xs ${active ? "text-primary" : "text-slate-500 dark:text-slate-400"}`}
          >
            <span className="material-symbols-outlined">{item.icon}</span>
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}
