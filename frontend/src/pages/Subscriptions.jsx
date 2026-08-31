import { useEffect, useState } from "react";
import { apiClient, extractErrorMessage } from "@/lib/api";

function fmtXOF(n) {
  return Number(n || 0).toLocaleString("fr-FR") + " FCFA";
}

export default function Subscriptions() {
  const [plans, setPlans] = useState([]);
  const [loading, setLoading] = useState(true);
  const [paying, setPaying] = useState(null); // plan_id en cours de paiement
  const [error, setError] = useState("");
  const [proofUrl, setProofUrl] = useState("");
  const [proofPlanId, setProofPlanId] = useState(null);
  const [proofSent, setProofSent] = useState(false);

  useEffect(() => {
    apiClient
      .get("/subscriptions/plans")
      .then((r) => setPlans(r.data))
      .finally(() => setLoading(false));
  }, []);

  const payWithPawaPay = async (plan) => {
    setError("");
    setPaying(plan.id);
    try {
      const sub = await apiClient.post("/subscriptions/subscribe", { plan_id: plan.id });
      const page = await apiClient.post("/payments/pawapay/payment-page", {
        subscription_id: sub.data.subscription_id,
        amount_xof: plan.price_xof,
      });
      window.location.href = page.data.redirect_url;
    } catch (err) {
      setError(extractErrorMessage(err, "Paiement indisponible pour le moment"));
    } finally {
      setPaying(null);
    }
  };

  const submitProof = async () => {
    if (!proofUrl.trim()) return;
    try {
      const sub = await apiClient.post("/subscriptions/subscribe", { plan_id: proofPlanId });
      await apiClient.post("/subscriptions/payment-proof", {
        subscription_id: sub.data.subscription_id,
        screenshot_url: proofUrl.trim(),
      });
      setProofSent(true);
    } catch (err) {
      setError(extractErrorMessage(err, "Envoi de la preuve impossible"));
    }
  };

  return (
    <div className="min-h-screen bg-background-light px-4 py-6 font-display dark:bg-background-dark">
      <h1 className="text-3xl font-bold text-slate-900 dark:text-white">Passez à Premium</h1>
      <p className="mt-2 text-slate-500 dark:text-slate-400">
        Débloquez toutes les fonctionnalités et multipliez vos chances de trouver la bonne personne.
      </p>

      {loading ? (
        <p className="mt-8 text-slate-400">Chargement…</p>
      ) : (
        <div className="mt-6 flex flex-col gap-4">
          {plans.map((p) => (
            <div
              key={p.id}
              className={`rounded-xl border p-5 ${p.featured ? "border-primary" : "border-slate-800/20 dark:border-white/10"}`}
            >
              {p.badge && (
                <span className="mb-2 inline-block rounded-full bg-primary px-3 py-1 text-xs font-bold text-white">
                  {p.badge}
                </span>
              )}
              <p className="text-slate-500 dark:text-slate-300">{p.name}</p>
              <p className="text-3xl font-bold text-slate-900 dark:text-white">
                {fmtXOF(p.price_xof)}{" "}
                <span className="text-sm font-normal text-slate-500">
                  / {p.duration_days >= 300 ? "an" : p.duration_days >= 28 ? "mois" : "semaine"}
                </span>
              </p>
              {p.savings_pct ? (
                <p className="text-sm font-semibold text-emerald-500">Économisez {p.savings_pct}%</p>
              ) : null}
              <ul className="mt-3 flex flex-col gap-1">
                {p.features.map((f) => (
                  <li key={f} className="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-200">
                    <span className="material-symbols-outlined text-base text-primary">check</span>
                    {f}
                  </li>
                ))}
              </ul>

              <button
                onClick={() => payWithPawaPay(p)}
                disabled={paying === p.id}
                className="mt-4 h-12 w-full rounded-full bg-primary text-sm font-bold text-white disabled:opacity-50"
              >
                {paying === p.id ? "Redirection…" : "Payer par Mobile Money (Orange / Moov / Telecel)"}
              </button>
              <button
                onClick={() => { setProofPlanId(p.id); setProofSent(false); }}
                className="mt-2 h-10 w-full rounded-full border border-slate-300 text-sm font-semibold text-slate-700 dark:border-white/20 dark:text-white"
              >
                J'ai déjà payé autrement — envoyer une preuve
              </button>
            </div>
          ))}
        </div>
      )}

      {error && <p className="mt-4 text-sm text-red-400">{error}</p>}

      {proofPlanId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
          <div className="w-full max-w-sm rounded-xl bg-white p-5 dark:bg-background-dark">
            {proofSent ? (
              <>
                <p className="font-bold text-slate-900 dark:text-white">Preuve envoyée</p>
                <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">
                  Notre équipe va vérifier votre paiement et activer votre abonnement sous peu.
                </p>
                <button onClick={() => setProofPlanId(null)} className="mt-4 h-11 w-full rounded-full bg-primary text-sm font-bold text-white">
                  Fermer
                </button>
              </>
            ) : (
              <>
                <p className="font-bold text-slate-900 dark:text-white">Lien de la capture d'écran</p>
                <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                  Collez le lien de la capture confirmant votre paiement (WhatsApp, Drive, etc.).
                </p>
                <input
                  value={proofUrl}
                  onChange={(e) => setProofUrl(e.target.value)}
                  className="input mt-3"
                  placeholder="https://…"
                />
                <div className="mt-4 flex gap-2">
                  <button onClick={() => setProofPlanId(null)} className="h-11 flex-1 rounded-full border border-slate-300 text-sm dark:border-white/20 dark:text-white">
                    Annuler
                  </button>
                  <button onClick={submitProof} className="h-11 flex-1 rounded-full bg-primary text-sm font-bold text-white">
                    Envoyer
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
