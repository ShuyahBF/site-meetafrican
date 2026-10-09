// ============================================================================
// ASSISTANCE SAWALI — pictogramme + fenêtre de discussion avec le support
// technique SAWALI (SAWALI lot 90, demande du propriétaire du 09/10/2026).
// ============================================================================
// « Pour ne pas être encombrant, un petit pictogramme représentant une
// assistance » : placé dans la barre du bas de l'espace membre (BottomNav), à
// droite de la mention de version. Un clic ouvre une petite fenêtre de chat :
//   - les messages partent vers le serveur beAuthentik (/api/support-sawali/…),
//     qui les relaie à SAWALI par une requête signée (AUCUN secret ici) ;
//   - fenêtre ouverte : lecture des réponses toutes les 5 s ;
//   - fenêtre fermée : vérification des réponses non lues toutes les 60 s
//     (pastille rouge) et un SON à chaque nouvelle réponse ;
//   - la requête est numérotée par SAWALI (SUP-…) et son état est affiché.
// Le pictogramme reste caché si la plateforme n'est pas reliée à SAWALI (clé
// absente) ou si le membre n'est pas connecté.
//
// À NE PAS CONFONDRE avec la page /support (« Écrire au support » : tickets
// internes avec l'équipe beAuthentik), qui reste inchangée.
//
// Rafraîchissements automatiques envoyés avec l'en-tête FOND : ils ne comptent
// pas comme une activité du membre (déconnexion pour inactivité préservée).
// La protection contre les captures (ProtectionCaptures, montée dans App.jsx)
// s'applique aussi à cette fenêtre.
// ============================================================================
import { useCallback, useEffect, useRef, useState } from "react";
import { apiClient, FOND } from "@/lib/api";
import Patientez from "@/components/Patientez";

const RAFRAICHIR_OUVERT_MS = 5000;   // lecture du fil, fenêtre ouverte
const RAFRAICHIR_FERME_MS = 60000;   // vérification des réponses non lues, fenêtre fermée

// Nombre de non-lus déjà signalés : gardé HORS du composant, car la barre du bas
// est recréée à chaque changement de page (sinon le son rejouerait à chaque page).
let nonLusSignales = 0;

// --- Son de notification (3 notes montantes, comme le chat de SAWALI) --------
let contexteAudio = null;
function jouerSon() {
  try {
    const Ctx = window.AudioContext || window.webkitAudioContext;
    if (!Ctx) return;
    contexteAudio = contexteAudio || new Ctx();
    if (contexteAudio.state === "suspended") contexteAudio.resume().catch(() => {});
    const t0 = contexteAudio.currentTime + 0.02;
    [[659.25, 0, 0.18], [783.99, 0.14, 0.18], [1046.5, 0.28, 0.32]].forEach(([f, debut, duree]) => {
      const osc = contexteAudio.createOscillator();
      const env = contexteAudio.createGain();
      osc.type = "triangle";
      osc.frequency.setValueAtTime(f, t0 + debut);
      env.gain.setValueAtTime(0.0001, t0 + debut);
      env.gain.exponentialRampToValueAtTime(0.5, t0 + debut + 0.02);
      env.gain.exponentialRampToValueAtTime(0.0001, t0 + debut + duree);
      osc.connect(env); env.connect(contexteAudio.destination);
      osc.start(t0 + debut); osc.stop(t0 + debut + duree + 0.02);
    });
  } catch { /* son impossible : sans importance */ }
}

// Heure courte « 14:05 » à partir d'une date ISO
const heure = (iso) => {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "" : d.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });
};

// Libellé de l'état de la requête (fourni par SAWALI)
const ETATS = { attente: "En attente du support", active: "En cours", terminee: "Terminée" };

// Message d'erreur lisible renvoyé par le serveur (texte seulement)
const detailErreur = (e, defaut) => {
  const d = e?.response?.data?.detail;
  return typeof d === "string" ? d : defaut;
};

export default function SupportSawali({ className = "" }) {
  const [actif, setActif] = useState(false);       // plateforme reliée à SAWALI ?
  const [ouvert, setOuvert] = useState(false);
  const [messages, setMessages] = useState([]);
  const [requete, setRequete] = useState(null);
  const [nonLus, setNonLus] = useState(nonLusSignales);
  const [texte, setTexte] = useState("");
  const [envoi, setEnvoi] = useState(false);
  const [chargement, setChargement] = useState(false); // première lecture du fil
  const [erreur, setErreur] = useState("");
  const dernierRef = useRef("");                   // date du dernier message reçu (lecture incrémentale)
  const filRef = useRef(null);

  // --- Le pictogramme n'apparaît que pour un membre connecté, plateforme reliée à SAWALI
  useEffect(() => {
    let vivant = true;
    if (!localStorage.getItem("maf_token")) return undefined;
    apiClient.get("/support-sawali/etat", FOND)
      .then((r) => { if (vivant) setActif(!!r.data?.actif); })
      .catch(() => { if (vivant) setActif(false); });
    return () => { vivant = false; };
  }, []);

  // --- Lecture du fil (fenêtre ouverte : nouveaux messages ajoutés et marqués lus)
  const lireFil = useCallback(async () => {
    try {
      const r = await apiClient.post("/support-sawali/fil",
        { depuis: dernierRef.current || null, marquer_lu: true }, FOND);
      const nouveaux = r.data?.messages || [];
      if (nouveaux.length) {
        // Son seulement pour une réponse du support arrivée pendant que la fenêtre est ouverte
        if (dernierRef.current && nouveaux.some((m) => m.de === "support")) jouerSon();
        dernierRef.current = nouveaux[nouveaux.length - 1].le;
        setMessages((avant) => {
          const connus = new Set(avant.map((m) => m.id));
          return [...avant, ...nouveaux.filter((m) => !connus.has(m.id))];
        });
      }
      setRequete(r.data?.requete || null);
      setNonLus(0); nonLusSignales = 0;
      setErreur("");
    } catch (e) {
      setErreur(detailErreur(e, "Assistance SAWALI injoignable : réessayez dans un instant."));
    }
  }, []);

  // --- Fenêtre fermée : simple vérification des réponses non lues (son si leur nombre augmente)
  const verifierNonLus = useCallback(async () => {
    try {
      const r = await apiClient.post("/support-sawali/fil",
        { depuis: dernierRef.current || null, marquer_lu: false }, FOND);
      const n = r.data?.non_lus || 0;
      if (n > nonLusSignales) jouerSon();
      nonLusSignales = n;
      setNonLus(n);
    } catch { /* silencieux : nouvel essai plus tard */ }
  }, []);

  // --- Rafraîchissement automatique : 5 s fenêtre ouverte, 60 s fenêtre fermée
  useEffect(() => {
    if (!actif) return undefined;
    if (ouvert) {
      // Première lecture à l'ouverture : « Patientez… » pendant le chargement
      setChargement(true);
      lireFil().finally(() => setChargement(false));
    } else {
      verifierNonLus();
    }
    const minuterie = setInterval(ouvert ? lireFil : verifierNonLus,
      ouvert ? RAFRAICHIR_OUVERT_MS : RAFRAICHIR_FERME_MS);
    return () => clearInterval(minuterie);
  }, [actif, ouvert, lireFil, verifierNonLus]);

  // --- Défilement automatique vers le dernier message
  useEffect(() => {
    if (filRef.current) filRef.current.scrollTop = filRef.current.scrollHeight;
  }, [messages, ouvert]);

  // --- Envoi d'un message (« Patientez… » pendant l'envoi ; texte conservé en cas d'échec)
  const envoyer = async (e) => {
    e.preventDefault();
    const t = texte.trim();
    if (!t || envoi) return;
    setEnvoi(true);
    try {
      const r = await apiClient.post("/support-sawali/messages", { texte: t });
      setTexte("");
      setRequete(r.data?.requete || requete);
      await lireFil();
    } catch (err) {
      setErreur(detailErreur(err, "Envoi impossible : votre message est conservé, réessayez."));
    } finally {
      setEnvoi(false);
    }
  };

  if (!actif) return null;
  return (
    <>
      {/* Pictogramme discret (casque-micro) + pastille des réponses non lues */}
      <button
        type="button"
        onClick={() => setOuvert((v) => !v)}
        title="Assistance SAWALI"
        aria-label="Assistance SAWALI — écrire au support technique"
        className={`relative inline-flex h-6 w-6 items-center justify-center rounded-full text-slate-400 transition hover:bg-slate-100 hover:text-ink ${className}`}
      >
        <span className="material-symbols-outlined text-[18px]" aria-hidden="true">headset_mic</span>
        {nonLus > 0 && (
          <span className="absolute -right-1 -top-1 min-w-[16px] rounded-full bg-primary px-1 text-center text-[9px] font-bold leading-[16px] text-white ring-2 ring-white">
            {nonLus > 9 ? "9+" : nonLus}
          </span>
        )}
      </button>

      {/* Attente longue (ouverture du fil, envoi) : toast « Patientez… » + jauge */}
      <Patientez actif={ouvert && (envoi || (chargement && messages.length === 0))} />

      {/* Fenêtre de discussion : coin inférieur droit, presque plein écran sur téléphone */}
      {ouvert && (
        <div
          role="dialog"
          aria-label="Assistance SAWALI"
          className="fixed inset-x-2 bottom-2 z-[60] flex h-[70vh] max-h-[560px] flex-col overflow-hidden rounded-2xl bg-white text-left font-display text-ink shadow-2xl ring-1 ring-slate-200 sm:inset-x-auto sm:right-4 sm:w-[360px]"
        >
          {/* En-tête : titre, numéro et état de la requête, bouton fermer */}
          <div className="flex items-center gap-2 bg-ink px-4 py-3 text-white">
            <span className="material-symbols-outlined text-[22px]" aria-hidden="true">headset_mic</span>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-bold">Assistance SAWALI</p>
              <p className="truncate text-xs text-white/70">
                {requete
                  ? `${requete.numero} · ${ETATS[requete.statut] || requete.libelle || ""}`
                  : "Support technique de la plateforme : posez votre question ici."}
              </p>
            </div>
            <button type="button" onClick={() => setOuvert(false)} aria-label="Fermer"
                    className="rounded-lg px-2 py-1 text-lg leading-none hover:bg-white/10">×</button>
          </div>

          {/* Fil des messages (les miens à droite, ceux du support à gauche) */}
          <div ref={filRef} className="flex-1 space-y-2 overflow-y-auto bg-slate-50 p-3">
            {messages.length === 0 && !chargement && (
              <p className="py-6 text-center text-sm italic text-slate-400">Aucun message pour l'instant.</p>
            )}
            {messages.map((m) => (
              <div key={m.id} className={`flex ${m.de === "moi" ? "justify-end" : "justify-start"}`}>
                <div className={`max-w-[80%] rounded-2xl px-3 py-2 text-sm shadow-sm ${
                  m.systeme ? "bg-amber-50 text-amber-900 ring-1 ring-amber-200"
                    : m.de === "moi" ? "bg-ink text-white" : "bg-white ring-1 ring-slate-200"}`}>
                  {m.de !== "moi" && !m.systeme && <p className="mb-0.5 text-[11px] font-bold text-slate-500">{m.auteur}</p>}
                  <p className="whitespace-pre-wrap break-words">{m.texte}</p>
                  <p className={`mt-1 text-right text-[10px] ${m.de === "moi" ? "text-white/60" : "text-slate-400"}`}>{heure(m.le)}</p>
                </div>
              </div>
            ))}
          </div>

          {/* Erreur lisible (jamais de détail technique) */}
          {erreur && <p className="bg-red-50 px-3 py-1 text-xs text-red-700">{erreur}</p>}

          {/* Saisie : Entrée envoie, Maj+Entrée va à la ligne */}
          <form onSubmit={envoyer} className="flex gap-2 border-t border-slate-200 p-2">
            <textarea
              value={texte}
              onChange={(e) => setTexte(e.target.value)}
              rows={2}
              maxLength={2000}
              onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) envoyer(e); }}
              placeholder="Votre message…"
              className="min-w-0 flex-1 resize-none rounded-xl border border-slate-300 px-3 py-2 text-sm"
            />
            <button type="submit" disabled={envoi || !texte.trim()}
                    className="rounded-xl bg-primary px-3 text-sm font-bold text-white disabled:opacity-40">
              {envoi ? "Patientez…" : "Envoyer"}
            </button>
          </form>
        </div>
      )}
    </>
  );
}
