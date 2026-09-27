import { useEffect } from "react";

// Tiroir BLANC qui monte du bas de l'écran (commentaires, options, filtres)
// — le geste le plus naturel au pouce sur mobile, emprunté à TikTok.
// Fermeture : clic sur le fond assombri, bouton ✕ ou touche Échap.
export default function BottomSheet({ title, onClose, children, heightClass = "max-h-[75dvh]" }) {
  // Échap ferme le tiroir (confort clavier sur ordinateur).
  useEffect(() => {
    const onKey = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-50 flex animate-fade-in items-end justify-center bg-black/40"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div className={`flex w-full max-w-lg animate-slide-up flex-col rounded-t-[1.75rem] bg-white shadow-2xl ${heightClass}`}>
        {/* Poignée + titre */}
        <div className="relative flex flex-col items-center px-5 pb-2 pt-3">
          <span className="h-1.5 w-10 rounded-full bg-slate-200" />
          {title && <p className="mt-3 text-sm font-extrabold text-ink">{title}</p>}
          <button
            onClick={onClose}
            aria-label="Fermer"
            className="absolute right-4 top-3 flex h-8 w-8 items-center justify-center rounded-full bg-slate-100 text-slate-500"
          >
            <span className="material-symbols-outlined text-lg">close</span>
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto">{children}</div>
      </div>
    </div>
  );
}
