import { useAuth } from "@/context/AuthContext";
import { Link } from "react-router-dom";

export default function Discover() {
  const { user, logout } = useAuth();

  return (
    <div className="dark flex min-h-screen flex-col bg-background-light font-display dark:bg-background-dark">
      <header className="flex items-center justify-between px-4 py-4">
        <h1 className="text-xl font-bold text-slate-900 dark:text-white">Découvrir</h1>
        <button onClick={logout} className="text-sm text-slate-500 dark:text-slate-400">Déconnexion</button>
      </header>

      <main className="flex flex-1 flex-col items-center justify-center gap-3 px-6 text-center">
        <span className="material-symbols-outlined text-5xl text-primary">favorite</span>
        <p className="text-lg font-bold text-slate-900 dark:text-white">
          Bienvenue {user?.full_name} 👋
        </p>
        <p className="max-w-xs text-sm text-slate-500 dark:text-slate-400">
          Le fil de découverte / matching arrive dans une prochaine itération.
        </p>
        <Link to="/abonnement" className="mt-2 rounded-full bg-primary px-5 py-3 text-sm font-bold text-white">
          Voir les formules Premium
        </Link>
      </main>

      <nav className="sticky bottom-0 flex items-center justify-around border-t border-slate-800/10 bg-background-light py-3 dark:border-white/10 dark:bg-background-dark">
        <NavItem icon="favorite" label="Découvrir" active />
        <NavItem icon="local_fire_department" label="Matchs" />
        <NavItem icon="chat_bubble" label="Messages" />
        <NavItem icon="person" label="Profil" />
      </nav>
    </div>
  );
}

function NavItem({ icon, label, active }) {
  return (
    <div className={`flex flex-col items-center gap-1 text-xs ${active ? "text-primary" : "text-slate-500 dark:text-slate-400"}`}>
      <span className="material-symbols-outlined">{icon}</span>
      {label}
    </div>
  );
}
