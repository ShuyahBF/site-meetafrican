import { useEffect, useRef, useState } from "react";
import { apiClient } from "@/lib/api";
import { uploadFile } from "@/lib/upload";

export default function AdminSettings() {
  return (
    <div className="flex flex-col gap-10">
      <div>
        <h1 className="text-2xl font-bold">Paramètres</h1>
        <p className="mt-1 text-sm text-slate-500">
          Réglages globaux de la plateforme — modérables sans redéploiement.
        </p>
      </div>
      <AppearanceSection />
      <ReferralPointsSection />
      <ModerationSection />
      <SmsSection />
    </div>
  );
}

// Fournisseur SMS principal pour les codes de vérification (l'autre en repli)
const SMS_CHOICES = [
  { value: "auto", label: "Automatique : Orange pour les numéros +226, OVH pour les autres pays" },
  { value: "orange", label: "Orange en principal, OVH en repli" },
  { value: "ovh", label: "OVH en principal, Orange en repli" },
];

function SmsSection() {
  const [data, setData] = useState(null);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    apiClient.get("/admin/settings/sms").then((r) => setData(r.data));
  }, []);

  // Enregistrement immédiat du choix (réservé à l'administrateur principal)
  const choose = async (primary) => {
    setSaved(false);
    setError("");
    try {
      const r = await apiClient.put("/admin/settings/sms", { primary });
      setData(r.data);
      setSaved(true);
    } catch {
      setError("Réservé à l'administrateur principal");
    }
  };

  if (!data) return null;
  return (
    <section className="rounded-xl border border-slate-200 bg-white p-5">
      <h2 className="font-bold">Envoi des SMS (codes de vérification)</h2>
      <p className="mt-1 text-sm text-slate-500">
        Choisissez le fournisseur principal ; si l'envoi échoue, l'autre prend le relais automatiquement.
      </p>
      <div className="mt-3 space-y-2">
        {SMS_CHOICES.map((c) => (
          <label key={c.value} className="flex items-center gap-2 text-sm">
            <input type="radio" name="sms-primary" checked={data.primary === c.value} onChange={() => choose(c.value)} />
            {c.label}
          </label>
        ))}
      </div>
      <p className="mt-3 text-xs text-slate-500">
        Orange : {data.configured.orange ? "✅ configuré" : "❌ non configuré"} · OVH : {data.configured.ovh ? "✅ configuré" : "❌ non configuré"}
        {" "}(identifiants à saisir sur Render)
      </p>
      {saved && <p className="mt-2 text-xs font-semibold text-emerald-600">Enregistré.</p>}
      {error && <p className="mt-2 text-xs font-semibold text-rose-600">{error}</p>}
    </section>
  );
}

function AppearanceSection() {
  const [form, setForm] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState("");
  const fileRef = useRef(null);

  useEffect(() => {
    apiClient.get("/admin/settings/appearance").then((r) => setForm(r.data));
  }, []);

  const save = async (next) => {
    setSaving(true);
    setSaved(false);
    try {
      await apiClient.put("/admin/settings/appearance", next);
      setForm(next);
      setSaved(true);
    } finally {
      setSaving(false);
    }
  };

  const uploadHero = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setError("");
    setUploading(true);
    try {
      const { url } = await uploadFile(file, "photo");
      await save({ ...form, hero_image_url: url });
    } catch {
      setError("Échec de l'envoi de l'image");
    } finally {
      setUploading(false);
      e.target.value = "";
    }
  };

  const resetHero = () => save({ ...form, hero_image_url: null });

  if (!form) return null;

  return (
    <section className="rounded-xl border border-slate-200 bg-white p-5">
      <h2 className="font-bold">Apparence de la page d'accueil</h2>
      <p className="mt-1 text-sm text-slate-500">
        Change la photo mise en avant sur la page d'accueil publique — pratique pour
        rafraîchir régulièrement le "look" du site sans repasser par le code.
        Sans image ici, le site utilise sa photo par défaut.
      </p>

      <div className="mt-4 flex items-center gap-4">
        <div className="h-24 w-40 overflow-hidden rounded-lg bg-slate-100">
          {form.hero_image_url && (
            <img src={form.hero_image_url} alt="Aperçu" className="h-full w-full object-cover" />
          )}
        </div>
        <div className="flex flex-col gap-2">
          <button
            onClick={() => fileRef.current?.click()}
            disabled={uploading}
            className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
          >
            {uploading ? "Envoi…" : "Changer l'image"}
          </button>
          {form.hero_image_url && (
            <button
              onClick={resetHero}
              disabled={saving}
              className="text-xs font-semibold text-slate-500 hover:text-primary"
            >
              Revenir à l'image par défaut
            </button>
          )}
        </div>
        <input ref={fileRef} type="file" accept="image/*" hidden onChange={uploadHero} />
      </div>

      {error && <p className="mt-2 text-sm text-red-500">{error}</p>}
      {saved && <span className="mt-3 inline-block text-sm text-emerald-600">Enregistré ✓</span>}
    </section>
  );
}

function ReferralPointsSection() {
  const [form, setForm] = useState(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    apiClient.get("/admin/settings/referral-points").then((r) => setForm(r.data));
  }, []);

  const update = (key) => (e) => setForm({ ...form, [key]: Number(e.target.value) });

  const save = async () => {
    setSaving(true);
    setSaved(false);
    try {
      await apiClient.put("/admin/settings/referral-points", form);
      setSaved(true);
    } finally {
      setSaving(false);
    }
  };

  if (!form) return null;

  return (
    <section className="rounded-xl border border-slate-200 bg-white p-5">
      <h2 className="font-bold">Points de parrainage social</h2>
      <p className="mt-1 text-sm text-slate-500">
        Points gagnés quand un membre partage le lien beAuthentik sur chaque plateforme.
      </p>
      <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Field label="WhatsApp">
          <input type="number" value={form.points_whatsapp} onChange={update("points_whatsapp")} className="admin-input" />
        </Field>
        <Field label="Facebook">
          <input type="number" value={form.points_facebook} onChange={update("points_facebook")} className="admin-input" />
        </Field>
        <Field label="Instagram">
          <input type="number" value={form.points_instagram} onChange={update("points_instagram")} className="admin-input" />
        </Field>
        <Field label="TikTok">
          <input type="number" value={form.points_tiktok} onChange={update("points_tiktok")} className="admin-input" />
        </Field>
      </div>
      <Field label="Limite de partages rémunérés par jour">
        <input type="number" value={form.max_shares_per_day} onChange={update("max_shares_per_day")} className="admin-input max-w-xs" />
      </Field>
      <SaveBar onSave={save} saving={saving} saved={saved} />
    </section>
  );
}

function ModerationSection() {
  const [form, setForm] = useState(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    apiClient.get("/admin/settings/moderation").then((r) => setForm(r.data));
  }, []);

  const save = async () => {
    setSaving(true);
    setSaved(false);
    try {
      await apiClient.put("/admin/settings/moderation", form);
      setSaved(true);
    } finally {
      setSaving(false);
    }
  };

  if (!form) return null;

  return (
    <section className="rounded-xl border border-slate-200 bg-white p-5">
      <h2 className="font-bold">Vérification & modération par IA</h2>

      <label className="mt-3 flex items-center gap-2 text-sm font-semibold">
        <input
          type="checkbox"
          checked={form.ai_auto_enabled}
          onChange={(e) => setForm({ ...form, ai_auto_enabled: e.target.checked })}
        />
        Vérification automatique activée
      </label>
      <p className="mt-1 text-xs text-slate-500">
        Si désactivée, toutes les soumissions (pièces d'identité et photos) passent directement en revue humaine.
      </p>

      <Field label="Prompt système — vérification d'identité">
        <textarea
          value={form.id_verification_prompt}
          onChange={(e) => setForm({ ...form, id_verification_prompt: e.target.value })}
          rows={6}
          className="admin-input font-mono text-xs"
        />
      </Field>

      <Field label="Prompt système — modération des photos de profil">
        <textarea
          value={form.photo_moderation_prompt}
          onChange={(e) => setForm({ ...form, photo_moderation_prompt: e.target.value })}
          rows={6}
          className="admin-input font-mono text-xs"
        />
      </Field>

      <SaveBar onSave={save} saving={saving} saved={saved} />
    </section>
  );
}

function Field({ label, children }) {
  return (
    <label className="mt-3 flex flex-col gap-1 text-sm font-semibold text-slate-600">
      {label}
      {children}
    </label>
  );
}

function SaveBar({ onSave, saving, saved }) {
  return (
    <div className="mt-4 flex items-center gap-3">
      <button onClick={onSave} disabled={saving} className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">
        {saving ? "Enregistrement…" : "Enregistrer"}
      </button>
      {saved && <span className="text-sm text-emerald-600">Enregistré ✓</span>}
    </div>
  );
}
