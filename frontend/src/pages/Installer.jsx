import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import PictoInstallation from "@/components/PictoInstallation";
import { detecterEnvironnement, estInstallee, guideInstallation } from "@/lib/installation";

// ============================================================================
// PAGE D'INSTALLATION de beAuthentik — PUBLIQUE (aucune connexion requise) : /installer
// ============================================================================
// Pensée pour une personne peu familière avec la technologie, qui reçoit souvent le lien par WhatsApp :
//  - un seul grand bouton quand le navigateur sait installer en un geste (Chrome, Edge, Samsung Internet…) ;
//  - sinon 3 étapes illustrées, adaptées au téléphone et au navigateur reconnus (lib/installation.js, testé) ;
//  - lien ouvert dans Facebook / Instagram / TikTok… : on explique d'abord comment l'ouvrir dans le vrai navigateur ;
//  - déjà installée : on le dit et on propose de l'ouvrir ;
//  - boutons « Copier le lien » et « Envoyer par WhatsApp » pour aider un proche.
// L'invitation d'installation de Chrome (« beforeinstallprompt ») est gardée par main.jsx dans window.__baInvite
// (l'événement « ba-invite » prévient les composants qu'elle est arrivée).
// ============================================================================
const NOM_APP = "beAuthentik";
const LIEN = `${window.location.origin}/installer`;

export default function Installer() {
  const [invite, setInvite] = useState(() => window.__baInvite || null);
  const [installee, setInstallee] = useState(() => estInstallee(window));
  const [copie, setCopie] = useState(false);

  // Identité du navigateur et étapes à montrer (recalculées quand l'invitation d'installation arrive)
  const env = useMemo(() => detecterEnvironnement(navigator.userAgent, { pointsTactiles: navigator.maxTouchPoints }), []);
  const guide = useMemo(() => guideInstallation(env, { nomApp: NOM_APP, invitePrete: !!invite, ipad: /iPad/.test(navigator.userAgent) || (env.systeme === "ios" && /Macintosh/.test(navigator.userAgent)) }), [env, invite]);

  useEffect(() => {
    const surInvite = () => setInvite(window.__baInvite || null);
    const surInstallation = () => { window.__baInvite = null; setInvite(null); setInstallee(true); };
    window.addEventListener("ba-invite", surInvite);
    window.addEventListener("appinstalled", surInstallation);
    return () => { window.removeEventListener("ba-invite", surInvite); window.removeEventListener("appinstalled", surInstallation); };
  }, []);

  // Installation en un geste (Chrome, Edge, Samsung Internet…)
  const installer = async () => {
    if (!invite) return;
    invite.prompt();
    try { await invite.userChoice; } catch { /* choix ignoré */ }
    window.__baInvite = null; setInvite(null);
  };

  // Copie du lien (repli : fenêtre de saisie si le navigateur refuse)
  const copier = async () => {
    try { await navigator.clipboard.writeText(LIEN); setCopie(true); setTimeout(() => setCopie(false), 3000); }
    catch { window.prompt("Copiez ce lien :", LIEN); }
  };
  const partager = async () => {
    if (navigator.share) { try { await navigator.share({ title: `Installer ${NOM_APP}`, text: `Installez ${NOM_APP} sur votre téléphone :`, url: LIEN }); } catch { /* annulé */ } }
  };
  const lienWhatsapp = `https://wa.me/?text=${encodeURIComponent(`Installez ${NOM_APP} sur votre téléphone : ${LIEN}`)}`;

  return (
    <div className="min-h-[100dvh] bg-white font-display text-ink">
      <header className="flex items-center gap-3 px-4 pb-2 pt-5">
        <Link to="/" aria-label="Retour à l'accueil" className="flex h-10 w-10 items-center justify-center rounded-full hover:bg-slate-50">
          <span className="material-symbols-outlined">arrow_back</span>
        </Link>
        <img src="/icone-beauthentik.svg" alt={NOM_APP} className="h-10 w-10" />
        <span className="text-lg font-extrabold">{NOM_APP}</span>
      </header>

      <main className="mx-auto w-full max-w-lg space-y-5 px-4 pb-10 pt-2">
        <div>
          <h1 className="text-2xl font-extrabold">Installer {NOM_APP} sur votre téléphone</h1>
          <p className="mt-1 text-base text-slate-600">Gratuit, rapide, sans passer par le Play Store. Aucune place à libérer : l'application est très légère.</p>
        </div>

        {/* Déjà installée */}
        {installee ? (
          <section className="card space-y-3 p-5" data-testid="installee">
            <p className="text-lg font-bold text-green-700">✅ {NOM_APP} est déjà installée sur cet appareil.</p>
            <Link to="/" className="btn-primary w-full text-lg">Ouvrir {NOM_APP}</Link>
          </section>
        ) : (
          <section className="card space-y-4 p-5" data-testid="guide-installation">
            <h2 className="text-lg font-extrabold">{guide.titre}</h2>
            <p className="text-base text-slate-700">{guide.intro}</p>

            {/* Un seul geste */}
            {guide.mode === "direct" && (
              <button type="button" onClick={installer} className="btn-primary h-14 w-full text-xl" data-testid="bouton-installer">Installer {NOM_APP}</button>
            )}

            {/* Étapes illustrées */}
            {guide.etapes.length > 0 && (
              <ol className="space-y-3">
                {guide.etapes.map((etape, i) => (
                  <li key={etape.texte} className="flex items-start gap-3 rounded-2xl border border-slate-200 bg-white p-3">
                    <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-primary text-lg font-bold text-white" aria-hidden="true">{i + 1}</span>
                    <p className="flex-1 pt-1 text-base">{etape.texte}</p>
                    <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-ink text-white"><PictoInstallation nom={etape.icone} taille={28} /></span>
                  </li>
                ))}
              </ol>
            )}

            {guide.conseil && <p className="rounded-2xl bg-slate-50 p-3 text-sm text-slate-700">💡 {guide.conseil}</p>}
          </section>
        )}

        {/* Aider un proche / changer de navigateur */}
        <section className="card space-y-3 p-5">
          <h2 className="text-lg font-extrabold">Envoyer ce lien</h2>
          <div className="flex flex-wrap gap-2">
            <button type="button" onClick={copier} className="btn-ghost" data-testid="copier-lien">{copie ? "✅ Lien copié" : "📋 Copier le lien"}</button>
            <a href={lienWhatsapp} target="_blank" rel="noreferrer" className="btn-ghost">💬 Envoyer par WhatsApp</a>
            {navigator.share && <button type="button" onClick={partager} className="btn-ghost">📤 Partager…</button>}
          </div>
          {env.systeme === "ordinateur" && <p className="text-sm text-slate-600">Ouvrez ce lien sur votre téléphone pour installer l'application.</p>}
        </section>

        {/* Questions fréquentes */}
        <section className="card space-y-3 p-5 text-sm">
          <h2 className="text-lg font-extrabold">Un souci ?</h2>
          <details><summary className="cursor-pointer font-semibold">Je ne vois pas l'option « Installer »</summary>
            <p className="mt-1 text-slate-700">Rechargez la page une fois, puis recommencez. Vérifiez que vous utilisez Chrome (Android) ou Safari (iPhone), et que vous avez ouvert le lien en entier.</p></details>
          <details><summary className="cursor-pointer font-semibold">Où est l'application après l'installation ?</summary>
            <p className="mt-1 text-slate-700">Sur l'écran d'accueil de votre téléphone, avec l'icône {NOM_APP}, comme vos autres applications. Sur Android, elle est aussi dans la liste de toutes les applications.</p></details>
          <details><summary className="cursor-pointer font-semibold">Faut-il la mettre à jour ?</summary>
            <p className="mt-1 text-slate-700">Non. {NOM_APP} se met à jour toute seule à chaque ouverture, quand vous avez Internet.</p></details>
          <details><summary className="cursor-pointer font-semibold">Comment la désinstaller ?</summary>
            <p className="mt-1 text-slate-700">Appuyez longuement sur l'icône {NOM_APP} puis choisissez « Désinstaller » ou « Supprimer ». Votre compte reste en ligne tant que vous ne le supprimez pas depuis vos réglages.</p></details>
        </section>

        <p className="text-center text-sm"><Link to="/connexion" className="font-semibold text-primary">← Retour à la connexion</Link></p>
      </main>
    </div>
  );
}
