import { useState } from "react";

// ============================================================================
// Champ MOT DE PASSE avec pictogramme « œil » (règle permanente du propriétaire,
// lot 46) : un clic sur l'œil affiche la saisie en clair, un second clic la
// masque de nouveau. Remplace tel quel un <input type="password" … /> : toutes
// les propriétés (value, onChange, required, className, autoComplete…) sont
// transmises au champ.
// ============================================================================
export default function ChampMotDePasse({ className = "", ...props }) {
  // false = saisie masquée (••••), true = saisie visible
  const [visible, setVisible] = useState(false);
  return (
    <span className="relative block w-full">
      {/* pr-10 : place réservée à droite pour le bouton œil */}
      <input {...props} type={visible ? "text" : "password"} className={`${className} w-full pr-10`} />
      <button
        type="button"
        onClick={() => setVisible((v) => !v)}
        aria-label={visible ? "Masquer le mot de passe" : "Afficher le mot de passe"}
        title={visible ? "Masquer le mot de passe" : "Afficher le mot de passe"}
        tabIndex={-1}
        className="absolute inset-y-0 right-0 flex w-10 items-center justify-center text-slate-400 hover:text-slate-700"
      >
        <span className="material-symbols-outlined text-[20px]">{visible ? "visibility_off" : "visibility"}</span>
      </button>
    </span>
  );
}
