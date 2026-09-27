import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { apiClient, extractErrorMessage } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { useProfileOptions } from "@/hooks/useProfileOptions";
import ProfilePhoto from "@/components/ProfilePhoto";
import VerifiedBadge from "@/components/VerifiedBadge";
import VideoGrid from "@/components/VideoGrid";
import GiftModal from "@/components/GiftModal";
import MatchCelebration from "@/components/MatchCelebration";
import UserActionsMenu from "@/components/UserActionsMenu";
import Toast, { useToast } from "@/components/Toast";
import { formatCount, formatLastSeen, responseBadge } from "@/lib/format";
import TestBadge from "@/components/TestBadge";

/**
 * Fiche publique d'un membre (fond blanc) : carrousel de photos, identité
 * vérifiée, infos clés en puces, centres d'intérêt, grille de ses Moments,
 * et barre d'actions (Passer / J'aime / Message / Cadeau).
 */
export default function UserProfile() {
  const { userId } = useParams();
  const navigate = useNavigate();
  const { user, refresh } = useAuth();
  const options = useProfileOptions();
  const [data, setData] = useState(null);
  const [videos, setVideos] = useState([]);
  const [error, setError] = useState("");
  const [photoIndex, setPhotoIndex] = useState(0);
  const [busy, setBusy] = useState(false);
  const [showGift, setShowGift] = useState(false);
  const [match, setMatch] = useState(null);
  const [toast, showToast] = useToast();

  const load = () =>
    apiClient
      .get(`/users/${userId}`)
      .then((r) => setData(r.data))
      .catch((err) => setError(extractErrorMessage(err, "Profil introuvable")));

  useEffect(() => {
    load();
    apiClient.get(`/users/${userId}/videos`).then((r) => setVideos(r.data)).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userId]);

  if (error) {
    return (
      <div className="flex min-h-[100dvh] flex-col items-center justify-center gap-3 bg-white px-6 text-center font-display">
        <p className="text-5xl">🙈</p>
        <p className="font-extrabold text-ink">{error}</p>
        <button onClick={() => navigate(-1)} className="btn-ghost">Retour</button>
      </div>
    );
  }
  if (!data) {
    return (
      <div className="flex min-h-[100dvh] items-center justify-center bg-white">
        <span className="h-10 w-10 animate-spin rounded-full border-4 border-slate-100 border-t-primary" />
      </div>
    );
  }

  const { profile } = data;
  const approvedPhotos = profile.photos.filter((p) => p.status === "approved");
  const badge = responseBadge(profile.avg_response_seconds);
  const labelOf = (list, value) => list?.find((o) => o.value === value)?.label;
  const facts = [
    profile.profession && { icon: "work", text: profile.profession },
    profile.relationship_goal && { icon: "favorite", text: labelOf(options?.relationship_goals, profile.relationship_goal) },
    profile.children && { icon: "child_care", text: labelOf(options?.children, profile.children) },
  ].filter((f) => f && f.text);

  const swipe = async (action) => {
    setBusy(true);
    try {
      const res = await apiClient.post("/swipe", { target_user_id: profile.id, action });
      if (res.data.matched) {
        const fresh = await apiClient.get(`/users/${profile.id}`);
        setData(fresh.data);
        setMatch({ conversationId: fresh.data.conversation_id });
      } else if (action === "like") {
        setData((d) => ({ ...d, my_swipe: "like" }));
        showToast("Like envoyé 💘");
      } else {
        navigate(-1);
      }
    } catch (err) {
      showToast(extractErrorMessage(err, "Action impossible"));
    } finally {
      setBusy(false);
    }
  };

  // Demande à voir les Moments de ce membre en clair.
  const requestAccess = async () => {
    try {
      const res = await apiClient.post(`/users/${profile.id}/video-access`);
      setData((d) => ({ ...d, video_access: res.data.status }));
      showToast("Demande envoyée 🔓");
    } catch (err) {
      showToast(extractErrorMessage(err, "Demande impossible"));
    }
  };

  return (
    <div className="min-h-[100dvh] bg-white pb-32 font-display text-ink">
      {/* Carrousel de photos (défilement horizontal aimanté) */}
      <div className="relative">
        <div
          className="no-scrollbar flex aspect-[4/5] max-h-[70dvh] w-full snap-x snap-mandatory overflow-x-auto"
          onScroll={(e) => setPhotoIndex(Math.round(e.currentTarget.scrollLeft / e.currentTarget.clientWidth))}
        >
          {(approvedPhotos.length ? approvedPhotos : [null]).map((photo, i) => (
            <div key={photo?.id || i} className="h-full w-full shrink-0 snap-center">
              {photo ? (
                <img src={photo.url} alt={profile.full_name} className="h-full w-full object-cover" />
              ) : (
                <ProfilePhoto profile={profile} className="h-full w-full" />
              )}
            </div>
          ))}
        </div>
        {/* Indicateurs de photo (barres en haut, façon "stories") */}
        {approvedPhotos.length > 1 && (
          <div className="absolute inset-x-4 top-4 flex gap-1.5">
            {approvedPhotos.map((p, i) => (
              <span key={p.id} className={`h-1 flex-1 rounded-full ${i === photoIndex ? "bg-white" : "bg-white/40"}`} />
            ))}
          </div>
        )}
        <div className="absolute inset-x-4 top-8 flex items-center justify-between">
          <button onClick={() => navigate(-1)} aria-label="Retour" className="flex h-10 w-10 items-center justify-center rounded-full bg-white/90 shadow">
            <span className="material-symbols-outlined">arrow_back</span>
          </button>
          {!data.is_me && (
            <div className="flex h-10 w-10 items-center justify-center rounded-full bg-white/90 shadow">
              <UserActionsMenu targetUserId={profile.id} targetName={profile.full_name} />
            </div>
          )}
        </div>
      </div>

      {/* Carte d'identité qui chevauche la photo */}
      <main className="relative -mt-8 rounded-t-[2rem] bg-white px-5 pt-6">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h1 className="flex items-center gap-1.5 text-2xl font-extrabold">
              <span className="truncate">{profile.full_name}</span>
              {profile.age && <span className="font-bold text-slate-400">{profile.age}</span>}
              {profile.verification_status === "verified" && <VerifiedBadge className="text-2xl" />}
              {profile.is_test_data && <TestBadge />}
            </h1>
            {(profile.city || profile.country) && (
              <p className="mt-0.5 flex items-center gap-1 text-sm font-semibold text-slate-500">
                <span className="material-symbols-outlined text-base">location_on</span>
                {[profile.city, profile.country].filter(Boolean).join(", ")}
              </p>
            )}
            <p className="mt-1 flex items-center gap-1.5 text-xs font-semibold text-slate-400">
              <span className={`h-2 w-2 rounded-full ${profile.is_online ? "bg-emerald-500" : "bg-slate-300"}`} />
              {profile.is_online ? "En ligne" : formatLastSeen(profile.last_seen_at)}
            </p>
          </div>
          {badge && <span className={`shrink-0 rounded-full px-3 py-1 text-[11px] font-bold ${badge.className}`}>{badge.label}</span>}
        </div>

        {/* Statistiques façon TikTok */}
        <div className="mt-5 grid grid-cols-3 rounded-2xl bg-slate-50 py-3 text-center">
          <Stat value={formatCount(profile.likes_received)} label="J'aime" />
          <Stat value={formatCount(profile.hearts_received)} label="Coups de cœur" />
          <Stat value={formatCount(data.videos_count)} label="Moments" />
        </div>

        {profile.bio && <p className="mt-5 whitespace-pre-line text-[15px] leading-relaxed text-slate-700">{profile.bio}</p>}

        {facts.length > 0 && (
          <div className="mt-5 flex flex-wrap gap-2">
            {facts.map((f) => (
              <span key={f.icon} className="inline-flex items-center gap-1.5 rounded-full bg-slate-100 px-3 py-1.5 text-sm font-semibold text-slate-700">
                <span className="material-symbols-outlined text-base text-primary">{f.icon}</span>
                {f.text}
              </span>
            ))}
          </div>
        )}

        {profile.interests?.length > 0 && (
          <section className="mt-7">
            <h2 className="section-title">Centres d'intérêt</h2>
            <div className="flex flex-wrap gap-2">
              {profile.interests.map((i) => <span key={i} className="chip border-primary/20 bg-primary/5 text-primary">{i}</span>)}
            </div>
          </section>
        )}

        <section className="mt-7">
          <h2 className="section-title">Moments</h2>
          {!data.is_me && data.videos_count > 0 && data.video_access !== "granted" && (
            <ClearAccessCard
              access={data.video_access}
              viewerVerified={user?.verification_status === "verified"}
              firstName={profile.full_name.split(" ")[0]}
              onRequest={requestAccess}
            />
          )}
          <VideoGrid videos={videos} />
        </section>
      </main>

      {/* Barre d'actions flottante */}
      {!data.is_me && (
        <div className="pb-safe fixed inset-x-0 bottom-0 z-30 flex items-center justify-center gap-4 bg-gradient-to-t from-white via-white to-white/0 px-6 pt-6">
          {data.is_match ? (
            <Link to={data.conversation_id ? `/messages/${data.conversation_id}` : "/messages"} className="btn-primary mb-2 h-14 flex-1">
              <span className="material-symbols-outlined">chat_bubble</span>
              Envoyer un message
            </Link>
          ) : (
            <>
              <RoundAction icon="close" label="Passer" onClick={() => swipe("pass")} disabled={busy} />
              <RoundAction
                icon="favorite"
                label={data.my_swipe === "like" ? "Déjà aimé" : "J'aime"}
                onClick={() => swipe("like")}
                disabled={busy || data.my_swipe === "like"}
                primary
              />
            </>
          )}
          <RoundAction icon="redeem" label="Cadeau" onClick={() => setShowGift(true)} disabled={busy} />
        </div>
      )}

      {showGift && (
        <GiftModal
          targetUserId={profile.id}
          targetName={profile.full_name}
          onClose={() => setShowGift(false)}
          onSent={() => {
            setShowGift(false);
            showToast("Cadeau envoyé 🎁");
            refresh();
          }}
        />
      )}
      {match && <MatchCelebration otherUser={profile} conversationId={match.conversationId} onClose={() => setMatch(null)} />}
      <Toast message={toast} />
    </div>
  );
}

function Stat({ value, label }) {
  return (
    <div>
      <p className="text-lg font-extrabold">{value}</p>
      <p className="text-[11px] font-semibold text-slate-400">{label}</p>
    </div>
  );
}

function RoundAction({ icon, label, onClick, disabled, primary = false }) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      aria-label={label}
      title={label}
      className={`mb-2 flex items-center justify-center rounded-full shadow-xl transition active:scale-90 disabled:opacity-60 ${
        primary ? "h-16 w-16 bg-brand text-white shadow-primary/30" : "h-14 w-14 bg-white text-slate-500 ring-1 ring-slate-100"
      }`}
    >
      <span className={`material-symbols-outlined text-3xl ${primary ? "icon-filled" : ""}`}>{icon}</span>
    </button>
  );
}

/** Encart "Moments floutés" : explique la règle et propose l'action adaptée. */
function ClearAccessCard({ access, viewerVerified, firstName, onRequest }) {
  return (
    <div className="mb-3 flex items-center gap-3 rounded-2xl bg-gradient-to-r from-primary/5 to-sunset/5 p-4 ring-1 ring-primary/10">
      <span className="material-symbols-outlined icon-filled text-2xl text-primary">lock</span>
      <div className="min-w-0 flex-1">
        <p className="text-sm font-extrabold">Moments floutés</p>
        <p className="text-xs text-slate-500">
          {access === "pending"
            ? `Demande envoyée — ${firstName} doit l'accepter.`
            : access === "refused"
            ? `${firstName} n'a pas accordé l'accès.`
            : `Visibles en clair si ${firstName} vous accepte (ou en cas de match).`}
        </p>
      </div>
      {access === "none" &&
        (viewerVerified ? (
          <button onClick={onRequest} className="btn-primary h-9 shrink-0 px-3 text-xs">Voir en clair</button>
        ) : (
          <Link to="/profil#verification" className="btn-ghost h-9 shrink-0 px-3 text-xs">Me vérifier</Link>
        ))}
    </div>
  );
}
