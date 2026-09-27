import { Link } from "react-router-dom";
import ProfilePhoto from "@/components/ProfilePhoto";
import { useAuth } from "@/context/AuthContext";

// Couleurs des confettis (dégradé de la marque + touches vives).
const CONFETTI_COLORS = ["#f4256a", "#ff7a45", "#8b5cf6", "#facc15", "#10b981"];

// Confettis générés une seule fois (positions/délais pseudo-aléatoires
// mais stables : pas de Math.random() au rendu).
const CONFETTI = Array.from({ length: 36 }, (_, i) => ({
  left: (i * 37) % 100,
  delay: ((i * 13) % 20) / 10,
  color: CONFETTI_COLORS[i % CONFETTI_COLORS.length],
  size: 6 + (i % 4) * 2,
}));

// Écran de fête "C'est un match !" — carte BLANCHE, deux photos qui se
// chevauchent, confettis. Partagé par la découverte, le fil vidéo et les
// fiches profil.
export default function MatchCelebration({ otherUser, conversationId, onClose }) {
  const { user } = useAuth();
  return (
    <div className="fixed inset-0 z-[60] flex animate-fade-in items-center justify-center overflow-hidden bg-black/50 p-6">
      {CONFETTI.map((c, i) => (
        <span
          key={i}
          className="pointer-events-none absolute top-0 animate-confetti rounded-sm"
          style={{ left: `${c.left}%`, width: c.size, height: c.size * 1.6, background: c.color, animationDelay: `${c.delay}s` }}
        />
      ))}

      <div className="relative w-full max-w-sm rounded-[2rem] bg-white p-7 text-center shadow-2xl">
        <div className="flex justify-center">
          <div className="-rotate-6 rounded-3xl bg-white p-1 shadow-lg">
            {user && <ProfilePhoto profile={user} className="h-28 w-24 rounded-[1.25rem]" />}
          </div>
          <div className="-ml-5 mt-4 rotate-6 rounded-3xl bg-white p-1 shadow-lg">
            <ProfilePhoto profile={otherUser} className="h-28 w-24 rounded-[1.25rem]" />
          </div>
        </div>
        <span className="material-symbols-outlined icon-filled mt-3 animate-pop text-4xl text-primary">favorite</span>
        <h2 className="text-3xl font-extrabold text-brand">C'est un match !</h2>
        <p className="mt-2 text-sm text-slate-500">
          {otherUser.full_name} et vous vous plaisez mutuellement. Lancez la conversation&nbsp;!
        </p>
        <Link
          to={conversationId ? `/messages/${conversationId}` : "/messages"}
          onClick={onClose}
          className="btn-primary mt-6 w-full"
        >
          <span className="material-symbols-outlined text-lg">chat_bubble</span>
          Envoyer un message
        </Link>
        <button onClick={onClose} className="mt-3 w-full text-sm font-semibold text-slate-400">
          Plus tard
        </button>
      </div>
    </div>
  );
}
