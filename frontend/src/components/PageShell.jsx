import { Link } from "react-router-dom";
import BottomNav from "@/components/BottomNav";

/**
 * Gabarit des pages simples (fond blanc) : en-tête avec retour + titre,
 * contenu centré, barre de navigation en bas.
 */
export default function PageShell({ title, subtitle, back = "/profil", children }) {
  return (
    <div className="flex min-h-[100dvh] flex-col bg-white font-display text-ink">
      <header className="flex items-center gap-3 px-4 pb-2 pt-5">
        <Link to={back} aria-label="Retour" className="flex h-10 w-10 items-center justify-center rounded-full hover:bg-slate-50">
          <span className="material-symbols-outlined">arrow_back</span>
        </Link>
        <div className="min-w-0">
          <h1 className="truncate text-xl font-extrabold">{title}</h1>
          {subtitle && <p className="truncate text-xs text-slate-500">{subtitle}</p>}
        </div>
      </header>
      <main className="mx-auto w-full max-w-lg flex-1 px-4 pb-8">{children}</main>
      <BottomNav />
    </div>
  );
}
