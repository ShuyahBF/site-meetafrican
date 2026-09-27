import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { apiClient } from "@/lib/api";

// Nombre de vérifications (toutes les 3 s) avant d'afficher "en attente".
const MAX_CHECKS = 10;

/**
 * Bandeau affiché au retour de la page de paiement PawaPay : le serveur
 * renvoie le client sur https://beauthentik.net/abonnement?paiement=<id>
 * (ou /portefeuille). On interroge l'état du paiement jusqu'à confirmation,
 * puis `onCompleted` permet à la page de se rafraîchir (abonnement actif,
 * solde crédité).
 */
export default function PaymentReturnBanner({ onCompleted }) {
  const [params, setParams] = useSearchParams();
  const depositId = params.get("paiement");
  const [status, setStatus] = useState(depositId ? "checking" : null);
  const [message, setMessage] = useState("");

  useEffect(() => {
    if (!depositId) return;
    let cancelled = false;
    let checks = 0;
    const check = async () => {
      checks += 1;
      try {
        const r = await apiClient.get(`/payments/pawapay/${depositId}`, { params: { refresh: true } });
        if (cancelled) return;
        const s = (r.data.status || "").toLowerCase();
        if (s === "completed") {
          setStatus("completed");
          onCompleted?.();
          return;
        }
        if (s === "failed" || s === "rejected") {
          setStatus("failed");
          setMessage(r.data.api_message || "");
          return;
        }
      } catch {
        // réseau capricieux : on retente
      }
      if (checks < MAX_CHECKS) setTimeout(check, 3000);
      else if (!cancelled) setStatus("pending");
    };
    check();
    return () => {
      cancelled = true;
    };
  }, [depositId]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!status) return null;

  const styles = {
    checking: ["bg-slate-50 text-slate-600", "hourglass_top", "Vérification de votre paiement…"],
    completed: ["bg-emerald-50 text-emerald-700", "check_circle", "Paiement confirmé, merci ! 🎉"],
    failed: ["bg-red-50 text-red-600", "error", `Le paiement n'a pas abouti${message ? ` : ${message}` : ""}.`],
    pending: ["bg-amber-50 text-amber-700", "schedule", "Paiement en attente de confirmation par votre opérateur. Revenez dans quelques minutes."],
  }[status];

  return (
    <div className={`mx-4 mt-3 flex items-center gap-3 rounded-2xl px-4 py-3 text-sm font-semibold ${styles[0]}`}>
      <span className="material-symbols-outlined icon-filled">{styles[1]}</span>
      <span className="flex-1">{styles[2]}</span>
      {status !== "checking" && (
        <button onClick={() => setParams({})} aria-label="Fermer" className="material-symbols-outlined text-lg opacity-60">
          close
        </button>
      )}
    </div>
  );
}
