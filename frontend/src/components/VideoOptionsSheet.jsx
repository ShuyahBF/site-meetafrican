import { useState } from "react";
import { apiClient, extractErrorMessage } from "@/lib/api";
import BottomSheet from "@/components/BottomSheet";

const REPORT_REASONS = [
  { value: "faux_profil", label: "Faux profil / usurpation", icon: "person_off" },
  { value: "contenu_choquant", label: "Contenu choquant ou inapproprié", icon: "visibility_off" },
  { value: "harcelement", label: "Harcèlement", icon: "front_hand" },
  { value: "spam", label: "Spam / arnaque", icon: "report" },
  { value: "autre", label: "Autre", icon: "more_horiz" },
];

// Options "…" d'une vidéo : signaler (vidéo d'un autre membre) ou supprimer
// (sa propre vidéo). `onRemoved` retire la vidéo du fil côté interface.
export default function VideoOptionsSheet({ video, onClose, onRemoved, notify }) {
  const [step, setStep] = useState("menu"); // "menu" | "report"
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const report = async (reason) => {
    setBusy(true);
    setError("");
    try {
      await apiClient.post(`/videos/${video.id}/report`, { reason });
      notify?.("Merci, notre équipe va examiner cette vidéo 🙏");
      onRemoved?.(video.id); // on ne la remontre plus à cette personne
      onClose();
    } catch (err) {
      setError(extractErrorMessage(err, "Signalement impossible"));
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    if (!window.confirm("Supprimer définitivement cette vidéo ?")) return;
    setBusy(true);
    try {
      await apiClient.delete(`/videos/${video.id}`);
      notify?.("Vidéo supprimée");
      onRemoved?.(video.id);
      onClose();
    } catch (err) {
      setError(extractErrorMessage(err, "Suppression impossible"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <BottomSheet title={step === "report" ? "Pourquoi signaler cette vidéo ?" : "Options"} onClose={onClose}>
      <div className="px-3 pb-6">
        {error && <p className="px-2 pb-2 text-sm text-red-500">{error}</p>}
        {step === "menu" ? (
          video.is_mine ? (
            <OptionRow icon="delete" label="Supprimer ma vidéo" danger onClick={remove} disabled={busy} />
          ) : (
            <OptionRow icon="flag" label="Signaler" danger onClick={() => setStep("report")} />
          )
        ) : (
          REPORT_REASONS.map((r) => (
            <OptionRow key={r.value} icon={r.icon} label={r.label} onClick={() => report(r.value)} disabled={busy} />
          ))
        )}
      </div>
    </BottomSheet>
  );
}

function OptionRow({ icon, label, onClick, danger = false, disabled = false }) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`flex w-full items-center gap-3 rounded-2xl px-3 py-3.5 text-left text-sm font-semibold transition hover:bg-slate-50 disabled:opacity-50 ${
        danger ? "text-red-500" : "text-ink"
      }`}
    >
      <span className="flex h-10 w-10 items-center justify-center rounded-full bg-slate-100">
        <span className="material-symbols-outlined text-xl">{icon}</span>
      </span>
      {label}
    </button>
  );
}
