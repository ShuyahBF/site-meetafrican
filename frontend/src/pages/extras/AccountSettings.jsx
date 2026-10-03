import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { apiClient, extractErrorMessage } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { enregistrerPreferencesSon, jouerSon, SONS } from "@/lib/bipMessage";
import PageShell from "@/components/PageShell";

// Réglages du compte : un interrupteur par option (le Mode Invisible et le son
// des messages ont chacun leur propre carte, plus bas).
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
];

/** Interrupteur visuel (allumé / éteint). */
function Interrupteur({ allume }) {
  return (
    <span className={`relative mt-1 h-6 w-11 shrink-0 rounded-full transition ${allume ? "bg-primary" : "bg-slate-200"}`}>
      <span className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition ${allume ? "left-[22px]" : "left-0.5"}`} />
    </span>
  );
}

/** Page « Réglages » : notes vocales, transcription, son des messages, Mode Invisible. */
export default function AccountSettings() {
  const [settings, setSettings] = useState(null);
  const [saving, setSaving] = useState("");
  const [message, setMessage] = useState("");

  // Chargement des réglages enregistrés dans le profil (copie locale du son mise à jour)
  useEffect(() => {
    apiClient.get("/me/settings").then((r) => {
      setSettings(r.data);
      enregistrerPreferencesSon(r.data);
    });
  }, []);

  // Enregistre une ou plusieurs valeurs côté serveur, puis relit la réponse
  const enregistrer = async (cle, valeurs) => {
    setSaving(cle);
    setMessage("");
    try {
      const r = await apiClient.put("/me/settings", valeurs);
      setSettings(r.data);
      enregistrerPreferencesSon(r.data);
      return true;
    } catch (err) {
      setMessage(extractErrorMessage(err, "Réglage refusé"));
      return false;
    } finally {
      setSaving("");
    }
  };

  // Bascule d'une option simple (enregistrée immédiatement)
  const toggle = (key) => enregistrer(key, { [key]: !settings[key] });

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
              <Interrupteur allume={settings[o.key]} />
            </button>
          ))}

          <SonMessages settings={settings} setSettings={setSettings} enregistrer={enregistrer} saving={saving} />
          <ModeInvisible settings={settings} setSettings={setSettings} enregistrer={enregistrer} saving={saving} />

          {message && <p role="alert" className="rounded-xl bg-rose-50 p-3 text-sm font-semibold text-rose-700">{message}</p>}
        </div>
      )}
    </PageShell>
  );
}

// ---------------------------------------------------------------------------
// Son des nouveaux messages : activé / mode silencieux, volume, choix du son
// ---------------------------------------------------------------------------
function SonMessages({ settings, setSettings, enregistrer, saving }) {
  const actif = settings.son_messages;
  const volume = Number(settings.son_volume ?? 70);
  const type = settings.son_type || "carillon";

  return (
    <section className="card p-4">
      <button type="button" onClick={() => enregistrer("son_messages", { son_messages: !actif })}
        disabled={saving === "son_messages"} className="flex w-full items-start gap-3 text-left">
        <span className="material-symbols-outlined mt-0.5 text-primary">{actif ? "notifications_active" : "notifications_off"}</span>
        <span className="min-w-0 flex-1">
          <span className="block text-sm font-extrabold">Son des nouveaux messages</span>
          <span className="mt-0.5 block text-xs text-slate-500">
            {actif ? "Un bip retentit quand vous recevez un message." : "Mode silencieux : aucun son à l'arrivée des messages."}
          </span>
        </span>
        <Interrupteur allume={actif} />
      </button>

      {actif && (
        <div className="mt-4 space-y-4 border-t border-slate-100 pt-4">
          {/* Volume : la valeur suit le curseur, elle est enregistrée au relâchement */}
          <label className="block text-xs font-bold text-slate-500">
            Volume : {volume} %
            <input type="range" min={0} max={100} step={5} value={volume} className="mt-2 w-full accent-primary"
              onChange={(e) => setSettings({ ...settings, son_volume: Number(e.target.value) })}
              onPointerUp={(e) => enregistrer("son_volume", { son_volume: Number(e.currentTarget.value) })}
              onKeyUp={(e) => enregistrer("son_volume", { son_volume: Number(e.currentTarget.value) })} />
          </label>

          {/* Choix du son (3 sons courts) */}
          <fieldset>
            <legend className="text-xs font-bold text-slate-500">Son</legend>
            <div className="mt-2 flex flex-wrap gap-2">
              {Object.entries(SONS).map(([cle, libelle]) => (
                <button key={cle} type="button" aria-pressed={type === cle}
                  onClick={() => { enregistrer("son_type", { son_type: cle }); jouerSon(cle, volume); }}
                  className={`rounded-full border px-4 py-1.5 text-sm font-bold ${type === cle ? "border-primary bg-primary text-white" : "border-slate-200 text-slate-600"}`}>
                  {libelle}
                </button>
              ))}
            </div>
          </fieldset>

          <button type="button" onClick={() => jouerSon(type, volume)}
            className="flex items-center gap-1 text-sm font-bold text-primary">
            <span className="material-symbols-outlined text-base">volume_up</span> Écouter
          </button>
        </div>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------------
// Mode Invisible : 14 jours, sur bonus payé ou formule d'abonnement l'incluant
// ---------------------------------------------------------------------------
function ModeInvisible({ settings, setSettings, enregistrer, saving }) {
  const etat = settings.mode_invisible || {};
  const [achat, setAchat] = useState(false);
  const [erreur, setErreur] = useState("");
  const aLeDroit = etat.bonus_actif || etat.formule_autorise;

  // Achat du bonus avec le portefeuille (le mode est activé aussitôt pour 14 jours)
  const acheter = async () => {
    if (!window.confirm(`Acheter le bonus Mode Invisible pour ${etat.prix_bonus_xof} FCFA (débités de votre portefeuille) ?`)) return;
    setAchat(true);
    setErreur("");
    try {
      const r = await apiClient.post("/me/mode-invisible/bonus");
      setSettings(r.data);
    } catch (err) {
      setErreur(extractErrorMessage(err, "Achat impossible"));
    } finally {
      setAchat(false);
    }
  };

  // Activation / désactivation (le serveur refuse l'activation sans droit : 403)
  const basculer = async () => {
    setErreur("");
    await enregistrer("invisible_mode", { invisible_mode: !settings.invisible_mode });
  };

  return (
    <section className="card p-4">
      <div className="flex items-start gap-3">
        <span className="material-symbols-outlined mt-0.5 text-primary">visibility_off</span>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-extrabold">Mode Invisible</p>
          <p className="mt-0.5 text-xs text-slate-500">
            Vous n'apparaissez plus « en ligne », et vos visites de profils ou de Moments ne sont pas montrées aux
            autres membres. Valable {etat.duree_jours || 14} jours à partir de l'activation, puis désactivé automatiquement.
          </p>
        </div>
        {aLeDroit && (
          <button type="button" onClick={basculer} disabled={saving === "invisible_mode"} aria-label="Activer ou désactiver le Mode Invisible">
            <Interrupteur allume={settings.invisible_mode} />
          </button>
        )}
      </div>

      {/* État actuel */}
      {settings.invisible_mode && etat.expire_le && (
        <p className="mt-3 rounded-xl bg-emerald-50 p-3 text-sm font-semibold text-emerald-800">
          Mode Invisible actif jusqu'au {formatDateTime(etat.expire_le)}.
        </p>
      )}
      {!settings.invisible_mode && etat.bonus_actif && (
        <p className="mt-3 text-xs text-slate-500">Votre bonus reste valable jusqu'au {formatDateTime(etat.bonus_jusqu_au)}.</p>
      )}
      {!settings.invisible_mode && !etat.bonus_actif && etat.formule_autorise && (
        <p className="mt-3 text-xs text-slate-500">Inclus dans votre formule d'abonnement.</p>
      )}

      {/* Sans droit : acheter le bonus ou changer de formule */}
      {!aLeDroit && (
        <div className="mt-3 space-y-2 rounded-xl bg-slate-50 p-3 text-sm">
          <p className="font-semibold text-slate-700">
            Le Mode Invisible est réservé aux membres qui achètent le bonus ou dont la formule l'inclut.
          </p>
          {etat.achat_disponible ? (
            <>
              <button type="button" onClick={acheter} disabled={achat} className="btn-primary flex items-center gap-2">
                {achat && <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/40 border-t-white" aria-hidden="true" />}
                {achat ? "Patientez…" : `Acheter le bonus · ${Number(etat.prix_bonus_xof).toLocaleString("fr-FR")} FCFA`}
              </button>
              <p className="text-xs text-slate-500">
                Payé avec votre portefeuille (solde : {Number(etat.solde_xof || 0).toLocaleString("fr-FR")} FCFA).{" "}
                <Link to="/portefeuille" className="font-bold text-primary">Recharger</Link>
              </p>
            </>
          ) : (
            <p className="text-xs text-slate-500">L'achat du bonus n'est pas encore disponible.</p>
          )}
          <p className="text-xs text-slate-500">
            Ou <Link to="/abonnement" className="font-bold text-primary">choisissez une formule</Link> qui inclut le Mode Invisible.
          </p>
        </div>
      )}
      {erreur && <p role="alert" className="mt-2 text-sm font-semibold text-rose-700">{erreur}</p>}
    </section>
  );
}
