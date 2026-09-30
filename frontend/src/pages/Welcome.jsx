import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { apiClient } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import PaymentMethods from "@/components/PaymentMethods";

const DEFAULT_HERO_IMAGE = "/images/hero-couple.jpg";

// Dernière image d'accueil connue, mémorisée dans le navigateur : au
// rechargement suivant, on la pré-télécharge pendant que /appearance
// répond, pour qu'elle s'affiche sans délai si le réglage n'a pas changé.
// Elle n'est jamais AFFICHÉE avant la réponse : si l'admin a changé
// d'image entre-temps, l'ancienne ne doit pas apparaître.
const HERO_CACHE_KEY = "maf_hero_image";

function readCachedHero() {
  try {
    return localStorage.getItem(HERO_CACHE_KEY);
  } catch {
    return null; // stockage indisponible (navigation privée…)
  }
}

function writeCachedHero(url) {
  try {
    localStorage.setItem(HERO_CACHE_KEY, url);
  } catch {
    // stockage indisponible : sans conséquence, on attendra l'API la prochaine fois
  }
}

// Formules affichées si l'API est momentanément injoignable — mêmes valeurs
// que les formules par défaut du backend (backend/seed.py). Les vraies
// formules (modifiables dans l'admin) remplacent celles-ci dès réception.
const FALLBACK_PLANS = [
  { id: "1_semaine", name: "1 Semaine", duration_days: 7, price_xof: 5000, features: ["Accès illimité au chat", "Voir toutes les photos", "Filtres de recherche avancée"] },
  { id: "1_mois", name: "1 Mois", duration_days: 30, price_xof: 12000, badge: "Populaire", features: ["Accès illimité au chat", "Voir toutes les photos", "Filtres de recherche avancée", "Voir qui a visité votre profil"] },
  { id: "12_mois", name: "12 Mois", duration_days: 365, price_xof: 55000, savings_pct: 62, featured: true, badge: "Meilleure offre", features: ["Accès illimité au chat", "Voir toutes les photos", "Filtres de recherche avancée", "Voir qui a visité votre profil", "Navigation sans publicité"] },
];

// Ce que propose le compte gratuit (fonctionnalités réellement ouvertes
// sans abonnement dans le code actuel).
const FREE_FEATURES = [
  "Créer son profil et ses photos",
  "Swiper, liker et matcher",
  "Regarder les Moments (floutés)",
  "Publier des Moments (identité vérifiée)",
];

// Fonctionnalités mises en avant — chacune correspond à une fonctionnalité
// réellement implémentée (pas de promesse en l'air).
const FEATURES = [
  { icon: "play_circle", title: "Les Moments, en vidéo", text: "Un fil vertical façon TikTok : défilez, double-tapez pour aimer, découvrez les gens tels qu'ils sont.", tint: "from-primary/15 to-sunset/15", big: true },
  { icon: "verified", title: "100 % identités vérifiées", text: "Pièce d'identité contrôlée par IA puis par un humain en cas de doute. Le badge bleu ne ment pas.", tint: "from-sky-100 to-sky-50" },
  { icon: "lock", title: "Votre image vous appartient", text: "Votre visage est flouté pour tous sur vos vidéos. Seuls vos matchs et les membres que vous acceptez vous voient en clair.", tint: "from-purple-100 to-purple-50" },
  { icon: "bolt", title: "Chat en temps réel", text: "Messages instantanés, « en train d'écrire… », accusés « Vu ». La conversation coule naturellement.", tint: "from-amber-100 to-amber-50" },
  { icon: "tune", title: "Recherche avancée", text: "Âge, ville, pays, type de relation, enfants, centres d'intérêt : trouvez exactement qui vous correspond.", tint: "from-emerald-100 to-emerald-50" },
  { icon: "redeem", title: "Cadeaux & coups de cœur", text: "Une rose, un bouquet, un diamant : faites-vous remarquer avec élégance.", tint: "from-rose-100 to-rose-50" },
];

const STEPS = [
  { n: "1", title: "Créez votre profil", text: "Gratuit, en 2 minutes. Ajoutez vos photos et vérifiez votre identité." },
  { n: "2", title: "Explorez", text: "Regardez les Moments, swipez, filtrez par ville ou par centres d'intérêt." },
  { n: "3", title: "Matchez & discutez", text: "Dès que c'est réciproque, la conversation s'ouvre, en direct." },
];

const FAQ = [
  { q: "L'inscription est-elle gratuite ?", a: "Oui. Créer son profil, swiper, matcher et regarder les Moments est gratuit. L'abonnement Premium débloque tout le reste." },
  { q: "Comment payer l'abonnement ?", a: "Par Mobile Money : Orange Money, Moov Money, Telecel Money, Sank Money, via la page de paiement sécurisée PawaPay. Aucune carte bancaire nécessaire." },
  { q: "Qui peut voir mes vidéos ?", a: "Tout le monde voit votre vidéo avec le visage flouté et sans le son. La version claire est réservée à vos matchs et aux membres vérifiés que vous acceptez — et vous pouvez retirer l'accès à tout moment." },
  { q: "Pourquoi vérifier mon identité ?", a: "Pour garantir une communauté de personnes réelles. La vérification donne le badge bleu et permet de publier des Moments. Votre pièce n'est jamais montrée aux autres membres." },
];

/** 55000 -> "55 000" (espaces fines insécables, format français). */
const fcfa = (n) => new Intl.NumberFormat("fr-FR").format(n);

/** Libellé de période d'une formule : "/ semaine", "/ mois", "/ an", sinon "/ 90 jours". */
function periodLabel(days) {
  if (days === 7) return "/ semaine";
  if (days === 30 || days === 31) return "/ mois";
  if (days === 365) return "/ an";
  return `/ ${days} jours`;
}

/**
 * Petit encart vidéo montrant ce qu'est un Moment (vidéo réglée dans
 * l'admin : Paramètres > Apparence de la page d'accueil).
 *
 * - Souris : la vidéo démarre au survol et s'arrête (retour au début)
 *   quand la souris sort de l'encart.
 * - Écran tactile (pas de survol possible) : un toucher lance la lecture,
 *   un second toucher l'arrête. La lecture s'arrête aussi d'elle-même dès
 *   que l'encart sort de l'écran (défilement).
 * - Clavier : Entrée / Espace alternent lecture et arrêt.
 * Vidéo toujours muette et en boucle ; preload="metadata" pour ne charger
 * que l'en-tête du fichier tant que personne ne la lance.
 */
function MomentsVideo({ src, poster }) {
  const videoRef = useRef(null);
  const boxRef = useRef(null);
  const [playing, setPlaying] = useState(false);
  // Type du dernier pointeur ayant touché l'encart ("mouse", "touch", "pen").
  const pointerType = useRef("mouse");

  const play = () => {
    const video = videoRef.current;
    if (!video) return;
    // play() peut être refusé par le navigateur : on reste alors à l'arrêt.
    video.play().then(() => setPlaying(!video.paused)).catch(() => setPlaying(false));
  };

  const stop = () => {
    const video = videoRef.current;
    if (!video) return;
    video.pause();
    video.currentTime = 0;
    setPlaying(false);
  };

  const toggle = () => (playing ? stop() : play());

  // Arrêt automatique quand l'encart sort de l'écran (utile surtout sur
  // mobile, où aucun "survol terminé" ne vient arrêter la vidéo).
  useEffect(() => {
    const box = boxRef.current;
    if (!box || typeof IntersectionObserver === "undefined") return undefined;
    const observer = new IntersectionObserver(([entry]) => {
      if (!entry.isIntersecting) stop();
    });
    observer.observe(box);
    return () => observer.disconnect();
  }, []);

  // Sans image d'aperçu, "#t=0.1" force l'affichage de la première image
  // de la vidéo (Safari iOS n'affiche sinon qu'un cadre noir).
  const videoSrc = poster ? src : `${src}#t=0.1`;

  return (
    <div
      ref={boxRef}
      role="button"
      tabIndex={0}
      aria-label={playing ? "Arrêter la vidéo de présentation des Moments" : "Lire la vidéo de présentation des Moments"}
      onPointerDown={(e) => { pointerType.current = e.pointerType; }}
      onPointerEnter={(e) => { if (e.pointerType === "mouse") play(); }}
      onPointerLeave={(e) => { if (e.pointerType === "mouse") stop(); }}
      onClick={() => { if (pointerType.current !== "mouse") toggle(); }}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          toggle();
        }
      }}
      className="relative mx-auto aspect-[9/16] w-full max-w-[200px] shrink-0 cursor-pointer overflow-hidden rounded-2xl bg-ink shadow-lg ring-1 ring-black/5 md:mx-0 md:w-48"
    >
      <video
        ref={videoRef}
        src={videoSrc}
        poster={poster}
        muted
        loop
        playsInline
        preload="metadata"
        disablePictureInPicture
        className="h-full w-full object-cover"
      />
      {/* Pictogramme "lecture" visible tant que la vidéo est à l'arrêt */}
      <div
        className={`pointer-events-none absolute inset-0 flex flex-col items-center justify-center gap-1 bg-black/20 text-white transition-opacity duration-300 ${
          playing ? "opacity-0" : "opacity-100"
        }`}
      >
        <span className="material-symbols-outlined icon-filled text-5xl drop-shadow">play_circle</span>
        <span className="text-[11px] font-bold drop-shadow">
          {/* Libellé adapté à l'appareil : survol possible (souris) ou non (tactile) */}
          <span className="hidden [@media(hover:hover)]:inline">Survolez pour voir</span>
          <span className="[@media(hover:hover)]:hidden">Touchez pour voir</span>
        </span>
      </div>
    </div>
  );
}

/**
 * Page d'accueil publique — fond blanc, simple et stylée :
 * héros avec maquette de téléphone animée, étapes, fonctionnalités
 * (grille "bento"), garanties de confiance, tarifs, FAQ, appel final.
 */
export default function Welcome() {
  const { user } = useAuth();
  // Image modifiable par l'admin (Paramètres > Apparence) sans redéploiement.
  // État initial = RIEN : aucune image (ni celle par défaut, ni une
  // ancienne) n'est affichée tant que le réglage n'est pas connu, sinon
  // elle "clignote" avant d'être remplacée par l'image paramétrée.
  const [heroImage, setHeroImage] = useState(null);
  // Adresse de l'image effectivement chargée : sert au fondu d'apparition.
  const [heroLoaded, setHeroLoaded] = useState(null);
  // Encart vidéo « Moments » (réglé dans l'admin) — null = pas d'encart.
  const [momentsVideo, setMomentsVideo] = useState(null);
  const [plans, setPlans] = useState(FALLBACK_PLANS);
  const [stats, setStats] = useState(null); // { registered, verified, visits, your_ip }

  useEffect(() => {
    // Pré-téléchargement (invisible) de la dernière image connue, en
    // parallèle de l'appel à l'API : le cache HTTP du navigateur la servira
    // instantanément si elle est toujours d'actualité.
    const cachedHero = readCachedHero();
    if (cachedHero) new Image().src = cachedHero;
    apiClient
      .get("/appearance")
      .then((r) => {
        // Image paramétrée, sinon image par défaut — puis mémorisation pour
        // le prochain chargement de la page.
        const url = r.data?.hero_image_url || DEFAULT_HERO_IMAGE;
        setHeroImage(url);
        writeCachedHero(url);
        // Vidéo affichée uniquement si elle est activée ET renseignée.
        if (r.data?.moments_video_enabled && r.data?.moments_video_url) {
          setMomentsVideo({ src: r.data.moments_video_url, poster: r.data.moments_video_poster_url || undefined });
        }
      })
      // API injoignable : dernière image connue, sinon l'image par défaut.
      .catch(() => setHeroImage(cachedHero || DEFAULT_HERO_IMAGE));
    // Compteurs publics + IP du visiteur. La visite n'est enregistrée qu'une
    // fois par session de navigation (le serveur ne compte de toute façon
    // qu'une visite par IP et par jour).
    let alreadyCounted = false;
    try {
      alreadyCounted = sessionStorage.getItem("maf_visit") === "1";
      sessionStorage.setItem("maf_visit", "1");
    } catch {
      // stockage indisponible (navigation privée…) : on enregistre la visite
    }
    (alreadyCounted ? apiClient.get("/stats/public") : apiClient.post("/stats/visit"))
      .then((r) => setStats(r.data))
      .catch(() => {});
    apiClient
      .get("/subscriptions/plans")
      .then((r) => r.data?.length && setPlans([...r.data].sort((a, b) => a.duration_days - b.duration_days)))
      .catch(() => {});
  }, []);

  // Connecté : les appels à l'action mènent directement à l'application.
  const primaryTo = user ? "/moments" : "/inscription";
  const primaryLabel = user ? "Ouvrir l'application" : "Créer mon compte gratuit";
  const planTo = user ? "/abonnement" : "/inscription";

  return (
    <div className="min-h-screen overflow-x-hidden bg-white font-display text-ink">
      {/* ---------------------------------------------------------------- */}
      {/* Barre de navigation                                               */}
      {/* ---------------------------------------------------------------- */}
      <header className="sticky top-0 z-40 border-b border-slate-100/80 bg-white/80 backdrop-blur-lg">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-5 py-3.5">
          <Link to="/" className="flex items-center gap-2 text-2xl font-extrabold tracking-tight">
            <img src="/icone-beauthentik.svg" alt="" className="h-9 w-9 rounded-xl" />
            <span>be<span className="text-brand">Authentik</span></span>
          </Link>
          <nav className="hidden items-center gap-8 text-sm font-semibold text-slate-500 md:flex">
            <a href="#fonctionnalites" className="hover:text-ink">Fonctionnalités</a>
            <a href="#confiance" className="hover:text-ink">Sécurité</a>
            <a href="#tarifs" className="hover:text-ink">Tarifs</a>
            <a href="#faq" className="hover:text-ink">FAQ</a>
          </nav>
          <div className="flex items-center gap-2">
            {!user && (
              <Link to="/connexion" className="whitespace-nowrap rounded-full px-3 py-2 text-sm font-bold text-ink hover:bg-slate-50 sm:px-4">
                <span className="sm:hidden">Connexion</span>
                <span className="hidden sm:inline">Se connecter</span>
              </Link>
            )}
            <Link to={primaryTo} className="btn-primary h-10 px-5 text-sm">
              {user ? "Ouvrir" : "S'inscrire"}
            </Link>
          </div>
        </div>
      </header>

      {/* ---------------------------------------------------------------- */}
      {/* Héros                                                             */}
      {/* ---------------------------------------------------------------- */}
      <section className="relative">
        {/* Halos colorés d'arrière-plan (décor) */}
        <div className="pointer-events-none absolute -left-32 -top-32 h-96 w-96 rounded-full bg-primary/15 blur-3xl" />
        <div className="pointer-events-none absolute -right-24 top-40 h-96 w-96 rounded-full bg-sunset/15 blur-3xl" />

        <div className="relative mx-auto grid max-w-6xl items-center gap-12 px-5 pb-16 pt-10 md:grid-cols-2 md:pb-24 md:pt-16">
          <div className="text-center md:text-left">
            <span className="inline-flex items-center gap-2 rounded-full bg-white px-4 py-1.5 text-xs font-bold text-slate-600 shadow-sm ring-1 ring-slate-100">
              <span className="material-symbols-outlined icon-filled text-base text-sky-500">verified</span>
              Des profils 100 % vérifiés
            </span>
            <h1 className="mt-5 text-[2.6rem] font-extrabold leading-[1.05] tracking-tight md:text-6xl">
              Rencontrez des Africains <span className="text-brand">authentiques</span>.
            </h1>
            <p className="mx-auto mt-5 max-w-md text-base leading-relaxed text-slate-500 md:mx-0 md:text-lg">
              Des vidéos, des vrais profils, des matchs qui comptent. Le site de rencontre pensé pour l'Afrique et sa
              diaspora — où que vous soyez.
            </p>
            <div className="mt-8 flex flex-col items-center gap-3 sm:flex-row sm:justify-center md:justify-start">
              <Link to={primaryTo} className="btn-primary h-14 w-full px-8 text-base sm:w-auto">
                {primaryLabel}
                <span className="material-symbols-outlined">arrow_forward</span>
              </Link>
              <a href="#tarifs" className="btn-ghost h-14 w-full px-8 text-base sm:w-auto">Voir les tarifs</a>
            </div>
            <div className="mt-8 flex flex-wrap items-center justify-center gap-x-5 gap-y-2 text-xs font-semibold text-slate-400 md:justify-start">
              <span className="flex items-center gap-1"><span className="material-symbols-outlined text-base text-emerald-500">check_circle</span>Inscription gratuite</span>
              <span className="flex items-center gap-1"><span className="material-symbols-outlined text-base text-emerald-500">check_circle</span>Paiement Mobile Money</span>
              <span className="flex items-center gap-1"><span className="material-symbols-outlined text-base text-emerald-500">check_circle</span>Vie privée protégée</span>
            </div>
            {/* Liens légaux visibles dès l'accueil, sans ouvrir de menu (exigé par les revues TikTok / Meta) */}
            <p className="mt-4 text-center text-xs text-slate-400 md:text-left">
              <Link to="/cgu" className="underline hover:text-ink">Conditions d'utilisation</Link>
              {" · "}
              <Link to="/confidentialite" className="underline hover:text-ink">Politique de confidentialité</Link>
            </p>
          </div>

          {/* Maquette de téléphone : aperçu du fil Moments (pur CSS) */}
          <div className="relative mx-auto w-[270px] md:w-[300px]">
            <div className="relative aspect-[9/19] overflow-hidden rounded-[2.75rem] bg-ink p-2.5 shadow-[0_30px_80px_-20px_rgba(244,37,106,0.45)]">
              <div className="relative h-full w-full overflow-hidden rounded-[2.2rem]">
                {/* Tant que l'image n'est pas connue/chargée : simple fond sombre
                    (celui du téléphone), puis fondu d'apparition de la bonne image. */}
                {heroImage && (
                  <img
                    key={heroImage}
                    src={heroImage}
                    alt="Un couple souriant"
                    onLoad={() => setHeroLoaded(heroImage)}
                    className={`h-full w-full object-cover transition-opacity duration-500 ${
                      heroLoaded === heroImage ? "opacity-100" : "opacity-0"
                    }`}
                  />
                )}
                <div className="absolute inset-0 bg-gradient-to-t from-black/70 via-transparent to-black/20" />
                <div className="absolute inset-x-0 top-4 flex justify-center gap-4 text-[11px] font-extrabold text-white/70">
                  <span>Près de moi</span><span className="text-white underline decoration-2 underline-offset-4">Pour toi</span><span>Matchs</span>
                </div>
                <div className="absolute bottom-16 right-2.5 flex flex-col items-center gap-3 text-white">
                  <span className="material-symbols-outlined icon-filled text-3xl text-primary drop-shadow">favorite</span>
                  <span className="material-symbols-outlined icon-filled text-3xl drop-shadow">chat_bubble</span>
                  <span className="material-symbols-outlined icon-filled text-3xl drop-shadow">redeem</span>
                </div>
                <div className="absolute bottom-5 left-4 right-14 text-white">
                  <p className="flex items-center gap-1 text-sm font-extrabold">
                    Kofi · 32 ans <span className="material-symbols-outlined icon-filled text-sm text-sky-400">verified</span>
                  </p>
                  <p className="text-[11px] text-white/80">Dimanche à Abidjan avec le sourire 🌅 #abidjan</p>
                </div>
              </div>
            </div>
            {/* Pastilles flottantes */}
            <div className="absolute -left-10 top-20 animate-[fade-in_0.6s_ease-out] rounded-2xl bg-white px-3.5 py-2.5 shadow-xl ring-1 ring-slate-100 md:-left-16">
              <p className="text-[11px] font-bold text-slate-400">Nouveau</p>
              <p className="text-sm font-extrabold text-brand">C'est un match ! 💘</p>
            </div>
            <div className="absolute -right-8 top-1/2 rounded-2xl bg-white px-3.5 py-2.5 shadow-xl ring-1 ring-slate-100 md:-right-14">
              <p className="flex items-center gap-1 text-sm font-extrabold">
                <span className="material-symbols-outlined icon-filled text-lg text-sky-500">verified</span> Identité vérifiée
              </p>
            </div>
            <div className="absolute -bottom-5 left-6 flex items-center gap-2 rounded-full bg-white px-4 py-2 shadow-xl ring-1 ring-slate-100">
              <span className="flex gap-1">
                {[0, 1, 2].map((d) => (
                  <span key={d} className="h-1.5 w-1.5 animate-typing-dot rounded-full bg-primary" style={{ animationDelay: `${d * 0.15}s` }} />
                ))}
              </span>
              <span className="text-xs font-bold text-slate-500">Awa est en train d'écrire…</span>
            </div>
          </div>
        </div>
      </section>

      {/* ---------------------------------------------------------------- */}
      {/* Compteurs en direct + IP du visiteur                              */}
      {/* ---------------------------------------------------------------- */}
      {stats && (
        <section className="mx-auto max-w-6xl px-5">
          <div className="grid grid-cols-3 divide-x divide-slate-100 rounded-3xl bg-white py-6 shadow-[0_4px_24px_rgba(18,6,11,0.06)] ring-1 ring-slate-100">
            <Counter value={stats.registered} label="Inscrits" icon="group" />
            <Counter value={stats.verified} label="Profils vérifiés" icon="verified" />
            <Counter value={stats.visits} label="Visites" icon="visibility" />
          </div>
          {stats.your_ip && (
            <p className="mt-3 flex items-center justify-center gap-1.5 text-xs font-semibold text-slate-400">
              <span className="material-symbols-outlined text-sm">lan</span>
              Votre adresse IP : <span className="font-mono text-slate-600">{stats.your_ip}</span>
            </p>
          )}
        </section>
      )}

      {/* ---------------------------------------------------------------- */}
      {/* Comment ça marche                                                 */}
      {/* ---------------------------------------------------------------- */}
      <section className="mx-auto max-w-6xl px-5 py-16">
        <SectionTitle kicker="Simple comme bonjour" title="Trois étapes pour faire de belles rencontres" />
        <div className="mt-10 grid gap-4 md:grid-cols-3">
          {STEPS.map((s) => (
            <div key={s.n} className="relative rounded-3xl bg-slate-50 p-6">
              <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-brand text-lg font-extrabold text-white shadow-lg shadow-primary/25">
                {s.n}
              </span>
              <p className="mt-4 text-lg font-extrabold">{s.title}</p>
              <p className="mt-1 text-sm leading-relaxed text-slate-500">{s.text}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ---------------------------------------------------------------- */}
      {/* Fonctionnalités (grille "bento")                                  */}
      {/* ---------------------------------------------------------------- */}
      <section id="fonctionnalites" className="scroll-mt-20 mx-auto max-w-6xl px-5 py-16">
        <SectionTitle kicker="Fonctionnalités" title="Tout pour se découvrir, vraiment" />
        <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map((f, i) => {
            // Avec une vidéo configurée, la carte « Moments » occupe toute la
            // largeur de la grille pour loger l'encart vidéo à côté du texte ;
            // la dernière carte s'élargit alors sur 2 colonnes (tablette) pour
            // ne pas rester seule sur sa ligne.
            const withVideo = f.big && momentsVideo;
            const span = withVideo
              ? "sm:col-span-2 lg:col-span-3"
              : momentsVideo && i === FEATURES.length - 1
                ? "sm:col-span-2 lg:col-span-1"
                : "";
            return (
              <div
                key={f.title}
                className={`group flex flex-col rounded-3xl bg-gradient-to-br ${f.tint} p-6 transition duration-300 hover:shadow-xl ${
                  withVideo ? "gap-6 md:flex-row md:items-center" : "hover:-translate-y-1"
                } ${f.big ? "ring-2 ring-primary/40" : ""} ${span}`}
              >
                {/* Texte de présentation (icône, titre, description, lien) */}
                <div className="flex flex-1 flex-col">
                  <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-white shadow-sm">
                    <span className="material-symbols-outlined icon-filled text-2xl text-primary">{f.icon}</span>
                  </span>
                  <div>
                    <p className="mt-5 text-lg font-extrabold">{f.title}</p>
                    <p className="mt-2 text-sm leading-relaxed text-slate-600">{f.text}</p>
                  </div>
                  {f.big && (
                    <Link to={primaryTo} className="mt-auto inline-flex items-center gap-1 pt-4 text-sm font-extrabold text-primary">
                      Découvrir les Moments <span className="material-symbols-outlined text-lg transition group-hover:translate-x-1">arrow_forward</span>
                    </Link>
                  )}
                </div>
                {/* Encart vidéo : sous le texte sur mobile, à côté à partir du format tablette */}
                {withVideo && <MomentsVideo src={momentsVideo.src} poster={momentsVideo.poster} />}
              </div>
            );
          })}
        </div>
      </section>

      {/* ---------------------------------------------------------------- */}
      {/* Confiance & sécurité                                              */}
      {/* ---------------------------------------------------------------- */}
      <section id="confiance" className="scroll-mt-20 mx-auto max-w-6xl px-5 py-16">
        <div className="overflow-hidden rounded-[2.5rem] bg-gradient-to-br from-primary to-sunset p-8 text-white md:p-14">
          <div className="grid items-center gap-10 md:grid-cols-2">
            <div>
              <p className="text-xs font-extrabold uppercase tracking-[0.2em] text-white/70">Confiance</p>
              <h2 className="mt-3 text-3xl font-extrabold leading-tight md:text-4xl">Ici, les profils sont réels. Et votre vie privée aussi.</h2>
              <p className="mt-4 text-white/85">
                Nous avons conçu beAuthentik pour que vous puissiez faire confiance aux personnes que vous rencontrez —
                et garder la main sur ce que vous montrez.
              </p>
            </div>
            <ul className="space-y-3">
              {[
                ["badge", "Vérification d'identité par IA + revue humaine"],
                ["blur_on", "Vidéos floutées, en clair sur votre accord uniquement"],
                ["flag", "Signalement en un clic, modération réactive"],
                ["favorite", "Match uniquement si l'intérêt est réciproque"],
                ["account_balance_wallet", "Paiement Mobile Money sécurisé"],
              ].map(([icon, text]) => (
                <li key={text} className="flex items-center gap-3 rounded-2xl bg-white/15 px-4 py-3 backdrop-blur">
                  <span className="material-symbols-outlined text-xl">{icon}</span>
                  <span className="text-sm font-bold">{text}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </section>

      {/* ---------------------------------------------------------------- */}
      {/* Tarifs                                                            */}
      {/* ---------------------------------------------------------------- */}
      <section id="tarifs" className="scroll-mt-20 mx-auto max-w-6xl px-5 py-16">
        <SectionTitle kicker="Tarifs" title="Commencez gratuitement, passez Premium quand vous voulez" />
        <p className="mx-auto mt-3 max-w-xl text-center text-sm text-slate-500">
          Sans engagement, sans renouvellement caché. Payez en Mobile Money, en FCFA.
        </p>

        <div className={`mt-12 grid items-stretch gap-5 sm:grid-cols-2 ${plans.length >= 3 ? "lg:grid-cols-4" : "lg:grid-cols-3"}`}>
          {/* Offre gratuite */}
          <PlanCard
            name="Découverte"
            price="0"
            period="pour toujours"
            features={FREE_FEATURES}
            cta="Commencer gratuitement"
            to={primaryTo}
          />
          {plans.map((p) => (
            <PlanCard
              key={p.id}
              name={p.name}
              price={fcfa(p.price_xof)}
              currency="FCFA"
              period={periodLabel(p.duration_days)}
              // Équivalent mensuel pour les formules longues : l'argument qui fait mouche.
              note={p.duration_days >= 60 ? `soit ${fcfa(Math.round(p.price_xof / (p.duration_days / 30)))} FCFA / mois` : null}
              badge={p.badge}
              savings={p.savings_pct}
              featured={p.featured}
              features={p.features}
              cta="Choisir cette formule"
              to={planTo}
            />
          ))}
        </div>
        <PaymentMethods className="mt-10" />
      </section>

      {/* ---------------------------------------------------------------- */}
      {/* FAQ                                                               */}
      {/* ---------------------------------------------------------------- */}
      <section id="faq" className="scroll-mt-20 mx-auto max-w-3xl px-5 py-16">
        <SectionTitle kicker="FAQ" title="Vos questions" />
        <div className="mt-8 space-y-3">
          {FAQ.map((item) => (
            <details key={item.q} className="group rounded-2xl bg-slate-50 px-5 py-4 open:bg-white open:shadow-lg open:ring-1 open:ring-slate-100">
              <summary className="flex cursor-pointer list-none items-center justify-between gap-4 font-bold">
                {item.q}
                <span className="material-symbols-outlined text-primary transition group-open:rotate-45">add</span>
              </summary>
              <p className="mt-3 text-sm leading-relaxed text-slate-500">{item.a}</p>
            </details>
          ))}
        </div>
      </section>

      {/* ---------------------------------------------------------------- */}
      {/* Appel final + pied de page                                        */}
      {/* ---------------------------------------------------------------- */}
      <section className="mx-auto max-w-6xl px-5 pb-16 pt-4">
        <div className="relative overflow-hidden rounded-[2.5rem] bg-ink px-8 py-14 text-center text-white">
          <div className="pointer-events-none absolute -left-20 -top-20 h-72 w-72 rounded-full bg-primary/40 blur-3xl" />
          <div className="pointer-events-none absolute -bottom-24 -right-10 h-72 w-72 rounded-full bg-sunset/40 blur-3xl" />
          <h2 className="relative text-3xl font-extrabold md:text-4xl">Votre prochaine belle histoire commence ici.</h2>
          <p className="relative mx-auto mt-3 max-w-md text-white/70">Inscription gratuite, en deux minutes.</p>
          <Link to={primaryTo} className="btn-primary relative mt-8 h-14 px-8 text-base">
            {primaryLabel}
            <span className="material-symbols-outlined">arrow_forward</span>
          </Link>
        </div>
      </section>

      <footer className="border-t border-slate-100">
        <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-3 px-5 py-8 text-sm text-slate-400 sm:flex-row">
          <span className="font-extrabold text-ink">
            be<span className="text-brand">Authentik</span>
          </span>
          <span>© {new Date().getFullYear()} beAuthentik — Rencontres authentiques</span>
          <div className="flex flex-wrap justify-center gap-4">
            <Link to="/connexion" className="hover:text-ink">Connexion</Link>
            <Link to="/inscription" className="hover:text-ink">Inscription</Link>
            {/* Pages légales publiques */}
            <Link to="/cgu" className="hover:text-ink">Conditions d'utilisation</Link>
            <Link to="/confidentialite" className="hover:text-ink">Confidentialité</Link>
          </div>
        </div>
      </footer>
    </div>
  );
}

function SectionTitle({ kicker, title }) {
  return (
    <div className="text-center">
      <p className="text-xs font-extrabold uppercase tracking-[0.2em] text-primary">{kicker}</p>
      <h2 className="mx-auto mt-3 max-w-2xl text-3xl font-extrabold leading-tight tracking-tight md:text-4xl">{title}</h2>
    </div>
  );
}

/**
 * Carte de tarif. La formule `featured` est mise en avant : contour en
 * dégradé, légère surélévation, bouton plein ; les autres restent sobres.
 */
function PlanCard({ name, price, currency, period, note, badge, savings, featured, features, cta, to }) {
  const card = (
    <div className={`relative flex h-full flex-col rounded-[1.75rem] bg-white p-6 ${featured ? "" : "ring-1 ring-slate-200"}`}>
      {badge && (
        <span
          className={`absolute -top-3 left-6 rounded-full px-3 py-1 text-[11px] font-extrabold ${
            featured ? "bg-brand text-white shadow-lg shadow-primary/30" : "bg-ink text-white"
          }`}
        >
          {badge}
        </span>
      )}
      <p className="text-sm font-extrabold uppercase tracking-wider text-slate-400">{name}</p>
      <p className="mt-3 flex items-baseline gap-1.5">
        <span className={`text-4xl font-extrabold tracking-tight ${featured ? "text-brand" : ""}`}>{price}</span>
        {currency && <span className="text-sm font-bold text-slate-400">{currency}</span>}
      </p>
      <p className="text-sm font-semibold text-slate-400">{period}</p>
      {(note || savings) && (
        <p className="mt-2 flex flex-wrap items-center gap-2 text-xs font-bold">
          {savings ? <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-emerald-600">−{savings} %</span> : null}
          {note && <span className="text-slate-500">{note}</span>}
        </p>
      )}
      <ul className="mt-6 flex-1 space-y-2.5">
        {features.map((f) => (
          <li key={f} className="flex items-start gap-2 text-sm text-slate-600">
            <span className={`material-symbols-outlined icon-filled mt-px text-lg ${featured ? "text-primary" : "text-emerald-500"}`}>check_circle</span>
            {f}
          </li>
        ))}
      </ul>
      <Link to={to} className={`${featured ? "btn-primary" : "btn-ghost"} mt-7 w-full`}>
        {cta}
      </Link>
    </div>
  );

  // Contour en dégradé pour la formule vedette (padding de 2 px coloré).
  return featured ? (
    <div className="rounded-[1.9rem] bg-gradient-to-br from-primary to-sunset p-[2px] shadow-2xl shadow-primary/20 lg:-translate-y-3">{card}</div>
  ) : (
    card
  );
}

/** Compteur de la bande de statistiques (chiffre au format français). */
function Counter({ value, label, icon }) {
  return (
    <div className="flex flex-col items-center gap-1 px-2 text-center">
      <span className="material-symbols-outlined icon-filled text-xl text-primary">{icon}</span>
      <span className="text-2xl font-extrabold tracking-tight md:text-3xl">{new Intl.NumberFormat("fr-FR").format(value || 0)}</span>
      <span className="text-[11px] font-bold uppercase tracking-wider text-slate-400">{label}</span>
    </div>
  );
}
