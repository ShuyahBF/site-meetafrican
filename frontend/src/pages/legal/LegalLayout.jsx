import { useEffect } from "react";
import { Link } from "react-router-dom";

// Contact officiel de l'éditeur (SAWALI SMART SYSTEMS), affiché dans les pages
// légales. Une seule constante pour les changer partout.
export const CONTACT_EMAIL = "contact@sawalismartsystems.com";
export const CONTACT_TELEPHONE = "+226 25 65 81 65";
// Date de la version en vigueur (identique à TERMS_VERSION côté serveur,
// backend/routes/auth.py — enregistrée à l'inscription de chaque membre).
export const LEGAL_VERSION_DATE = "28 septembre 2026";

/**
 * Mise en page commune des pages légales : fond blanc, largeur de lecture
 * confortable, sommaire cliquable, liens croisés entre les deux pages.
 */
export default function LegalLayout({ title, documentTitle, intro, sections, other }) {
  // Titre de l'onglet : EXACTEMENT « beAuthentik Privacy Policy » / « beAuthentik
  // Terms of Service » (vérifié par les revues d'applications TikTok, Meta…)
  useEffect(() => {
    if (!documentTitle) return undefined;
    document.title = documentTitle;
    return () => { document.title = "beAuthentik"; };
  }, [documentTitle]);

  return (
    <div className="min-h-screen bg-white font-display text-ink">
      <header className="sticky top-0 z-10 border-b border-slate-100 bg-white/90 backdrop-blur">
        <div className="mx-auto flex max-w-3xl items-center justify-between px-5 py-4">
          <Link to="/" className="text-xl font-extrabold tracking-tight">
            be<span className="text-brand">Authentik</span>
          </Link>
          <Link to={other.to} className="text-sm font-bold text-primary">{other.label}</Link>
        </div>
      </header>

      <main className="mx-auto max-w-3xl px-5 pb-20 pt-10">
        {/* Icône + nom de l'app en tête de page (demandé par les revues d'applications) */}
        <div className="mb-6 flex items-center gap-3">
          <img src="/icone-beauthentik.svg" alt="beAuthentik app icon" className="h-12 w-12 rounded-2xl" />
          <span className="text-lg font-extrabold">beAuthentik</span>
        </div>
        {documentTitle && <p className="text-sm font-bold uppercase tracking-widest text-primary">{documentTitle}</p>}
        <h1 className="text-3xl font-extrabold leading-tight md:text-4xl">{title}</h1>
        <p className="mt-2 text-sm text-slate-400">Version en vigueur au {LEGAL_VERSION_DATE}</p>
        <p className="mt-6 leading-relaxed text-slate-600">{intro}</p>

        {/* Sommaire */}
        <nav className="mt-8 rounded-2xl bg-slate-50 p-5">
          <p className="text-xs font-extrabold uppercase tracking-widest text-slate-400">Sommaire</p>
          <ol className="mt-3 grid gap-1.5 text-sm sm:grid-cols-2">
            {sections.map((s, i) => (
              <li key={s.id}>
                <a href={`#${s.id}`} className="font-semibold text-slate-700 hover:text-primary">
                  {i + 1}. {s.title}
                </a>
              </li>
            ))}
          </ol>
        </nav>

        {sections.map((s, i) => (
          <section key={s.id} id={s.id} className="scroll-mt-24 pt-10">
            <h2 className="text-xl font-extrabold">
              {i + 1}. {s.title}
            </h2>
            <div className="mt-3 space-y-3 leading-relaxed text-slate-600 [&_li]:ml-5 [&_li]:list-disc [&_strong]:text-ink">
              {s.body}
            </div>
          </section>
        ))}

        <p className="mt-14 rounded-2xl bg-primary/5 p-5 text-sm text-slate-600">
          Une question ? Écrivez-nous à{" "}
          <a href={`mailto:${CONTACT_EMAIL}`} className="font-bold text-primary">{CONTACT_EMAIL}</a> ou appelez le{" "}
          <a href="tel:+22625658165" className="font-bold text-primary">{CONTACT_TELEPHONE}</a>.
          <br />beAuthentik est édité par SAWALI SMART SYSTEMS, Ouagadougou, Burkina Faso.
        </p>
      </main>
    </div>
  );
}
