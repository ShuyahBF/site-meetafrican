import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { apiClient, extractErrorMessage } from "@/lib/api";
import BottomNav from "@/components/BottomNav";

const PRESETS_XOF = [1000, 2500, 5000, 10000];

const KIND_LABEL = {
  recharge: "Recharge",
  gift_sent: "Cadeau envoyé",
  gift_received: "Cadeau reçu",
};

function fmtXOF(n) {
  return Number(n || 0).toLocaleString("fr-FR") + " FCFA";
}

export default function Wallet() {
  const [balance, setBalance] = useState(0);
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);
  const [amount, setAmount] = useState(PRESETS_XOF[1]);
  const [paying, setPaying] = useState(false);
  const [error, setError] = useState("");

  const load = () => {
    setLoading(true);
    apiClient
      .get("/me/wallet")
      .then((r) => {
        setBalance(r.data.balance_xof);
        setHistory(r.data.history);
      })
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  const recharge = async () => {
    if (amount <= 0 || paying) return;
    setError("");
    setPaying(true);
    try {
      const page = await apiClient.post("/payments/pawapay/wallet-recharge", { amount_xof: amount });
      window.location.href = page.data.redirect_url;
    } catch (err) {
      setError(extractErrorMessage(err, "Recharge indisponible pour le moment"));
      setPaying(false);
    }
  };

  return (
    <div className="flex min-h-screen flex-col bg-background-light font-display dark:bg-background-dark">
      <header className="flex items-center gap-3 px-4 py-4">
        <Link to="/profil" className="text-slate-500 dark:text-slate-400">
          <span className="material-symbols-outlined">arrow_back</span>
        </Link>
        <h1 className="text-xl font-bold text-slate-900 dark:text-white">Mon portefeuille</h1>
      </header>

      <main className="flex-1 px-4 pb-6">
        <div className="rounded-2xl bg-primary p-5 text-white shadow-lg">
          <p className="text-sm opacity-80">Solde disponible</p>
          <p className="mt-1 text-3xl font-bold">{loading ? "…" : fmtXOF(balance)}</p>
          <p className="mt-1 text-xs opacity-80">Sert à envoyer des cadeaux payants (fleurs, chocolats…)</p>
        </div>

        <section className="mt-6">
          <h2 className="mb-3 text-sm font-bold uppercase tracking-wide text-slate-500 dark:text-slate-400">
            Recharger
          </h2>
          <div className="grid grid-cols-4 gap-2">
            {PRESETS_XOF.map((p) => (
              <button
                key={p}
                onClick={() => setAmount(p)}
                className={`h-11 rounded-xl border-2 text-sm font-semibold transition ${
                  amount === p
                    ? "border-primary bg-primary/10 text-primary"
                    : "border-slate-200 text-slate-600 hover:border-primary/50 dark:border-white/10 dark:text-slate-300"
                }`}
              >
                {p.toLocaleString("fr-FR")}
              </button>
            ))}
          </div>
          <input
            type="number"
            min={100}
            step={100}
            value={amount}
            onChange={(e) => setAmount(Number(e.target.value))}
            className="input mt-3"
            placeholder="Montant personnalisé (XOF)"
          />
          {error && <p className="mt-2 text-sm text-red-500">{error}</p>}
          <button
            onClick={recharge}
            disabled={paying || amount <= 0}
            className="mt-3 h-12 w-full rounded-full bg-primary text-sm font-bold text-white disabled:opacity-50"
          >
            {paying ? "Redirection…" : "Recharger par Mobile Money"}
          </button>
        </section>

        <section className="mt-8">
          <h2 className="mb-3 text-sm font-bold uppercase tracking-wide text-slate-500 dark:text-slate-400">
            Historique
          </h2>
          {loading ? (
            <p className="text-sm text-slate-400">Chargement…</p>
          ) : history.length === 0 ? (
            <p className="text-sm text-slate-500 dark:text-slate-400">Aucun mouvement pour l'instant.</p>
          ) : (
            <div className="flex flex-col divide-y divide-slate-800/10 dark:divide-white/10">
              {history.map((h) => (
                <div key={h.id} className="flex items-center justify-between py-3">
                  <div>
                    <p className="text-sm font-semibold text-slate-800 dark:text-white">
                      {KIND_LABEL[h.kind] || h.kind}
                    </p>
                    <p className="text-xs text-slate-500 dark:text-slate-400">{h.description}</p>
                  </div>
                  <p className={`font-bold ${h.amount_xof >= 0 ? "text-emerald-500" : "text-slate-500 dark:text-slate-300"}`}>
                    {h.amount_xof >= 0 ? "+" : ""}
                    {fmtXOF(h.amount_xof)}
                  </p>
                </div>
              ))}
            </div>
          )}
        </section>
      </main>

      <BottomNav />
    </div>
  );
}
