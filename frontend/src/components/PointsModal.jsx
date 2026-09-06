import { useState } from "react";
import { apiClient, extractErrorMessage } from "@/lib/api";
import ModalShell from "@/components/ModalShell";

// Transfert réel de points (débités du solde de l'expéditeur) vers un
// autre profil — distinct du "coup de cœur", geste gratuit sans transfert.
export default function PointsModal({ targetUserId, targetName, availablePoints, onClose, onSent }) {
  const [amount, setAmount] = useState(10);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);

  const send = async () => {
    if (amount <= 0 || sending) return;
    setSending(true);
    setError("");
    try {
      await apiClient.post(`/users/${targetUserId}/points`, { amount });
      setDone(true);
      onSent?.(amount);
    } catch (err) {
      setError(extractErrorMessage(err, "Impossible d'envoyer ces points"));
    } finally {
      setSending(false);
    }
  };

  return (
    <ModalShell onClose={onClose}>
      {done ? (
        <p className="text-sm text-slate-700 dark:text-white">
          ⭐ {amount} points envoyés à {targetName} !
        </p>
      ) : (
        <>
          <p className="font-bold text-slate-900 dark:text-white">Envoyer des points à {targetName}</p>
          <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
            Votre solde : {availablePoints ?? 0} points
          </p>
          <input
            type="number"
            min={1}
            value={amount}
            onChange={(e) => setAmount(Number(e.target.value))}
            className="input mt-3"
          />
          {error && <p className="mt-2 text-sm text-red-500">{error}</p>}
          <button
            onClick={send}
            disabled={sending || amount <= 0}
            className="mt-3 h-11 w-full rounded-full bg-primary text-sm font-bold text-white disabled:opacity-50"
          >
            {sending ? "Envoi…" : "Envoyer"}
          </button>
        </>
      )}
    </ModalShell>
  );
}
