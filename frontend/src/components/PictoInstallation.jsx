// Pictogrammes de la page d'installation (dessinés ici, aucune image à charger : ils s'affichent même sans connexion).
// Chaque pictogramme représente EXACTEMENT ce que l'utilisateur doit chercher à l'écran de son téléphone.
// La couleur suit celle du texte (currentColor). Les noms correspondent aux « icone » de lib/installation.js.
const TRAIT = { fill: "none", stroke: "currentColor", strokeWidth: 2.2, strokeLinecap: "round", strokeLinejoin: "round" };

const DESSINS = {
  // Trois points verticaux ⋮ (menu de Chrome, Firefox)
  "menu-points": (<><circle cx="16" cy="7" r="2.2" fill="currentColor" /><circle cx="16" cy="16" r="2.2" fill="currentColor" /><circle cx="16" cy="25" r="2.2" fill="currentColor" /></>),
  // Trois traits ≡ (menu de Samsung Internet)
  "menu-lignes": (<g {...TRAIT}><path d="M6 9h20M6 16h20M6 23h20" /></g>),
  // Bouton « Partager » de Safari : un carré ouvert avec une flèche vers le haut
  partager: (<g {...TRAIT}><path d="M16 21V5M10.5 10.5 16 5l5.5 5.5" /><path d="M10 14H8.5A2.5 2.5 0 0 0 6 16.5v8A2.5 2.5 0 0 0 8.5 27h15a2.5 2.5 0 0 0 2.5-2.5v-8a2.5 2.5 0 0 0-2.5-2.5H22" /></g>),
  // Écran d'accueil : un téléphone avec une grille d'icônes dont une en plus (+)
  "ecran-accueil": (<g {...TRAIT}><rect x="8" y="3" width="16" height="26" rx="3" /><rect x="11.5" y="7" width="4" height="4" rx="1" /><rect x="17" y="7" width="4" height="4" rx="1" /><rect x="11.5" y="13" width="4" height="4" rx="1" /><path d="M19 15v6M16 18h6" /></g>),
  // Installer : une flèche qui descend dans un téléphone
  installer: (<g {...TRAIT}><rect x="8" y="3" width="16" height="26" rx="3" /><path d="M16 9v10M12 15.5l4 4 4-4" /><path d="M13 24.5h6" /></g>),
  // Navigateur : une boussole
  navigateur: (<g {...TRAIT}><circle cx="16" cy="16" r="11" /><path d="m20.5 11.5-2.8 6.2-6.2 2.8 2.8-6.2 6.2-2.8Z" /></g>),
  // Copier : deux feuilles
  copier: (<g {...TRAIT}><rect x="11" y="11" width="15" height="16" rx="2.5" /><path d="M21 11V8.5A2.5 2.5 0 0 0 18.5 6h-10A2.5 2.5 0 0 0 6 8.5v13A2.5 2.5 0 0 0 8.5 24H11" /></g>),
};

export default function PictoInstallation({ nom, taille = 32, className = "" }) {
  const dessin = DESSINS[nom];
  if (!dessin) return null;
  // aria-hidden : le texte de l'étape dit déjà la même chose pour les lecteurs d'écran
  return <svg viewBox="0 0 32 32" width={taille} height={taille} aria-hidden="true" className={className}>{dessin}</svg>;
}
