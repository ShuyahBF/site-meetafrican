import { useEffect, useState } from "react";
import { apiClient } from "@/lib/api";
import PageShell from "@/components/PageShell";

// Réglages du compte : un interrupteur par option.
const OPTIONS = [
  {
    key: "voice_notes",
    icon: "mic",
    title: "Notes vocales",
    text: "Envoyer et recevoir des messages vocaux dans vos conversations.",
  },
  {
    key: "voice_transcription",
    icon: "subtitles",
    title: "Transcription des notes vocales",
    text: "Vos notes vocales sont aussi écrites en texte (reconnaissance vocale de votre navigateur), et vous voyez le texte de celles que vous recevez.",
  },
  {
    key: "invisible_mode",
    icon: "visibility_off",
    title: "Mode invisible",
    text: "Vous n'apparaissez plus « en ligne », et vos visites de profils ou de Moments ne sont pas montrées aux autres membres.",
  },
];

/** Page « Réglages » : notes vocales, transcription, mode invisible. */
export default function AccountSettings() {
  const [settings, setSettings] = useState(null);
  const [saving, setSaving] = useState("");

  useEffect(() => {
    apiClient.get("/me/settings").then((r) => setSettings(r.data));
  }, []);

  // Bascule d'une option (enregistrée immédiatement)
  const toggle = async (key) => {
    setSaving(key);
    try {
      const r = await apiClient.put("/me/settings", { [key]: !settings[key] });
      setSettings(r.data);
    } finally {
      setSaving("");
    }
  };

  return (
    <PageShell title="Réglages" subtitle="Confidentialité et messagerie">
      {settings && (
        <div className="mt-2 space-y-3">
          {OPTIONS.map((o) => (
            <button
              key={o.key}
              onClick={() => toggle(o.key)}
              disabled={saving === o.key}
              className="card flex w-full items-start gap-3 p-4 text-left"
            >
              <span className="material-symbols-outlined mt-0.5 text-primary">{o.icon}</span>
              <span className="min-w-0 flex-1">
                <span className="block text-sm font-extrabold">{o.title}</span>
                <span className="mt-0.5 block text-xs text-slate-500">{o.text}</span>
              </span>
              {/* Interrupteur */}
              <span className={`relative mt-1 h-6 w-11 shrink-0 rounded-full transition ${settings[o.key] ? "bg-primary" : "bg-slate-200"}`}>
                <span className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition ${settings[o.key] ? "left-[22px]" : "left-0.5"}`} />
              </span>
            </button>
          ))}
        </div>
      )}
    </PageShell>
  );
}
