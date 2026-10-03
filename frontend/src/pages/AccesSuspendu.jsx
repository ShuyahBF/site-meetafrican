import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { apiClient } from "@/lib/api";
import MentionVersion from "@/components/MentionVersion";
import { CONTACT_EMAIL, CONTACT_TELEPHONE } from "@/pages/legal/LegalLayout";

// ============================================================================
// PAGE « ACCÈS MOMENTANÉMENT SUSPENDU » (lot 47)
// ============================================================================
// Affichée quand le serveur refuse l'accès parce que le super-administrateur a
// bloqué le compte ou l'adresse IP du visiteur (onglet « Usage » du back-office).
// Le site y arrive automatiquement (voir lib/api.js : réponse 403 « acces_suspendu »).
//
// Ton volontairement courtois, en français, SANS détail technique (ni adresse IP,
// ni motif) : on invite simplement à contacter l'Administrateur pour réclamer son
// accès ou contester la décision.
//
// Contact : celui réglé par le super-administrateur dans l'onglet « Usage »
// (e-mail, WhatsApp) ; à défaut, le contact officiel des pages légales.
// ============================================================================
export default function AccesSuspendu() {
  // Contact réglé par l'administrateur ({ email, whatsapp }, vides si non réglés)
  const [contact, setContact] = useState({ email: "", whatsapp: "" });

  useEffect(() => {
    // Route publique : fonctionne même sans connexion
    apiClient.get("/acces-suspendu/contact").then((r) => setContact(r.data)).catch(() => {});
  }, []);

  const email = contact.email || CONTACT_EMAIL;
  // Lien WhatsApp : seulement les chiffres du numéro (format international attendu par wa.me)
  const whatsappChiffres = (contact.whatsapp || "").replace(/\D/g, "");

  return (
    <div className="flex min-h-screen w-full items-center justify-center bg-background-light px-4 py-10 font-display dark:bg-background-dark">
      <div className="w-full max-w-md rounded-3xl bg-white p-6 text-center shadow-xl ring-1 ring-slate-100 dark:bg-slate-900 dark:ring-white/10">
        {/* Logo et titre */}
        <img src="/icone-beauthentik.svg" alt="beAuthentik" className="mx-auto h-16 w-16" />
        <span className="material-symbols-outlined mt-4 text-5xl text-amber-500" aria-hidden="true">pause_circle</span>
        <h1 className="mt-2 text-2xl font-bold text-slate-900 dark:text-white">Accès momentanément suspendu</h1>

        {/* Message courtois */}
        <p className="mt-4 text-sm leading-relaxed text-slate-600 dark:text-slate-300">
          Bonjour, l'accès à beAuthentik est momentanément suspendu pour votre compte ou depuis votre connexion.
        </p>
        <p className="mt-3 text-sm leading-relaxed text-slate-600 dark:text-slate-300">
          Si vous pensez qu'il s'agit d'une erreur, ou pour réclamer votre accès ou contester cette décision,
          nous vous invitons à contacter l'Administrateur : votre demande sera examinée avec attention.
        </p>

        {/* Moyens de contact de la plateforme */}
        <div className="mt-5 space-y-2 rounded-2xl bg-slate-50 p-4 text-sm dark:bg-white/5">
          <p className="font-semibold text-slate-700 dark:text-slate-200">Contacter l'Administrateur</p>
          <a href={`mailto:${email}`} className="flex items-center justify-center gap-2 font-semibold text-primary">
            <span className="material-symbols-outlined text-[20px]" aria-hidden="true">mail</span>
            {email}
          </a>
          {whatsappChiffres ? (
            <a href={`https://wa.me/${whatsappChiffres}`} target="_blank" rel="noreferrer"
               className="flex items-center justify-center gap-2 font-semibold text-emerald-600">
              <span className="material-symbols-outlined text-[20px]" aria-hidden="true">chat</span>
              WhatsApp : {contact.whatsapp}
            </a>
          ) : (
            <a href={`tel:${CONTACT_TELEPHONE.replace(/\s/g, "")}`} className="flex items-center justify-center gap-2 font-semibold text-primary">
              <span className="material-symbols-outlined text-[20px]" aria-hidden="true">call</span>
              {CONTACT_TELEPHONE}
            </a>
          )}
        </div>

        <p className="mt-4 text-sm text-slate-500 dark:text-slate-400">Merci de votre compréhension.</p>

        <Link to="/" className="mt-5 inline-block text-sm font-semibold text-primary underline">
          Revenir à l'accueil
        </Link>

        {/* Version et lot (règle permanente) */}
        <MentionVersion className="mt-6" />
      </div>
    </div>
  );
}
