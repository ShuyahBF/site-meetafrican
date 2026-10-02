import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { apiClient, extractErrorMessage } from "@/lib/api";
import { formatDecompte, heureLocale, signalerChangementMaintenance, useEtatMaintenance } from "@/lib/maintenancePlateforme";

// ---------------------------------------------------------------------------
// Surveillance de la maintenance de la plateforme, montée une seule fois dans
// App.jsx pour TOUT utilisateur connecté (rien pour les simples visiteurs).
//
// Membres (et modérateurs) :
//   - annonce      : fenêtre (message + décompte) qu'on peut fermer ; fermée, un
//                    bandeau rouge reste affiché avec le décompte ;
//   - verrouillage : écran entièrement verrouillé (ni Échap, ni clic dehors,
//                    ni tabulation vers la page), message + décompte mm:ss ;
//   - échéance     : déconnexion forcée et retour à la page de connexion.
// Administrateur principal (jamais déconnecté) : bandeau de suivi avec
// « Annuler » avant l'échéance, puis « Maintenance en cours — connexions
// bloquées » avec « Réactiver les connexions ».
// ---------------------------------------------------------------------------
export default function SurveillanceMaintenance() {
  const { user } = useAuth();
  const suivi = useEtatMaintenance(!!user);
  if (!user || !suivi.etat || suivi.phase === "aucune") return null;
  return user.role === "admin" ? <BandeauAdministrateur {...suivi} /> : <AlerteMembre {...suivi} />;
}

// ---------------------------------------------------------------------------
// Membres : fenêtre, bandeau, verrouillage puis déconnexion forcée
// ---------------------------------------------------------------------------
function AlerteMembre({ etat, phase, secondes }) {
  const { logout } = useAuth();
  const navigate = useNavigate();
  // Fenêtre fermée pour CETTE annonce (une nouvelle annonce la rouvre)
  const [fermeePour, setFermeePour] = useState(null);
  const deconnecte = useRef(false);

  const echeanceAtteinte = phase === "maintenance" || secondes <= 0;
  useEffect(() => {
    if (!echeanceAtteinte || deconnecte.current) return;
    deconnecte.current = true;
    logout(); // efface la session (jeton) et l'utilisateur courant
    navigate("/connexion", { replace: true, state: { maintenance: true } });
  }, [echeanceAtteinte, logout, navigate]);

  if (phase === "verrouillage" || echeanceAtteinte) {
    return <EcranVerrouille etat={etat} secondes={secondes} deconnexionEnCours={echeanceAtteinte} />;
  }
  if (fermeePour !== etat.annonce_le) {
    return (
      <div className="fixed inset-0 z-[110] flex items-center justify-center bg-black/60 p-4"
        onClick={() => setFermeePour(etat.annonce_le)}>
        <div role="alertdialog" aria-modal="true" aria-labelledby="maintenance-titre"
          className="w-full max-w-md animate-fade-in rounded-2xl bg-white p-6 text-ink shadow-2xl" onClick={(e) => e.stopPropagation()}>
          <div className="mb-3 flex items-start justify-between gap-4">
            <h2 id="maintenance-titre" className="text-lg font-bold text-rose-700">⚠️ Déconnexion programmée</h2>
            <button type="button" onClick={() => setFermeePour(etat.annonce_le)} aria-label="Fermer"
              className="rounded-full px-2 py-1 text-slate-500 hover:bg-slate-100">✕</button>
          </div>
          <p className="whitespace-pre-line text-slate-800">{etat.message}</p>
          <Decompte secondes={secondes} />
          <p className="text-sm text-slate-600">
            Terminez ce que vous êtes en train de faire. L'écran sera verrouillé à {heureLocale(etat.debut_verrouillage)},
            puis vous serez déconnecté(e) à {heureLocale(etat.echeance)}. Vous pourrez vous reconnecter dès que
            l'accès sera rétabli.
          </p>
          <button type="button" className="btn-primary mt-4 w-full" onClick={() => setFermeePour(etat.annonce_le)}>
            J'ai compris
          </button>
        </div>
      </div>
    );
  }
  // Fenêtre fermée : bandeau rouge persistant
  return (
    <div role="status" className="fixed inset-x-0 top-0 z-[90] bg-rose-600 px-4 py-2 text-sm text-white shadow-lg">
      <div className="mx-auto flex max-w-5xl flex-wrap items-center justify-center gap-x-3 gap-y-1 text-center">
        <span className="font-semibold">⚠️ Déconnexion de tous les utilisateurs dans <span className="font-mono">{formatDecompte(secondes)}</span></span>
        <span className="max-w-full truncate opacity-90">{etat.message}</span>
        <button type="button" className="underline" onClick={() => setFermeePour(null)}>Revoir le message</button>
      </div>
    </div>
  );
}

function Decompte({ secondes, clair = false }) {
  return (
    <div className={`my-4 rounded-xl p-3 text-center ${clair ? "bg-white/10" : "bg-rose-50"}`}>
      <p className={`text-xs font-semibold uppercase tracking-wider ${clair ? "text-rose-200" : "text-rose-700"}`}>Déconnexion forcée dans</p>
      <p className={`font-mono text-4xl font-extrabold tabular-nums ${clair ? "text-white" : "text-rose-700"}`} aria-live="off">
        {formatDecompte(secondes)}
      </p>
    </div>
  );
}

/** Écran verrouillé, impossible à fermer : la page en dessous est rendue inerte. */
function EcranVerrouille({ etat, secondes, deconnexionEnCours }) {
  useEffect(() => {
    const racine = document.getElementById("root");
    racine?.setAttribute("inert", "");
    const debordement = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    // Échap n'a aucun effet (ni sur cet écran, ni sur une fenêtre ouverte dessous)
    const bloquer = (e) => { if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); } };
    window.addEventListener("keydown", bloquer, true);
    return () => {
      racine?.removeAttribute("inert");
      document.body.style.overflow = debordement;
      window.removeEventListener("keydown", bloquer, true);
    };
  }, []);

  return createPortal(
    <div role="alertdialog" aria-modal="true" aria-labelledby="verrou-titre"
      className="fixed inset-0 z-[1000] flex items-center justify-center bg-ink/95 p-4 text-white backdrop-blur-sm">
      <div className="w-full max-w-lg text-center">
        <p className="text-5xl" aria-hidden="true">🔒</p>
        <h2 id="verrou-titre" className="mt-3 text-2xl font-extrabold">beAuthentik est en cours de maintenance</h2>
        <p className="mt-4 whitespace-pre-line text-lg text-slate-100">{etat.message}</p>
        {deconnexionEnCours ? (
          <p className="mt-6 text-lg font-semibold text-rose-200">Déconnexion en cours…</p>
        ) : (
          <Decompte secondes={secondes} clair />
        )}
        <p className="text-sm text-slate-300">
          Votre session sera fermée à {heureLocale(etat.echeance)}. Vous pourrez vous reconnecter dès que
          l'accès au site sera rétabli.
        </p>
      </div>
    </div>,
    document.body,
  );
}

// ---------------------------------------------------------------------------
// Administrateur principal : suivi, annulation et réactivation
// ---------------------------------------------------------------------------
function BandeauAdministrateur({ etat, phase, secondes }) {
  const [envoi, setEnvoi] = useState(false);

  async function agir(action, succes) {
    setEnvoi(true);
    try {
      await apiClient.post(`/plateforme/deconnexion-generale/${action}`);
      window.alert(succes);
    } catch (err) {
      window.alert(extractErrorMessage(err, "Action impossible"));
    } finally {
      signalerChangementMaintenance();
      setEnvoi(false);
    }
  }

  const enMaintenance = phase === "maintenance";
  return (
    <div role="status" className={`fixed inset-x-0 bottom-0 z-[90] px-4 py-2 text-sm text-white shadow-lg ${enMaintenance ? "bg-rose-700" : "bg-amber-600"}`}>
      <div className="mx-auto flex max-w-5xl flex-wrap items-center justify-center gap-x-4 gap-y-2 text-center">
        {enMaintenance ? (
          <span className="font-semibold">🔒 Maintenance en cours — connexions bloquées pour tous les utilisateurs (sauf l'administrateur)</span>
        ) : (
          <span className="font-semibold">
            ⏳ Déconnexion générale programmée : {phase === "verrouillage" ? "écrans verrouillés, " : ""}
            déconnexion forcée dans <span className="font-mono">{formatDecompte(secondes)}</span> ({heureLocale(etat.echeance)})
          </span>
        )}
        <Link to="/admin/donnees-maintenance" className="underline">Détails</Link>
        {enMaintenance ? (
          <button type="button" disabled={envoi} className="rounded-full bg-white px-4 py-1.5 font-bold text-rose-700 hover:bg-rose-50 disabled:opacity-50"
            onClick={() => agir("reactiver", "Connexions réactivées : chacun peut se reconnecter.")}>
            {envoi ? "…" : "Réactiver les connexions"}
          </button>
        ) : (
          <button type="button" disabled={envoi} className="rounded-full border border-white/60 px-4 py-1.5 font-semibold text-white hover:bg-white/10 disabled:opacity-50"
            onClick={() => window.confirm("Annuler la déconnexion programmée ? Personne ne sera déconnecté.")
              && agir("annuler", "Déconnexion annulée.")}>
            {envoi ? "…" : "Annuler la déconnexion"}
          </button>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Avis affiché sur la page de connexion
// ---------------------------------------------------------------------------
export function AvisMaintenance() {
  const { etat, phase, secondes } = useEtatMaintenance(true);
  if (!etat || phase === "aucune") return null;
  if (phase === "maintenance") {
    return (
      <div role="alert" className="mb-6 rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800">
        <p className="font-bold">🔒 beAuthentik est en maintenance</p>
        <p className="mt-1 whitespace-pre-line">{etat.message}</p>
        <p className="mt-1 text-xs">Les connexions sont suspendues jusqu'au rétablissement de l'accès. Réessayez un peu plus tard.</p>
      </div>
    );
  }
  return (
    <div role="status" className="mb-6 rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
      <p className="font-bold">⏳ Maintenance prévue dans <span className="font-mono">{formatDecompte(secondes)}</span></p>
      <p className="mt-1 whitespace-pre-line">{etat.message}</p>
    </div>
  );
}
