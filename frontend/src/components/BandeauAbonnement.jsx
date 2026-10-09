import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { apiClient, FOND } from "@/lib/api";

const RELECTURE_MS = 5 * 60 * 1000;

/**
 * Abonnement Premium du membre connecté (backend/abonnement_grace.py et cycle_vie.py),
 * monté une seule fois dans App :
 *  - période de grâce : bandeau rouge « Abonnement expiré — N jour(s) de grâce restant(s) — Renouveler » ;
 *  - grâce écoulée : bandeau orange (fonctions Premium coupées), avec les dates de
 *    suspension et de suppression du compte prévues par le cycle de vie ;
 *  - compte suspendu (J+110) : écran « Compte suspendu — renouveler » sans aucune
 *    donnée, sauf sur la page Abonnement (paiement du renouvellement).
 * Rien pour l'administrateur et les modérateurs.
 */
export default function BandeauAbonnement() {
  const { user, logout } = useAuth();
  const { pathname } = useLocation();
  const [etat, setEtat] = useState(null);
  const [masque, setMasque] = useState(false);

  const equipe = user && (user.role === "admin" || user.role === "moderator");
  useEffect(() => {
    if (!user || equipe) { setEtat(null); return undefined; }
    let annule = false;
    const lire = () => apiClient.get("/abonnement/etat", FOND)
      .then((r) => { if (!annule) setEtat(r.data); })
      .catch(() => {});
    lire();
    const t = setInterval(lire, RELECTURE_MS);
    return () => { annule = true; clearInterval(t); };
  }, [user, equipe, pathname]);

  if (!etat || !user || equipe) return null;
  const cycle = etat.cycle_vie;

  if (etat.suspendu) {
    if (pathname === "/abonnement") {
      return (
        <div role="alert" className="fixed inset-x-0 top-0 z-[80] bg-rose-700 px-4 py-2 text-center text-sm font-semibold text-white">
          Compte suspendu : renouvelez votre abonnement pour le réactiver{cycle?.suppression_le ? ` (suppression le ${cycle.suppression_le})` : ""}.
        </div>
      );
    }
    return (
      <div role="alertdialog" aria-modal="true" aria-labelledby="suspendu-titre"
        className="fixed inset-0 z-[100] flex items-center justify-center bg-ink/95 p-4 text-white">
        <div className="w-full max-w-md text-center">
          <p className="text-5xl" aria-hidden="true">⛔</p>
          <h2 id="suspendu-titre" className="mt-3 text-2xl font-extrabold">Compte suspendu — renouveler</h2>
          <p className="mt-3 text-slate-200">
            Votre abonnement Premium n'a pas été renouvelé. Votre compte est suspendu et n'est plus visible.
            {cycle?.suppression_le && <> Sans renouvellement, il sera <b>définitivement supprimé le {cycle.suppression_le}</b>.</>}
          </p>
          <Link to="/abonnement" className="btn-primary mt-6 inline-block w-full">Renouveler mon abonnement</Link>
          <button type="button" onClick={() => { logout(); window.location.assign("/connexion"); }}
            className="mt-3 w-full py-2 text-sm font-semibold text-slate-300 underline">Se déconnecter</button>
        </div>
      </div>
    );
  }

  if (etat.statut === "grace") {
    const n = etat.jours_grace_restants;
    return (
      <div role="status" className="fixed inset-x-0 top-0 z-[80] bg-rose-600 px-4 py-2 text-center text-sm text-white shadow">
        <span className="font-semibold">Abonnement expiré — {n} jour{n > 1 ? "s" : ""} de grâce restant{n > 1 ? "s" : ""}</span>
        {pathname !== "/abonnement" && <> — <Link to="/abonnement" className="font-bold underline">Renouveler</Link></>}
      </div>
    );
  }

  if (etat.statut === "expire" && !masque) {
    return (
      <div role="status" className="fixed inset-x-0 top-0 z-[80] bg-amber-500 px-4 py-2 text-center text-sm text-white shadow">
        <span className="font-semibold">Abonnement Premium expiré : les fonctions Premium sont coupées.</span>
        {cycle?.suspension_le && <> Sans renouvellement, compte suspendu le {cycle.suspension_le} puis supprimé le {cycle.suppression_le}.</>}
        {pathname !== "/abonnement" && <> <Link to="/abonnement" className="font-bold underline">Renouveler</Link></>}
        <button type="button" aria-label="Masquer" onClick={() => setMasque(true)} className="ml-3 font-bold">✕</button>
      </div>
    );
  }
  return null;
}
