import { useState } from "react";
import ProfilePhoto from "@/components/ProfilePhoto";
import GiftModal from "@/components/GiftModal";
import PointsModal from "@/components/PointsModal";
import { formatLastSeen, responseBadge } from "@/lib/format";

// Carte de profil complète (photo, présence, réactivité, actions) — utilisée
// par Discover pour la pile de découverte. Chaque action (`onXxx`) est
// optionnelle : le bouton correspondant n'apparaît que si son handler est
// fourni, pour rester réutilisable dans d'autres contextes (ex. un match
// déjà établi, qui n'a plus besoin de "annuler le swipe").
export default function ProfileCard({
  profile,
  currentUserPoints = 0,
  onLike,
  onPass,
  onUndo,
  onHeart,
  onMessage,
  onSpend,
  busy = false,
}) {
  const [showGift, setShowGift] = useState(false);
  const [showPoints, setShowPoints] = useState(false);
  const badge = responseBadge(profile.avg_response_seconds);

  return (
    <div className="w-full max-w-sm overflow-hidden rounded-2xl bg-white shadow-xl dark:bg-white/5">
      <div className="relative aspect-[3/4] w-full">
        <ProfilePhoto profile={profile} showOnlineDot className="h-full w-full" />

        {/* Bandeau de stats — s'adapte à l'espace en s'empilant verticalement */}
        <div className="absolute right-2 top-2 flex flex-col items-end gap-1">
          {badge && (
            <span className={`rounded-full px-2.5 py-1 text-[11px] font-bold shadow ${badge.className}`}>
              {badge.label}
            </span>
          )}
          <span className="flex items-center gap-1 rounded-full bg-black/55 px-2.5 py-1 text-[11px] font-bold text-white shadow">
            <span className="material-symbols-outlined text-sm leading-none">favorite</span>
            {profile.likes_received ?? 0}
          </span>
          {profile.hearts_received > 0 && (
            <span className="flex items-center gap-1 rounded-full bg-black/55 px-2.5 py-1 text-[11px] font-bold text-white shadow">
              💖 {profile.hearts_received}
            </span>
          )}
        </div>

        <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/70 to-transparent p-4 pt-10">
          <p className="text-lg font-bold text-white">
            {profile.full_name}
            {profile.age ? `, ${profile.age}` : ""}
          </p>
          {profile.city && <p className="text-sm text-white/80">{profile.city}</p>}
          <p className="mt-1 text-xs text-white/70">
            {profile.is_online ? "En ligne" : formatLastSeen(profile.last_seen_at)}
          </p>
        </div>
      </div>

      {profile.bio && (
        <p className="px-4 pt-3 text-sm text-slate-600 dark:text-slate-300">{profile.bio}</p>
      )}

      <div className="flex flex-wrap items-center justify-center gap-3 p-4">
        {onPass && (
          <ActionButton onClick={onPass} disabled={busy} label="Passer" icon="close" tone="neutral" />
        )}
        {onLike && (
          <ActionButton onClick={onLike} disabled={busy} label="J'aime" icon="favorite" tone="primary" big />
        )}
        {onMessage && (
          <ActionButton onClick={onMessage} disabled={busy} label="Message" icon="chat_bubble" tone="neutral" />
        )}
        {onUndo && (
          <ActionButton onClick={onUndo} disabled={busy} label="Annuler" icon="undo" tone="neutral" />
        )}
        {onHeart && (
          <ActionButton onClick={onHeart} disabled={busy} label="Coup de cœur" icon="volunteer_activism" tone="pink" />
        )}
        <ActionButton onClick={() => setShowPoints(true)} disabled={busy} label="Points" icon="stars" tone="neutral" />
        <ActionButton onClick={() => setShowGift(true)} disabled={busy} label="Cadeau" icon="redeem" tone="neutral" />
      </div>

      {showPoints && (
        <PointsModal
          targetUserId={profile.id}
          targetName={profile.full_name}
          availablePoints={currentUserPoints}
          onClose={() => setShowPoints(false)}
          onSent={() => { setShowPoints(false); onSpend?.(); }}
        />
      )}
      {showGift && (
        <GiftModal
          targetUserId={profile.id}
          targetName={profile.full_name}
          onClose={() => setShowGift(false)}
          onSent={() => { setShowGift(false); onSpend?.(); }}
        />
      )}
    </div>
  );
}

const TONE_CLASSES = {
  neutral: "border-2 border-slate-300 text-slate-500 dark:border-white/20 dark:text-white",
  primary: "bg-primary text-white",
  pink: "bg-pink-500/10 text-pink-500 border-2 border-pink-500/30",
};

function ActionButton({ onClick, disabled, label, icon, tone, big }) {
  const size = big ? "h-16 w-16" : "h-12 w-12";
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      title={label}
      aria-label={label}
      className={`flex ${size} items-center justify-center rounded-full transition disabled:opacity-50 ${TONE_CLASSES[tone]}`}
    >
      <span className="material-symbols-outlined text-xl">{icon}</span>
    </button>
  );
}
