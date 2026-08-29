import { Link } from "react-router-dom";

const SLIDES = [
  { icon: "swipe", title: "Découvrez des profils", text: "Trouvez facilement des personnes compatibles à proximité." },
  { icon: "chat", title: "Connectez en sécurité", text: "Discutez en toute confiance grâce à notre chat sécurisé." },
  { icon: "celebration", title: "Vivez de vrais moments", text: "L'application est conçue pour mener à de vraies rencontres." },
];

export default function Welcome() {
  return (
    <div className="dark relative flex min-h-screen w-full flex-col overflow-x-hidden bg-background-light font-display dark:bg-background-dark">
      <div className="relative w-full">
        <div className="flex min-h-[40vh] w-full flex-col items-center justify-center bg-[#181113] md:min-h-[50vh]">
          <span className="material-symbols-outlined text-5xl text-white">favorite</span>
        </div>
      </div>

      <h1 className="px-4 pb-3 pt-8 text-center font-display text-3xl font-bold leading-tight tracking-tight text-slate-900 dark:text-white md:text-4xl">
        La rencontre commence ici
      </h1>

      <div className="flex-grow">
        <div className="flex gap-4 overflow-x-auto px-4 py-4 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
          {SLIDES.map((s) => (
            <div key={s.title} className="flex h-full w-64 flex-shrink-0 flex-col gap-4 rounded-lg">
              <div className="flex aspect-square w-full items-center justify-center rounded-xl bg-primary/10">
                <span className="material-symbols-outlined text-6xl text-primary">{s.icon}</span>
              </div>
              <div>
                <p className="text-base font-bold leading-normal text-slate-800 dark:text-white">{s.title}</p>
                <p className="text-sm font-normal leading-normal text-slate-500 dark:text-slate-400">{s.text}</p>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="flex w-full flex-row items-center justify-center gap-2 py-5">
        <div className="h-2 w-6 rounded-full bg-primary" />
        <div className="h-2 w-2 rounded-full bg-primary/20" />
        <div className="h-2 w-2 rounded-full bg-primary/20" />
      </div>

      <div className="sticky bottom-0 flex justify-center bg-background-light pb-6 pt-2 dark:bg-background-dark">
        <div className="flex w-full max-w-[480px] flex-1 flex-col items-stretch gap-3 px-4">
          <Link
            to="/inscription"
            className="flex h-14 w-full min-w-[84px] cursor-pointer items-center justify-center overflow-hidden rounded-full bg-primary px-5 text-base font-bold leading-normal tracking-[0.015em] text-white"
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
