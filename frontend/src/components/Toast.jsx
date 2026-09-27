import { useCallback, useRef, useState } from "react";

// Petit message éphémère en haut de l'écran ("Lien copié !", "Vidéo
// publiée 🎉"…). Usage :
//   const [toast, showToast] = useToast();
//   showToast("Lien copié");  …  <Toast message={toast} />
export function useToast(durationMs = 2200) {
  const [message, setMessage] = useState("");
  const timer = useRef(null);
  const show = useCallback((text) => {
    clearTimeout(timer.current);
    setMessage(text);
    timer.current = setTimeout(() => setMessage(""), durationMs);
  }, [durationMs]);
  return [message, show];
}

export default function Toast({ message }) {
  if (!message) return null;
  return (
    <div className="pointer-events-none fixed inset-x-0 top-4 z-[70] flex justify-center px-4">
      <div className="animate-fade-in rounded-full bg-ink/90 px-5 py-2.5 text-sm font-semibold text-white shadow-xl backdrop-blur">
        {message}
      </div>
    </div>
  );
}
