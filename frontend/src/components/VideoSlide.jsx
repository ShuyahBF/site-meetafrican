import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import VerifiedBadge from "@/components/VerifiedBadge";
import { formatCount } from "@/lib/format";
import TestBadge from "@/components/TestBadge";

// Délai max entre deux taps pour qu'ils comptent comme un double-tap.
const DOUBLE_TAP_MS = 280;
// Temps de lecture avant de compter une "vue" (évite de compter les vidéos
// qu'on fait défiler sans les regarder).
const VIEW_AFTER_MS = 2000;

/**
 * Une vidéo plein écran du fil "Moments" — tout le côté "TikTok" est ici :
 *   - lecture auto en boucle quand la vidéo est à l'écran (`active`), pause sinon ;
 *   - 1 tap = pause/lecture (+ réactive le son la première fois) ;
 *   - double-tap = J'aime, avec un gros cœur qui éclate là où on a tapé ;
 *   - colonne d'actions à droite (profil + "Ça me plaît", J'aime,
 *     commentaires, cadeau, partage) ;
 *   - légende avec #hashtags cliquables et barre de progression fine en bas ;
 *   - vidéo FLOUTÉE (par le serveur) tant que l'auteur n'a pas accepté le
 *     visiteur : cadenas + bouton "Voir en clair" (cf. AccessBadge).
 */
export default function VideoSlide({
  video,
  active,
  preload,
  muted,
  onToggleMute,
  onLike,
  onLikeProfile,
  onComments,
  onGift,
  onShare,
  onMore,
  onTag,
  onViewed,
  onRequestAccess,
  viewerVerified,
}) {
  const videoRef = useRef(null);
  const lastTapRef = useRef(0);
  const singleTapTimer = useRef(null);
  const [paused, setPaused] = useState(false);
  const [progress, setProgress] = useState(0);
  const [hearts, setHearts] = useState([]); // cœurs du double-tap en cours d'animation
  const [likePop, setLikePop] = useState(false);
  const [expanded, setExpanded] = useState(false); // légende dépliée

  // Lecture / pause selon que la vidéo est celle affichée à l'écran.
  useEffect(() => {
    const el = videoRef.current;
    if (!el) return;
    if (active) {
      el.currentTime = 0;
      el.play().then(() => setPaused(false)).catch(() => setPaused(true));
    } else {
      el.pause();
    }
  }, [active]);

  // Compte une vue après VIEW_AFTER_MS de lecture effective.
  useEffect(() => {
    if (!active || paused) return;
    const t = setTimeout(() => onViewed?.(video.id), VIEW_AFTER_MS);
    return () => clearTimeout(t);
  }, [active, paused, video.id, onViewed]);

  const togglePlay = () => {
    const el = videoRef.current;
    if (!el) return;
    if (el.paused) {
      el.play().catch(() => {});
      setPaused(false);
    } else {
      el.pause();
      setPaused(true);
    }
  };

  // Distingue simple tap (pause) et double-tap (J'aime) sur la vidéo.
  const handleTap = (e) => {
    const now = Date.now();
    const rect = e.currentTarget.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;

    if (now - lastTapRef.current < DOUBLE_TAP_MS) {
      // Double-tap : annule la pause prévue, lance le cœur, aime la vidéo
      // (sans jamais "désaimer" — comme sur TikTok).
      clearTimeout(singleTapTimer.current);
      lastTapRef.current = 0;
      const id = now;
      setHearts((h) => [...h, { id, x, y }]);
      setTimeout(() => setHearts((h) => h.filter((heart) => heart.id !== id)), 900);
      if (!video.liked_by_me) triggerLike(true);
      return;
    }
    lastTapRef.current = now;
    singleTapTimer.current = setTimeout(() => {
      // Premier tap sur un fil muet : on active le son plutôt que de mettre
      // en pause (c'est presque toujours ce que la personne veut).
      if (muted) onToggleMute();
      else togglePlay();
    }, DOUBLE_TAP_MS);
  };

  const triggerLike = (like) => {
    setLikePop(true);
    setTimeout(() => setLikePop(false), 350);
    onLike(video, like);
  };

  const author = video.author;
  const caption = video.caption || "";

  return (
    <section className="relative h-full w-full snap-start snap-always overflow-hidden bg-black">
      <video
        ref={videoRef}
        src={video.url}
        // Vignette floutée affichée pendant le chargement (pas d'écran noir).
        poster={video.poster_url || undefined}
        className="absolute inset-0 h-full w-full object-cover"
        loop
        playsInline
        muted={muted}
        preload={preload}
        onTimeUpdate={(e) => {
          const el = e.currentTarget;
          if (el.duration) setProgress((el.currentTime / el.duration) * 100);
        }}
      />

      {/* Zone de tap (sous les boutons) */}
      <div className="absolute inset-0" onClick={handleTap} />

      {/* Dégradés haut/bas pour garder textes et icônes lisibles */}
      <div className="pointer-events-none absolute inset-x-0 top-0 h-32 bg-gradient-to-b from-black/50 to-transparent" />
      <div className="pointer-events-none absolute inset-x-0 bottom-0 h-72 bg-gradient-to-t from-black/75 via-black/30 to-transparent" />

      {/* Icône lecture quand en pause */}
      {paused && (
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
          <span className="material-symbols-outlined icon-filled animate-pop text-[88px] text-white/80 drop-shadow-lg">
            play_arrow
          </span>
        </div>
      )}

      {/* Cœurs du double-tap */}
      {hearts.map((h) => (
        <span
          key={h.id}
          className="material-symbols-outlined icon-filled pointer-events-none absolute animate-heart-burst text-[110px] text-primary drop-shadow-[0_6px_20px_rgba(244,37,106,0.6)]"
          style={{ left: h.x, top: h.y }}
        >
          favorite
        </span>
      ))}

      {/* Colonne d'actions à droite */}
      <div className="absolute bottom-24 right-3 flex flex-col items-center gap-5">
        {/* Avatar -> profil ; pastille ✚ = "Ça me plaît" (like du PROFIL, peut créer un match) */}
        <div className="relative mb-2">
          <Link to={`/profils/${author.id}`} className="block h-12 w-12 overflow-hidden rounded-full bg-slate-200 ring-2 ring-white">
            {author.avatar_url ? (
              <img src={author.avatar_url} alt={author.full_name} className="h-full w-full object-cover" />
            ) : (
              <span className="flex h-full w-full items-center justify-center bg-brand text-lg font-extrabold text-white">
                {author.full_name?.[0]}
              </span>
            )}
          </Link>
          {!video.is_mine && (
            <button
              onClick={() => onLikeProfile(video)}
              aria-label={video.author_liked_by_me ? "Profil déjà aimé" : "Ça me plaît"}
              className={`absolute -bottom-2 left-1/2 flex h-6 w-6 -translate-x-1/2 items-center justify-center rounded-full text-white shadow ${
                video.author_liked_by_me ? "bg-white text-primary" : "bg-brand"
              }`}
            >
              <span className={`material-symbols-outlined text-base ${video.author_liked_by_me ? "icon-filled text-primary" : ""}`}>
                {video.author_liked_by_me ? "favorite" : "add"}
              </span>
            </button>
          )}
        </div>

        <RailButton
          icon="favorite"
          filled={video.liked_by_me}
          color={video.liked_by_me ? "text-primary" : "text-white"}
          pop={likePop}
          label={formatCount(video.likes_count)}
          onClick={() => triggerLike(!video.liked_by_me)}
          aria={video.liked_by_me ? "Je n'aime plus" : "J'aime"}
        />
        <RailButton icon="chat_bubble" filled label={formatCount(video.comments_count)} onClick={() => onComments(video)} aria="Commentaires" />
        {!video.is_mine && <RailButton icon="redeem" filled label="Cadeau" onClick={() => onGift(video)} aria="Envoyer un cadeau" />}
        <RailButton icon="share" filled label="Partager" onClick={() => onShare(video)} aria="Partager" />
        <RailButton icon="more_horiz" label="" onClick={() => onMore(video)} aria="Plus d'options" />
      </div>

      {/* Infos auteur + légende */}
      <div className="absolute bottom-6 left-4 right-20 text-white">
        {/* Nom + âge + badges en flux "texte" (retour à la ligne naturel si le nom est long) */}
        <Link to={`/profils/${author.id}`} className="block text-base font-extrabold leading-tight drop-shadow">
          {author.full_name}
          {author.age ? <span className="whitespace-nowrap font-semibold text-white/85"> · {author.age} ans</span> : null}
          {author.is_verified && <VerifiedBadge className="ml-1 text-lg" />}
          {author.is_test_data && <TestBadge dark className="ml-1.5" />}
          {author.is_online && <span className="ml-1.5 inline-block h-2 w-2 rounded-full bg-emerald-400 align-middle ring-2 ring-emerald-400/30" />}
        </Link>
        {(author.city || author.country) && (
          <p className="mt-0.5 flex items-center gap-1 text-xs font-semibold text-white/80">
            <span className="material-symbols-outlined text-sm">location_on</span>
            {[author.city, author.country].filter(Boolean).join(", ")}
            {/* Mode "Autour de moi" : distance approximative (jamais la position) */}
            {video.distance_km ? <span className="text-white/60"> · à {video.distance_km} km</span> : null}
          </p>
        )}
        {caption && (
          <p
            onClick={() => setExpanded((v) => !v)}
            className={`mt-2 text-sm leading-snug drop-shadow ${expanded ? "" : "line-clamp-2"}`}
          >
            <CaptionWithTags caption={caption} onTag={onTag} />
          </p>
        )}
      </div>

      {/* Bouton son (haut droite) — absent sur la version floutée, qui
          n'a pas de piste audio (la voix identifie aussi). */}
      {video.is_clear && (
        <button
          onClick={onToggleMute}
          aria-label={muted ? "Activer le son" : "Couper le son"}
          className="glass absolute right-3 top-16 flex h-9 w-9 items-center justify-center rounded-full text-white"
        >
          <span className="material-symbols-outlined text-xl">{muted ? "volume_off" : "volume_up"}</span>
        </button>
      )}

      {/* Vidéo floutée : cadenas + action pour la voir en clair */}
      {!video.is_clear && (
        <AccessBadge video={video} viewerVerified={viewerVerified} onRequestAccess={onRequestAccess} />
      )}

      {/* Barre de progression */}
      <div className="absolute inset-x-0 bottom-0 h-[3px] bg-white/20">
        <div className="h-full bg-gradient-to-r from-primary to-sunset" style={{ width: `${progress}%` }} />
      </div>
    </section>
  );
}

function RailButton({ icon, label, onClick, filled = false, color = "text-white", pop = false, aria }) {
  return (
    <button onClick={onClick} aria-label={aria} className="flex flex-col items-center gap-0.5 text-white active:scale-90">
      <span
        className={`material-symbols-outlined text-[34px] drop-shadow-[0_2px_6px_rgba(0,0,0,0.45)] ${color} ${
          filled ? "icon-filled" : ""
        } ${pop ? "animate-pop" : ""}`}
      >
        {icon}
      </span>
      {label && <span className="text-xs font-bold drop-shadow">{label}</span>}
    </button>
  );
}

/** Rend les #hashtags de la légende cliquables (filtrent le fil). */
function CaptionWithTags({ caption, onTag }) {
  const parts = caption.split(/(#[\wÀ-ÿ]{2,30})/g);
  return parts.map((part, i) =>
    part.startsWith("#") ? (
      <button
        key={i}
        onClick={(e) => {
          e.stopPropagation();
          onTag(part.slice(1).toLowerCase());
        }}
        className="font-extrabold text-white"
      >
        {part}
      </button>
    ) : (
      <span key={i}>{part}</span>
    ),
  );
}

/**
 * Pastille centrale sur une vidéo floutée. Selon la situation du visiteur :
 *   - identité non vérifiée  -> lien vers la vérification ;
 *   - pas encore demandé     -> bouton "Demander à voir en clair" ;
 *   - demande en attente     -> "Demande envoyée" ;
 *   - demande refusée        -> "Accès non accordé".
 */
function AccessBadge({ video, viewerVerified, onRequestAccess }) {
  const first = video.author.full_name.split(" ")[0];
  let content;
  if (!viewerVerified) {
    content = (
      <Link to="/profil#verification" className="btn-primary h-10 px-4 text-xs">
        <span className="material-symbols-outlined text-base">verified</span>
        Vérifiez-vous pour voir en clair
      </Link>
    );
  } else if (video.access === "pending") {
    content = <span className="text-sm font-bold text-white">⏳ Demande envoyée à {first}</span>;
  } else if (video.access === "refused") {
    content = <span className="text-sm font-bold text-white/80">Accès non accordé</span>;
  } else {
    content = (
      <button onClick={() => onRequestAccess(video)} className="btn-primary h-10 px-4 text-xs">
        <span className="material-symbols-outlined text-base">visibility</span>
        Demander à voir en clair
      </button>
    );
  }
  return (
    <div className="pointer-events-none absolute left-0 right-20 top-[20%] flex justify-center pl-4">
      <div className="glass pointer-events-auto flex flex-col items-center gap-2 rounded-3xl px-5 py-4 text-center">
        <span className="material-symbols-outlined icon-filled text-3xl text-white">lock</span>
        <p className="text-xs font-semibold text-white/85">
          Visage flouté · visible en clair si {first} vous accepte
        </p>
        {content}
      </div>
    </div>
  );
}
