import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { apiClient, extractErrorMessage } from "@/lib/api";
import ModalShell from "@/components/ModalShell";

// Choix d'un cadeau payant (débité du portefeuille prépayé) à envoyer à
// `targetName`. Le catalogue vient de GET /gifts (géré par l'admin).
export default function GiftModal({ targetUserId, targetName, onClose, onSent }) {
  const [gifts, setGifts] = useState([]);
  const [balance, setBalance] = useState(null);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState(null);
  const [message, setMessage] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);

  useEffect(() => {
    Promise.all([apiClient.get("/gifts"), apiClient.get("/me/wallet")])
      .then(([giftsRes, walletRes]) => {
        setGifts(giftsRes.data);
        setBalance(walletRes.data.balance_xof);
      })
      .finally(() => setLoading(false));
  }, []);

  const send = async () => {
    if (!selected || sending) return;
    setSending(true);
    setError("");
    try {
      await apiClient.post(`/users/${targetUserId}/gifts/${selected.id}`, { message: message || null });
      setDone(true);
      onSent?.();
    } catch (err) {
      setError(extractErrorMessage(err, "Impossible d'envoyer ce cadeau"));
    } finally {
      setSending(false);
    }
  };

  return (
    <ModalShell onClose={onClose}>
      {done ? (
        <p className="text-sm text-slate-700 dark:text-white">
          🎁 Cadeau envoyé à {targetName} !
        </p>
      ) : (
        <>
          <p className="font-bold text-slate-900 dark:text-white">Offrir un cadeau à {targetName}</p>
          {balance != null && (
            <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
              Solde du portefeuille : {balance.toLocaleString("fr-FR")} XOF
            </p>
          )}
          {loading ? (
            <p className="mt-3 text-sm text-slate-400">Chargement du catalogue…</p>
          ) : (
            <div className="mt-3 grid grid-cols-3 gap-2">
              {gifts.map((g) => (
                <button
                  key={g.id}
                  onClick={() => setSelected(g)}
                  className={`flex flex-col items-center gap-1 rounded-xl border-2 p-3 transition ${
                    selected?.id === g.id
                      ? "border-primary bg-primary/10"
                      : "border-slate-200 hover:border-primary/50 dark:border-white/10"
                  }`}
                >
                  <span className="text-2xl">{g.emoji}</span>
                  <span className="text-xs font-semibold text-slate-700 dark:text-white">{g.name}</span>
                  <span className="text-[11px] text-slate-400">{g.price_xof} XOF</span>
                </button>
              ))}
            </div>
          )}
          <input
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            maxLength={200}
            placeholder="Petit mot (optionnel)"
            className="input mt-3"
          />
          {error && (
            <div className="mt-2">
              <p className="text-sm text-red-500">{error}</p>
              {error.toLowerCase().includes("insuffisant") && (
                <Link to="/portefeuille" className="text-sm font-semibold text-primary underline">
                  Recharger mon portefeuille
                </Link>
              )}
            </div>
          )}
          <button
            onClick={send}
            disabled={!selected || sending}
            className="mt-3 h-11 w-full rounded-full bg-primary text-sm font-bold text-white disabled:opacity-50"
          >
            {sending ? "Envoi…" : "Envoyer le cadeau"}
          </button>
        </>
      )}
    </ModalShell>
  );
}
