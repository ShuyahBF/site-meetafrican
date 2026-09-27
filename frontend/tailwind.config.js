/** @type {import('tailwindcss').Config} */
export default {
  // Thème sombre désactivé en pratique : <html> ne porte plus la classe
  // "dark" (exigence : fond BLANC pour toutes les fenêtres). Les variantes
  // dark: restées dans le code sont donc simplement ignorées.
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        primary: "#f4256a",
        // Accents du dégradé "coucher de soleil" (rose -> orange), signature
        // visuelle jeune de l'app : boutons principaux, bouton ✚, badges.
        sunset: "#ff7a45",
        violet: "#8b5cf6",
        // Fond des pages : blanc pur (obligation de la charte).
        "background-light": "#ffffff",
        "background-dark": "#221016",
        ink: "#12060b", // texte principal, presque noir teinté de rose
      },
      fontFamily: {
        display: ["Plus Jakarta Sans", "sans-serif"],
      },
      borderRadius: {
        DEFAULT: "1rem",
        lg: "1.5rem",
        xl: "2rem",
        full: "9999px",
      },
      // Micro-animations qui donnent le côté ludique (façon TikTok).
      keyframes: {
        // Cœur géant du double-tap : grossit, penche, puis s'envole.
        "heart-burst": {
          "0%": { transform: "translate(-50%, -50%) scale(0) rotate(-15deg)", opacity: "0" },
          "15%": { transform: "translate(-50%, -50%) scale(1.25) rotate(-15deg)", opacity: "1" },
          "30%": { transform: "translate(-50%, -50%) scale(0.95) rotate(-15deg)", opacity: "1" },
          "100%": { transform: "translate(-50%, -160%) scale(1.4) rotate(-15deg)", opacity: "0" },
        },
        // Petit rebond d'un bouton qu'on vient d'activer (J'aime…).
        pop: {
          "0%": { transform: "scale(1)" },
          "40%": { transform: "scale(1.35)" },
          "100%": { transform: "scale(1)" },
        },
        // Tiroirs (commentaires, options) qui montent du bas de l'écran.
        "slide-up": {
          "0%": { transform: "translateY(100%)" },
          "100%": { transform: "translateY(0)" },
        },
        "fade-in": { "0%": { opacity: "0" }, "100%": { opacity: "1" } },
        // Points de l'indicateur "en train d'écrire…".
        "typing-dot": {
          "0%, 60%, 100%": { transform: "translateY(0)", opacity: "0.4" },
          "30%": { transform: "translateY(-4px)", opacity: "1" },
        },
        // Disque qui tourne (avatar de l'auteur en bas à droite, clin d'œil
        // au disque "son" de TikTok).
        "spin-slow": { "0%": { transform: "rotate(0deg)" }, "100%": { transform: "rotate(360deg)" } },
        // Confettis de l'écran "C'est un match !".
        confetti: {
          "0%": { transform: "translateY(-10vh) rotate(0deg)", opacity: "1" },
          "100%": { transform: "translateY(110vh) rotate(720deg)", opacity: "0.9" },
        },
      },
      animation: {
        "heart-burst": "heart-burst 0.9s ease-out forwards",
        pop: "pop 0.35s ease-out",
        "slide-up": "slide-up 0.28s cubic-bezier(0.22, 1, 0.36, 1)",
        "fade-in": "fade-in 0.2s ease-out",
        "typing-dot": "typing-dot 1.2s infinite",
        "spin-slow": "spin-slow 6s linear infinite",
        confetti: "confetti 2.8s ease-in forwards",
      },
    },
  },
  plugins: [],
};
