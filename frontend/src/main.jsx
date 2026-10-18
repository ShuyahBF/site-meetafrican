import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'
// Règle 9 — Ctrl + Espace / double-clic : reprendre le texte par défaut (gris) d'un champ pour le modifier
import { installerValeurParDefaut } from "./lib/valeurParDefaut";

installerValeurParDefaut();

// Application installable : le « service worker » est enregistré dès l'ouverture du site (condition d'installation sur Android)
// et affiche la page « Pas de connexion » quand Internet manque.
if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => navigator.serviceWorker.register("/sw.js").catch(() => {}));
}

// Garde l'invitation d'installation de Chrome pour le bouton « Installer l'application » (connexion, réglages)
window.addEventListener("beforeinstallprompt", (e) => { e.preventDefault(); window.__baInvite = e; window.dispatchEvent(new Event("ba-invite")); });

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
