import { useState } from "react";
import { apiClient } from "@/lib/api";

const REPORT_REASONS = [
  { value: "fake_profile", label: "Faux profil" },
  { value: "abus", label: "Comportement abusif" },
  { value: "autre", label: "Autre" },
];

export default function UserActionsMenu({ targetUserId, targetName }) {
  const [open, setOpen] = useState(false);
  const [modal, setModal] = useState(null); // "rate" | "report" | null

  return (
    <div className="relative">
      <button onClick={() => setOpen((v) => !v)} className="text-slate-500 dark:text-slate-400">
        <span className="material-symbols-outlined">more_vert</span>
      </button>

      {open && (
        <div className="absolute right-0 top-full z-10 mt-1 w-40 rounded-xl bg-white py-1 shadow-lg dark:bg-background-dark dark:ring-1 dark:ring-white/10">
          <button
            onClick={() => { setModal("rate"); setOpen(false); }}
            className="block w-full px-4 py-2 text-left text-sm text-slate-700 hover:bg-slate-100 dark:text-white dark:hover:bg-white/10"
          >
            Noter
          </button>
          <button
            onClick={() => { setModal("report"); setOpen(false); }}
            className="block w-full px-4 py-2 text-left text-sm text-red-500 hover:bg-slate-100 dark:hover:bg-white/10"
          >
            Signaler
          </button>
        </div>
      )}

      {modal === "rate" && <RateModal targetUserId={targetUserId} targetName={targetName} onClose={() => setModal(null)} />}
      {modal === "report" && <ReportModal targetUserId={targetUserId} targetName={targetName} onClose={() => setModal(null)} />}
    </div>
  );
}

function RateModal({ targetUserId, targetName, onClose }) {
  const [score, setScore] = useState(5);
  const [comment, setComment] = useState("");
  const [sending, setSending] = useState(false);
  const [done, setDone] = useState(false);

  const submit = async () => {
    setSending(true);
    try {
      await apiClient.post("/me/ratings", { rated_user_id: targetUserId, score, comment: comment || null });
      setDone(true);
    } finally {
      setSending(false);
    }
  };

  return (
    <ModalShell onClose={onClose}>
      {done ? (
        <p className="text-sm text-slate-700 dark:text-white">Merci pour votre avis sur {targetName} !</p>
      ) : (
        <>
          <p className="font-bold text-slate-900 dark:text-white">Noter {targetName}</p>
          <div className="mt-3 flex justify-center gap-1">
            {[1, 2, 3, 4, 5].map((n) => (
              <button key={n} onClick={() => setScore(n)}>
                <span className={`material-symbols-outlined text-3xl ${n <= score ? "text-primary" : "text-slate-300 dark:text-white/20"}`}>
                  star
                </span>
              </button>
            ))}
          </div>
          <textarea
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            placeholder="Commentaire (optionnel)"
            rows={3}
            className="textarea mt-3"
          />
          <button onClick={submit} disabled={sending} className="mt-3 h-11 w-full rounded-full bg-primary text-sm font-bold text-white disabled:opacity-50">
            {sending ? "Envoi…" : "Envoyer la note"}
          </button>
        </>
      )}
    </ModalShell>
  );
}

function ReportModal({ targetUserId, targetName, onClose }) {
  const [reason, setReason] = useState("fake_profile");
  const [details, setDetails] = useState("");
  const [sending, setSending] = useState(false);
  const [done, setDone] = useState(false);

  const submit = async () => {
    setSending(true);
    try {
      await apiClient.post("/me/reports", { reported_user_id: targetUserId, reason, details: details || null });
      setDone(true);
    } finally {
      setSending(false);
    }
  };

  return (
    <ModalShell onClose={onClose}>
      {done ? (
        <p className="text-sm text-slate-700 dark:text-white">
          Signalement envoyé. Notre équipe va examiner le profil de {targetName}.
        </p>
      ) : (
        <>
          <p className="font-bold text-slate-900 dark:text-white">Signaler {targetName}</p>
          <select value={reason} onChange={(e) => setReason(e.target.value)} className="input select mt-3">
            {REPORT_REASONS.map((r) => (
              <option key={r.value} value={r.value}>{r.label}</option>
            ))}
          </select>
          <textarea
            value={details}
            onChange={(e) => setDetails(e.target.value)}
            placeholder="Détails (optionnel)"
            rows={3}
            className="textarea mt-3"
          />
          <button onClick={submit} disabled={sending} className="mt-3 h-11 w-full rounded-full bg-red-600 text-sm font-bold text-white disabled:opacity-50">
            {sending ? "Envoi…" : "Envoyer le signalement"}
          </button>
        </>
      )}
    </ModalShell>
  );
}

function ModalShell({ children, onClose }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="w-full max-w-sm rounded-xl bg-white p-5 dark:bg-background-dark">
        {children}
        <button onClick={onClose} className="mt-3 w-full text-center text-sm text-slate-400">
          Fermer
        </button>
      </div>
    </div>
  );
}
