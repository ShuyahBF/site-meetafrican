import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { apiClient } from "@/lib/api";

const DEFAULT_HERO_IMAGE = "/images/hero-couple.jpg";

// Trois bénéfices réels de l'app (pas des promesses en l'air : chaque item
// correspond à une fonctionnalité déjà implémentée côté backend), présentés
// façon "pourquoi nous choisir" plutôt que le carrousel générique d'avant.
const FEATURES = [
  {
    icon: "verified_user",
    title: "Profils vérifiés",
    text: "Chaque pièce d'identité est contrôlée avant validation du profil, pour une communauté plus sûre.",
  },
  {
    icon: "favorite",
    title: "Des rencontres qui comptent",
    text: "Un match ne se fait que si l'intérêt est réciproque — fini les messages sans réponse.",
  },
  {
    icon: "play_circle",
    title: "Des Moments en vidéo",
    text: "Découvrez les gens tels qu'ils sont, en vidéo : un double-tap pour aimer, un match pour discuter en direct.",
  },
];

export default function Welcome() {
  // Image modifiable par l'admin (Paramètres > Apparence de la page
  // d'accueil) sans redéploiement ; repli sur l'image embarquée par défaut
  // tant que rien n'a été réglé.
  const [heroImage, setHeroImage] = useState(DEFAULT_HERO_IMAGE);

  useEffect(() => {
    apiClient
      .get("/appearance")
      .then((r) => {
        if (r.data?.hero_image_url) setHeroImage(r.data.hero_image_url);
      })
      .catch(() => {});
  }, []);

  return (
    <div className="relative flex min-h-screen w-full flex-col overflow-x-hidden bg-background-light font-display dark:bg-background-dark">
      {/* Barre de marque minimale — juste le wordmark, pas de navigation :
          cette page n'a que deux destinations (inscription / connexion),
          déjà mises en avant plus bas. */}
      <header className="flex items-center justify-center px-4 py-5">
        <span className="text-xl font-extrabold tracking-tight text-ink">
          b<span className="text-brand">Authentik</span>
        </span>
      </header>

      {/* Hero : photo + dégradé pour garder le texte lisible par-dessus,
          quel que soit le contenu de l'image. */}
      <div className="relative w-full">
        <div className="relative h-[46vh] w-full overflow-hidden md:h-[54vh]">
          <img
            src={heroImage}
            alt="Un couple souriant"
            className="h-full w-full object-cover"
          />
          <div className="absolute inset-0 bg-gradient-to-t from-black/75 via-black/25 to-transparent" />
        </div>

        {/* Titre posé EN BAS de la photo (lisible grâce au dégradé sombre),
            la suite de la page restant sur fond blanc. */}
        <div className="absolute inset-x-0 bottom-6 px-4 text-center">
          <h1 className="font-display text-3xl font-extrabold leading-tight tracking-tight text-white drop-shadow-sm md:text-5xl">
            La rencontre commence ici
          </h1>
          <p className="mx-auto mt-3 max-w-md text-sm leading-relaxed text-white/90 md:text-base">
            La plateforme pensée pour les Africains qui veulent rencontrer,
            échanger et construire une vraie relation — où qu'ils soient.
          </p>
        </div>
      </div>

      {/* Bénéfices — grille de cartes, plus lisible qu'un carrousel horizontal
          qu'une partie du contenu reste hors champ sans indice visuel. */}
      <div className="mx-auto grid w-full max-w-4xl grid-cols-1 gap-4 px-4 py-10 sm:grid-cols-3">
        {FEATURES.map((f) => (
          <div
            key={f.title}
            className="flex flex-col items-center gap-3 rounded-xl bg-white p-6 text-center shadow-sm ring-1 ring-black/5 dark:bg-white/5 dark:ring-white/10"
          >
            <div className="flex h-14 w-14 items-center justify-center rounded-full bg-primary/10">
              <span className="material-symbols-outlined text-3xl text-primary">{f.icon}</span>
            </div>
            <p className="text-base font-bold text-slate-900 dark:text-white">{f.title}</p>
            <p className="text-sm leading-relaxed text-slate-500 dark:text-slate-400">{f.text}</p>
          </div>
        ))}
      </div>

      <div className="flex-grow" />

      <div className="sticky bottom-0 flex justify-center bg-background-light pb-6 pt-4 dark:bg-background-dark">
        <div className="flex w-full max-w-[480px] flex-1 flex-col items-stretch gap-3 px-4">
          <Link
            to="/inscription"
            className="btn-primary h-14 w-full text-base"
          >
            Créer un compte
          </Link>
          <Link
            to="/connexion"
            className="flex h-14 w-full min-w-[84px] cursor-pointer items-center justify-center overflow-hidden rounded-full bg-transparent px-5 text-base font-bold leading-normal tracking-[0.015em] text-slate-800 hover:bg-primary/10 dark:text-white"
          >
            Se connecter
          </Link>
        </div>
      </div>
    </div>
  );
}
