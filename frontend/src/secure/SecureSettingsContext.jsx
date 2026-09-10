import { createContext, useContext, useEffect, useState } from "react";

// Réglages globaux de la zone /secure (thème + visibilité des notes techniques
// VIDAL), partagés par les 3 maquettes via ce contexte plutôt que d'être
// re-déclarés à chaque route dans App.jsx. Persistés en localStorage pour ne
// pas les perdre en changeant de page ou en rafraîchissant.
const SecureSettingsContext = createContext(null);

function readStored(key, fallback) {
  try {
    return localStorage.getItem(key) ?? fallback;
  } catch {
    return fallback;
  }
}

export function SecureSettingsProvider({ children }) {
  const [theme, setTheme] = useState(() => readStored("secure-theme", "light"));
  const [vidalNotes, setVidalNotes] = useState(() => readStored("secure-vidal-notes", "off") === "on");

  useEffect(() => {
    try {
      localStorage.setItem("secure-theme", theme);
    } catch {
      /* stockage indisponible (navigation privée...) : le réglage reste actif pour la session */
    }
  }, [theme]);

  useEffect(() => {
    try {
      localStorage.setItem("secure-vidal-notes", vidalNotes ? "on" : "off");
    } catch {
      /* idem */
    }
  }, [vidalNotes]);

  return (
    <SecureSettingsContext.Provider value={{ theme, setTheme, vidalNotes, setVidalNotes }}>
      {children}
    </SecureSettingsContext.Provider>
  );
}

export function useSecureSettings() {
  const ctx = useContext(SecureSettingsContext);
  if (!ctx) throw new Error("useSecureSettings must be used within SecureSettingsProvider");
  return ctx;
}
