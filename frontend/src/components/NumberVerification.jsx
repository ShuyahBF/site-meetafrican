import { useEffect, useState } from "react";
import { apiClient, extractErrorMessage } from "@/lib/api";
import { formatDateTime } from "@/lib/format";

// Les deux canaux vérifiables : WhatsApp (API Meta) et téléphone (SMS Orange).
const CHANNELS = [
  { key: "whatsapp", label: "WhatsApp", icon: "chat", numberField: "whatsapp", verifiedField: "whatsapp_verified", color: "text-emerald-600" },
  { key: "sms", label: "Téléphone (SMS)", icon: "sms", numberField: "phone", verifiedField: "phone_verified", color: "text-sky-600" },
].map((c) => ({ ...c, verifiedAtField: `${c.verifiedField}_at` })); // ex. "whatsapp_verified_at"

/**
 * Section « Mes numéros » de la page profil : vérification du numéro
 * WhatsApp et du numéro de téléphone par code OTP à 6 chiffres.
 * Étapes : saisir le numéro -> « Recevoir le code » -> saisir le code -> « Valider ».
 */
export default function NumberVerification() {
  const [numbers, setNumbers] = useState(null);

  // Chargement de mes numéros et des canaux disponibles côté serveur
  const load = () => apiClient.get("/me/numbers").then((r) => setNumbers(r.data));
  useEffect(() => {
    load();
  }, []);

  if (!numbers) return null;
  return (
    <section id="numeros" className="mt-8">
      <h2 className="section-title">Mes numéros</h2>
      <p className="-mt-1 mb-3 text-xs text-slate-400">
        Un numéro vérifié rassure vos contacts (badge sur votre profil). Il n'est jamais montré aux autres membres.
      </p>
      <div className="space-y-3">
        {CHANNELS.map((c) => (
          <ChannelRow
            key={c.key}
            channel={c}
            number={numbers[c.numberField]}
            verified={numbers[c.verifiedField]}
            verifiedAt={numbers[c.verifiedAtField]}
            available={numbers.channels?.[c.key]}
            onVerified={load}
          />
        ))}
      </div>
    </section>
  );
}

/** Une ligne (WhatsApp ou SMS) avec son propre petit parcours OTP. */
function ChannelRow({ channel, number, verified, verifiedAt, available, onVerified }) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(number || "");
  const [codeSentTo, setCodeSentTo] = useState(""); // numéro masqué, une fois le code envoyé
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  // Étape 1 : demander l'envoi du code
  const sendCode = async () => {
    setBusy(true);
    setError("");
    try {
      const r = await apiClient.post("/me/numbers/otp/request", { channel: channel.key, number: value });
      setCodeSentTo(r.data.masked_number);
      setCode("");
    } catch (err) {
      setError(extractErrorMessage(err, "Envoi du code impossible"));
    } finally {
      setBusy(false);
    }
  };

  // Étape 2 : valider le code reçu
  const verify = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await apiClient.post("/me/numbers/otp/verify", { channel: channel.key, code });
      setCodeSentTo("");
      setEditing(false);
      onVerified();
    } catch (err) {
      setError(extractErrorMessage(err, "Code refusé"));
    } finally {
      setBusy(false);
    }
  };

  const showForm = !verified || editing;
  return (
    <div className="card p-4">
      <div className="flex items-center gap-3">
        <span className={`material-symbols-outlined ${channel.color}`}>{channel.icon}</span>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-extrabold">{channel.label}</p>
          <p className="truncate text-xs text-slate-500">
            {number || "Aucun numéro"}
            {verified && verifiedAt && <> · vérifié le {formatDateTime(verifiedAt)}</>}
          </p>
        </div>
        {verified && !editing ? (
          <>
            <span className="chip bg-emerald-50 text-emerald-700">
              <span className="material-symbols-outlined icon-filled text-sm">verified</span> Vérifié
            </span>
            <button onClick={() => setEditing(true)} className="text-xs font-semibold text-slate-400 hover:text-primary">
              Changer
            </button>
          </>
        ) : null}
      </div>

      {showForm && !available && (
        <p className="mt-3 text-xs text-slate-400">Bientôt disponible : l'envoi de codes par {channel.label} n'est pas encore activé.</p>
      )}

      {showForm && available && !codeSentTo && (
        <div className="mt-3 flex gap-2">
          <input
            value={value}
            onChange={(e) => setValue(e.target.value)}
            inputMode="tel"
            placeholder="+226 70 12 34 56"
            className="h-11 min-w-0 flex-1 rounded-xl bg-slate-100 px-4 text-sm outline-none focus:ring-2 focus:ring-primary/30"
          />
          <button onClick={sendCode} disabled={busy || value.replace(/\D/g, "").length < 8} className="btn-primary h-11 px-4 text-sm">
            {busy ? "Envoi…" : "Recevoir le code"}
          </button>
        </div>
      )}

      {showForm && codeSentTo && (
        <form onSubmit={verify} className="mt-3 space-y-2">
          <p className="text-xs text-slate-500">
            Code envoyé par {channel.label} au {codeSentTo}. Il est valable 10 minutes.
          </p>
          <div className="flex gap-2">
            <input
              value={code}
              onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
              inputMode="numeric"
              autoComplete="one-time-code"
              placeholder="123456"
              className="h-11 w-32 rounded-xl bg-slate-100 px-4 text-center text-lg font-bold tracking-[0.3em] outline-none focus:ring-2 focus:ring-primary/30"
            />
            <button disabled={busy || code.length !== 6} className="btn-primary h-11 px-4 text-sm">
              {busy ? "…" : "Valider"}
            </button>
          </div>
          <button type="button" onClick={sendCode} disabled={busy} className="text-xs font-semibold text-slate-400 hover:text-primary">
            Renvoyer le code
          </button>
        </form>
      )}

      {error && <p className="mt-2 text-xs font-semibold text-rose-600">{error}</p>}
    </div>
  );
}
