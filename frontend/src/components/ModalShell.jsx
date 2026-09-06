// Conteneur modal générique (fond assombri, fermeture au clic extérieur) —
// partagé par les actions de carte profil (points, cadeaux...).
export default function ModalShell({ children, onClose }) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div className="w-full max-w-sm rounded-xl bg-white p-5 shadow-2xl dark:bg-background-dark dark:ring-1 dark:ring-white/10">
        {children}
        <button onClick={onClose} className="mt-3 w-full text-center text-sm text-slate-400">
          Fermer
        </button>
      </div>
    </div>
  );
}
