import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { apiClient, extractErrorMessage } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import BottomNav from "@/components/BottomNav";
import VideoSlide from "@/components/VideoSlide";
import CommentsSheet from "@/components/CommentsSheet";
import VideoOptionsSheet from "@/components/VideoOptionsSheet";
import GiftModal from "@/components/GiftModal";
import MatchCelebration from "@/components/MatchCelebration";
import Toast, { useToast } from "@/components/Toast";

// Onglets du haut, comme "Abonnements | Pour toi" sur TikTok.
const TABS = [
  { key: "pres-de-moi", label: "Près de moi" },
  { key: "pour-toi", label: "Pour toi" },
  { key: "matchs", label: "Mes matchs" },
];
const PAGE_SIZE = 8;

/**
 * Fil vidéo vertical plein écran "Moments".
 * - Défilement "aimanté" d'une vidéo à l'autre (CSS scroll-snap), au doigt,
 *   à la molette ou aux flèches ↑/↓ du clavier.
 * - La vidéo visible est détectée par IntersectionObserver -> lecture auto.
 * - Chargement de la page suivante quand on approche de la fin (défilement infini).
 * - /moments/:videoId ouvre directement une vidéo partagée, suivie du fil.
 * - ?tag=xxx filtre le fil sur un #hashtag.
 */
export default function Moments() {
  const { videoId } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const { refresh } = useAuth();
  const tag = searchParams.get("tag");

  const [tab, setTab] = useState("pour-toi");
  const [items, setItems] = useState([]);
  const [hasMore, setHasMore] = useState(true);
  const [loading, setLoading] = useState(true);
  const [hint, setHint] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);
  // Son coupé au départ : les navigateurs n'autorisent la lecture auto
  // qu'en muet. Un tap sur la vidéo réactive le son pour tout le fil.
  const [muted, setMuted] = useState(true);
  const [commentsFor, setCommentsFor] = useState(null);
  const [optionsFor, setOptionsFor] = useState(null);
  const [giftFor, setGiftFor] = useState(null);
  const [match, setMatch] = useState(null); // { otherUser, conversationId }
  const [toast, showToast] = useToast();

  const containerRef = useRef(null);
  const loadingMoreRef = useRef(false); // évite deux chargements simultanés
  const feedCountRef = useRef(0); // nb de vidéos déjà reçues du fil (= skip de la page suivante)
  const viewedRef = useRef(new Set()); // vues déjà envoyées (1 par vidéo et par session)

  // Récupère une page du fil pour l'onglet / le hashtag courant.
  const fetchPage = useCallback(
    (skip) =>
      apiClient.get("/videos/feed", {
        params: { tab: tag ? "pour-toi" : tab, tag: tag || undefined, skip, limit: PAGE_SIZE },
      }),
    [tab, tag],
  );

  // Ajoute une page reçue au fil (sans doublon : une vidéo partagée ouverte
  // en premier peut aussi revenir dans le fil).
  const appendPage = (data) => {
    feedCountRef.current += data.items.length;
    setHint(data.hint || "");
    setHasMore(data.has_more);
    setItems((prev) => {
      const known = new Set(prev.map((v) => v.id));
      return [...prev, ...data.items.filter((v) => !known.has(v.id))];
    });
  };

  // (Re)chargement complet quand l'onglet, le hashtag ou la vidéo ciblée
  // change. Une vidéo partagée (/moments/:videoId) passe en tête du fil.
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setItems([]);
    setActiveIndex(0);
    feedCountRef.current = 0;
    containerRef.current?.scrollTo({ top: 0 });
    (async () => {
      let first = [];
      if (videoId) {
        try {
          first = [(await apiClient.get(`/videos/${videoId}`)).data];
        } catch {
          showToast("Cette vidéo n'est plus disponible");
        }
      }
      try {
        const res = await fetchPage(0);
        if (cancelled) return;
        setItems(first);
        appendPage(res.data);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fetchPage, videoId]);

  // Page suivante (défilement infini).
  const loadMore = useCallback(async () => {
    if (loadingMoreRef.current) return;
    loadingMoreRef.current = true;
    try {
      const res = await fetchPage(feedCountRef.current);
      appendPage(res.data);
    } catch {
      // réseau capricieux : on réessaiera au prochain défilement
    } finally {
      loadingMoreRef.current = false;
    }
  }, [fetchPage]);

  // Détection de la vidéo affichée (au moins 60 % visible).
  useEffect(() => {
    const root = containerRef.current;
    if (!root) return;
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) setActiveIndex(Number(entry.target.dataset.index));
        });
      },
      { root, threshold: 0.6 },
    );
    root.querySelectorAll("[data-index]").forEach((el) => observer.observe(el));
    return () => observer.disconnect();
  }, [items.length]);

  // Défilement infini : 3 vidéos avant la fin, on charge la suite.
  useEffect(() => {
    if (!loading && hasMore && items.length > 0 && activeIndex >= items.length - 3) loadMore();
  }, [activeIndex, items.length, hasMore, loading, loadMore]);

  // Flèches ↑/↓ au clavier (ordinateur).
  useEffect(() => {
    const onKey = (e) => {
      if (commentsFor || optionsFor || giftFor) return;
      const root = containerRef.current;
      if (!root) return;
      if (e.key === "ArrowDown") root.scrollBy({ top: root.clientHeight, behavior: "smooth" });
      if (e.key === "ArrowUp") root.scrollBy({ top: -root.clientHeight, behavior: "smooth" });
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [commentsFor, optionsFor, giftFor]);

  // Met à jour une vidéo du fil localement (compteurs, états).
  const patchVideo = (id, patch) =>
    setItems((prev) => prev.map((v) => (v.id === id ? { ...v, ...(typeof patch === "function" ? patch(v) : patch) } : v)));

  // J'aime "optimiste" : l'interface réagit tout de suite, le serveur suit.
  const handleLike = async (video, like) => {
    patchVideo(video.id, (v) => ({ liked_by_me: like, likes_count: Math.max(0, v.likes_count + (like ? 1 : -1)) }));
    try {
      const res = await apiClient.post(`/videos/${video.id}/like`, null, { params: { like } });
      patchVideo(video.id, { liked_by_me: res.data.liked, likes_count: res.data.likes_count });
    } catch {
      patchVideo(video.id, { liked_by_me: video.liked_by_me, likes_count: video.likes_count });
    }
  };

  // "Ça me plaît" : like du PROFIL de l'auteur (même logique que le swipe).
  const handleLikeProfile = async (video) => {
    if (video.author_liked_by_me) {
      navigate(`/profils/${video.author.id}`);
      return;
    }
    try {
      const res = await apiClient.post("/swipe", { target_user_id: video.author.id, action: "like" });
      setItems((prev) => prev.map((v) => (v.user_id === video.user_id ? { ...v, author_liked_by_me: true } : v)));
      if (res.data.matched) {
        const profile = await apiClient.get(`/users/${video.author.id}`);
        setMatch({ otherUser: profile.data.profile, conversationId: profile.data.conversation_id });
      } else {
        showToast(`${video.author.full_name.split(" ")[0]} saura que vous l'appréciez 💘`);
      }
    } catch (err) {
      showToast(extractErrorMessage(err, "Action impossible"));
    }
  };

  const handleShare = async (video) => {
    const url = `${window.location.origin}/moments/${video.id}`;
    try {
      if (navigator.share) {
        await navigator.share({ title: `${video.author.full_name} sur bAuthentik`, text: video.caption, url });
      } else {
        await navigator.clipboard.writeText(url);
        showToast("Lien copié 🔗");
      }
    } catch {
      // partage annulé par l'utilisateur : rien à faire
    }
  };

  const handleViewed = useCallback((id) => {
    if (viewedRef.current.has(id)) return;
    viewedRef.current.add(id);
    apiClient.post(`/videos/${id}/view`).catch(() => {});
  }, []);

  const openTag = (t) => setSearchParams({ tag: t });

  return (
    <div className="flex h-[100dvh] flex-col bg-black">
      <div className="relative min-h-0 flex-1">
        {/* En-tête flottant : onglets ou hashtag actif */}
        <header className="absolute inset-x-0 top-0 z-20 flex items-center justify-center gap-5 px-4 pt-4">
          <Link to="/recherche" aria-label="Rechercher" className="absolute left-4 top-4 text-white drop-shadow">
            <span className="material-symbols-outlined text-[28px]">search</span>
          </Link>
          {tag ? (
            <button
              onClick={() => setSearchParams({})}
              className="glass flex items-center gap-1 rounded-full px-4 py-1.5 text-sm font-extrabold text-white"
            >
              #{tag}
              <span className="material-symbols-outlined text-base">close</span>
            </button>
          ) : (
            TABS.map((t) => (
              <button
                key={t.key}
                onClick={() => setTab(t.key)}
                className={`relative pb-1.5 text-[15px] font-extrabold drop-shadow transition ${
                  tab === t.key ? "text-white" : "text-white/60"
                }`}
              >
                {t.label}
                {tab === t.key && <span className="absolute inset-x-3 bottom-0 h-[3px] rounded-full bg-white" />}
              </button>
            ))
          )}
        </header>

        {/* Le fil : une vidéo par "page", défilement aimanté */}
        <div ref={containerRef} className="no-scrollbar h-full snap-y snap-mandatory overflow-y-scroll">
          {items.map((video, index) => (
            <div key={video.id} data-index={index} className="h-full">
              <VideoSlide
                video={video}
                active={index === activeIndex}
                // Précharge la vidéo suivante pour un enchaînement instantané.
                preload={Math.abs(index - activeIndex) <= 1 ? "auto" : "metadata"}
                muted={muted}
                onToggleMute={() => setMuted((m) => !m)}
                onLike={handleLike}
                onLikeProfile={handleLikeProfile}
                onComments={setCommentsFor}
                onGift={setGiftFor}
                onShare={handleShare}
                onMore={setOptionsFor}
                onTag={openTag}
                onViewed={handleViewed}
              />
            </div>
          ))}

          {!loading && items.length === 0 && <EmptyFeed tab={tab} tag={tag} hint={hint} />}
          {loading && items.length === 0 && (
            <div className="flex h-full items-center justify-center">
              <span className="h-10 w-10 animate-spin rounded-full border-4 border-white/20 border-t-primary" />
            </div>
          )}
        </div>
      </div>

      <BottomNav />

      {commentsFor && (
        <CommentsSheet
          video={commentsFor}
          onClose={() => setCommentsFor(null)}
          onCountChange={(delta) => patchVideo(commentsFor.id, (v) => ({ comments_count: Math.max(0, v.comments_count + delta) }))}
        />
      )}
      {optionsFor && (
        <VideoOptionsSheet
          video={optionsFor}
          onClose={() => setOptionsFor(null)}
          onRemoved={(id) => setItems((prev) => prev.filter((v) => v.id !== id))}
          notify={showToast}
        />
      )}
      {giftFor && (
        <GiftModal
          targetUserId={giftFor.author.id}
          targetName={giftFor.author.full_name}
          onClose={() => setGiftFor(null)}
          onSent={() => {
            setGiftFor(null);
            showToast("Cadeau envoyé 🎁");
            refresh();
          }}
        />
      )}
      {match && (
        <MatchCelebration otherUser={match.otherUser} conversationId={match.conversationId} onClose={() => setMatch(null)} />
      )}
      <Toast message={toast} />
    </div>
  );
}

/** Fil vide : message et appel à l'action adaptés à l'onglet. */
function EmptyFeed({ tab, tag, hint }) {
  const content = tag
    ? { emoji: "🔎", title: `Aucune vidéo #${tag}`, text: "Lancez la tendance en publiant la première !" }
    : tab === "matchs"
    ? { emoji: "💞", title: "Vos matchs n'ont rien publié", text: "Découvrez de nouveaux profils pour élargir votre cercle." }
    : tab === "pres-de-moi" && hint
    ? { emoji: "📍", title: "Où êtes-vous ?", text: hint }
    : { emoji: "🎬", title: "Le fil est encore calme", text: "Soyez parmi les premiers à publier un Moment !" };

  return (
    <div className="flex h-full flex-col items-center justify-center gap-3 px-8 text-center">
      <span className="text-6xl">{content.emoji}</span>
      <p className="text-xl font-extrabold text-white">{content.title}</p>
      <p className="max-w-xs text-sm text-white/70">{content.text}</p>
      <Link to={hint ? "/profil" : "/moments/publier"} className="btn-primary mt-3">
        <span className="material-symbols-outlined text-lg">{hint ? "edit" : "videocam"}</span>
        {hint ? "Compléter mon profil" : "Publier un Moment"}
      </Link>
    </div>
  );
}
