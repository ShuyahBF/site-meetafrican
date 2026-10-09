import { useEffect, useRef, useState } from "react";
import { apiClient, extractErrorMessage } from "@/lib/api";
import { uploadFile } from "@/lib/upload";
import MentionVersion from "@/components/MentionVersion";

export default function AdminSettings() {
  return (
    <div className="flex flex-col gap-10">
      <div>
        <h1 className="text-2xl font-bold">Paramètres</h1>
        <p className="mt-1 text-sm text-slate-500">
          Réglages globaux de la plateforme — modérables sans redéploiement.
        </p>
        {/* Page de paramétrage : libellé DÉTAILLÉ de la version déployée
            (version, lot, commit, date/heure de déploiement) */}
        <MentionVersion className="mt-2 !text-left !text-xs !text-slate-500" detaille />
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

      <MomentsVideoSettings form={form} save={save} />
    </section>
  );
}

// Taille maximale de la vidéo « Moments » de l'accueil — même valeur par
// défaut que le backend (max_home_video_upload_bytes), vérifiée ici pour
// prévenir l'admin avant un envoi inutile ; le serveur reste l'arbitre.
const HOME_VIDEO_MAX_MB = 20;
const HOME_VIDEO_TYPES = ["video/mp4", "video/webm"];

/**
 * Encart vidéo « Moments » de la page d'accueil : fichier envoyé (MP4/WebM)
 * ou URL, image d'aperçu facultative, activation. Tout est enregistré dans
 * le même réglage "Apparence" que l'image de la page d'accueil.
 */
function MomentsVideoSettings({ form, save }) {
  const [videoUrl, setVideoUrl] = useState(form.moments_video_url || "");
  const [posterUrl, setPosterUrl] = useState(form.moments_video_poster_url || "");
  const [enabled, setEnabled] = useState(!!form.moments_video_enabled);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  const videoFileRef = useRef(null);
  const posterFileRef = useRef(null);

  // Enregistre le réglage complet (en conservant l'image d'accueil actuelle).
  const persist = async (next) => {
    setError("");
    setSaved(false);
    try {
      await save({
        ...form,
        moments_video_url: next.videoUrl.trim() || null,
        moments_video_poster_url: next.posterUrl.trim() || null,
        moments_video_enabled: next.enabled,
      });
      setSaved(true);
    } catch (err) {
      setError(extractErrorMessage(err, "Échec de l'enregistrement"));
    }
  };

  // Envoi du fichier vidéo vers le stockage des médias, puis enregistrement.
  const uploadVideo = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    if (!HOME_VIDEO_TYPES.includes(file.type)) {
      setError("Format non autorisé : MP4 ou WebM uniquement");
      return;
    }
    if (file.size > HOME_VIDEO_MAX_MB * 1024 * 1024) {
      setError(`Vidéo trop volumineuse (max ${HOME_VIDEO_MAX_MB} Mo)`);
      return;
    }
    setError("");
    setBusy("video");
    try {
      const formData = new FormData();
      formData.append("file", file);
      const { data } = await apiClient.post("/admin/settings/appearance/moments-video", formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setVideoUrl(data.url);
      setEnabled(true);
      await persist({ videoUrl: data.url, posterUrl, enabled: true });
    } catch (err) {
      setError(extractErrorMessage(err, "Échec de l'envoi de la vidéo"));
    } finally {
      setBusy("");
    }
  };

  // Envoi de l'image d'aperçu (même circuit que les photos), puis enregistrement.
  const uploadPoster = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setError("");
    setBusy("poster");
    try {
      const { url } = await uploadFile(file, "photo");
      setPosterUrl(url);
      await persist({ videoUrl, posterUrl: url, enabled });
    } catch (err) {
      setError(extractErrorMessage(err, "Échec de l'envoi de l'image"));
    } finally {
      setBusy("");
    }
  };

  // Retire complètement la vidéo : plus aucun encart sur la page d'accueil.
  const remove = async () => {
    setVideoUrl("");
    setPosterUrl("");
    setEnabled(false);
    await persist({ videoUrl: "", posterUrl: "", enabled: false });
  };

  return (
    <div className="mt-6 border-t border-slate-100 pt-5">
      <h3 className="font-bold">Vidéo « Moments »</h3>
      <p className="mt-1 text-sm text-slate-500">
        Petit encart vidéo affiché à côté du texte de présentation des Moments, pour montrer aux visiteurs ce
        qu'est un Moment. Muette, en boucle, elle démarre au survol de la souris (au toucher sur mobile).
        Format vertical conseillé, MP4 ou WebM, {HOME_VIDEO_MAX_MB} Mo maximum — idéalement 5 à 15 secondes.
        Sans vidéo (ou désactivée), rien n'est affiché.
      </p>

      <div className="mt-4 flex flex-wrap items-start gap-4">
        {/* Aperçu de la vidéo telle qu'elle apparaîtra (lecture au survol) */}
        <div className="aspect-[9/16] w-28 overflow-hidden rounded-lg bg-slate-100">
          {videoUrl.trim() && (
            <video
              key={videoUrl}
              src={videoUrl}
              poster={posterUrl || undefined}
              muted
              loop
              playsInline
              preload="metadata"
              onMouseEnter={(e) => e.currentTarget.play().catch(() => {})}
              onMouseLeave={(e) => {
                e.currentTarget.pause();
                e.currentTarget.currentTime = 0;
              }}
              className="h-full w-full object-cover"
            />
          )}
        </div>

        <div className="flex min-w-[240px] flex-1 flex-col gap-2">
          <div className="flex flex-wrap gap-2">
            <button
              onClick={() => videoFileRef.current?.click()}
              disabled={!!busy}
              className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
            >
              {busy === "video" ? "Envoi…" : "Envoyer une vidéo"}
            </button>
            <button
              onClick={() => posterFileRef.current?.click()}
              disabled={!!busy}
              className="rounded-lg border border-slate-200 px-4 py-2 text-sm font-semibold text-slate-600 disabled:opacity-50"
            >
              {busy === "poster" ? "Envoi…" : "Image d'aperçu (facultatif)"}
            </button>
          </div>
          <input ref={videoFileRef} type="file" accept="video/mp4,video/webm" hidden onChange={uploadVideo} />
          <input ref={posterFileRef} type="file" accept="image/*" hidden onChange={uploadPoster} />

          <Field label="… ou adresse de la vidéo (https://…)">
            <input
              type="url"
              value={videoUrl}
              onChange={(e) => setVideoUrl(e.target.value)}
              placeholder="https://…/moment.mp4"
              className="admin-input"
            />
          </Field>
          <Field label="Adresse de l'image d'aperçu (facultatif)">
            <input
              type="url"
              value={posterUrl}
              onChange={(e) => setPosterUrl(e.target.value)}
              placeholder="https://…/apercu.jpg"
              className="admin-input"
            />
          </Field>

          <label className="mt-2 flex items-center gap-2 text-sm font-semibold">
            <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
            Afficher la vidéo sur la page d'accueil
          </label>

          <div className="mt-2 flex items-center gap-3">
            <button
              onClick={() => persist({ videoUrl, posterUrl, enabled })}
              disabled={!!busy}
              className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
            >
              Enregistrer
            </button>
            {(videoUrl || posterUrl) && (
              <button onClick={remove} disabled={!!busy} className="text-xs font-semibold text-slate-500 hover:text-primary">
                Retirer la vidéo
              </button>
            )}
            {saved && <span className="text-sm text-emerald-600">Enregistré ✓</span>}
          </div>
          {error && <p className="text-sm text-red-500">{error}</p>}
        </div>
      </div>
    </div>
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

      {/* 09/10/2026 — validation des photos par un administrateur, même quand l'IA les juge conformes */}
      <label className="mt-3 flex items-center gap-2 text-sm font-semibold">
        <input
          type="checkbox"
          checked={form.validation_admin_systematique ?? false}
          onChange={(e) => setForm({ ...form, validation_admin_systematique: e.target.checked })}
        />
        Validation systématique des photos par l'équipe (administrateur ou modérateur)
      </label>
      <p className="mt-1 text-xs text-slate-500">
        Désactivée (recommandé) : l'IA valide ou refuse seule les photos et les pièces d'identité ; l'équipe ne
        tranche que les doutes et peut forcer une décision de l'IA (« Décisions de l'IA ») — photos : administrateurs
        et modérateurs ; pièces d'identité : super-administrateur seulement. Activée : chaque nouvelle photo attend
        en plus une validation de l'équipe.
      </p>

      {/* 09/10/2026 — façon de cacher le visage aux membres qui n'ont pas matché (logo beAuthentik au centre).
          Changer de style régénère en arrière-plan toutes les photos déjà approuvées. */}
      <fieldset className="mt-4">
        <legend className="text-sm font-semibold">Visage caché aux membres sans match</legend>
        <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
          {[
            { valeur: "bandeau", titre: "Bandeau noir", texte: "Des sourcils jusqu'un peu au-dessus du menton." },
            { valeur: "masque_sanitaire", titre: "Masque sanitaire", texte: "Blanc, du nez au menton : le logo ressort mieux ; les yeux restent visibles." },
          ].map((o) => (
            <label
              key={o.valeur}
              className={`flex cursor-pointer items-start gap-3 rounded-xl border p-3 text-sm ${
                (form.style_masque || "bandeau") === o.valeur ? "border-primary bg-primary/5" : "border-slate-200"
              }`}
            >
              <input
                type="radio"
                name="style_masque"
                value={o.valeur}
                checked={(form.style_masque || "bandeau") === o.valeur}
                onChange={() => setForm({ ...form, style_masque: o.valeur })}
                className="mt-1"
              />
              {/* Pictogramme : visage avec bandeau noir ou avec masque bleu */}
              <svg viewBox="0 0 40 40" className="h-10 w-10 shrink-0" aria-hidden="true">
                <ellipse cx="20" cy="21" rx="13" ry="16" fill="#e9c7a8" />
                {o.valeur === "bandeau"
                  ? <rect x="5" y="13" width="30" height="17" rx="2" fill="#0e0c0c" />
                  : <path d="M8 22 Q20 18 32 22 L31 30 Q20 38 9 30 Z" fill="#fafafa" stroke="#c8c8c8" />}
                <circle cx="20" cy={o.valeur === "bandeau" ? 21.5 : 26} r="3" fill="#f4256a" />
              </svg>
              <span>
                <span className="block font-semibold">{o.titre}</span>
                <span className="text-xs text-slate-500">{o.texte}</span>
              </span>
            </label>
          ))}
        </div>
        <p className="mt-1 text-xs text-slate-500">
          Logo beAuthentik au centre. Après un match, les deux membres se voient en clair. Un changement de style
          s'applique aux nouvelles photos et, en arrière-plan, à toutes les photos déjà publiées.
        </p>
      </fieldset>

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
