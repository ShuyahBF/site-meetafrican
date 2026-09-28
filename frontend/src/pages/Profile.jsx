import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { apiClient, extractErrorMessage } from "@/lib/api";
import { uploadFile } from "@/lib/upload";
import { useAuth } from "@/context/AuthContext";
import { useProfileOptions } from "@/hooks/useProfileOptions";
import BottomNav from "@/components/BottomNav";
import ProfilePhoto from "@/components/ProfilePhoto";
import VerifiedBadge from "@/components/VerifiedBadge";
import VideoGrid from "@/components/VideoGrid";
import VideoAccessRequests from "@/components/VideoAccessRequests";
import Toast, { useToast } from "@/components/Toast";

const STATUS_LABEL = {
  unverified: { text: "Identité non vérifiée", className: "bg-slate-100 text-slate-500" },
  pending: { text: "Vérification en cours", className: "bg-amber-50 text-amber-600" },
  verified: { text: "Identité vérifiée", className: "bg-sky-50 text-sky-600" },
  rejected: { text: "Vérification refusée", className: "bg-red-50 text-red-500" },
};

const PHOTO_STATUS_LABEL = {
  pending: "En attente",
  approved: "Approuvée",
  rejected: "Refusée",
  needs_review: "En revue",
};

const MAX_INTERESTS = 10;

// Champs éditables du profil, extraits de l'utilisateur connecté.
function toForm(user) {
  return {
    full_name: user?.full_name || "",
    bio: user?.bio || "",
    city: user?.city || "",
    country: user?.country || "",
    profession: user?.profession || "",
    relationship_goal: user?.relationship_goal || "",
    children: user?.children || "",
    interests: user?.interests || [],
  };
}

/**
 * "Mon profil" (maquette Stitch n°11), fond blanc : en-tête avec
 * statistiques, album photo, "À propos de moi" éditable, centres
 * d'intérêt, mes Moments, vérification d'identité, compte.
 */
export default function Profile() {
  const { user, logout, refresh } = useAuth();
  const options = useProfileOptions();
  const [photos, setPhotos] = useState(user?.photos || []);
  const [form, setForm] = useState(() => toForm(user));
  const [videos, setVideos] = useState([]);
  const [saving, setSaving] = useState(false);
  const [uploadingPhoto, setUploadingPhoto] = useState(false);
  const [uploadingDoc, setUploadingDoc] = useState(false);
  const [error, setError] = useState("");
  const [toast, showToast] = useToast();
  const photoInputRef = useRef(null);
  // Appareil photo (selfie) : sur mobile, ouvre directement la caméra frontale.
  const cameraInputRef = useRef(null);
  const docInputRef = useRef(null);

  useEffect(() => {
    setPhotos(user?.photos || []);
    setForm(toForm(user));
  }, [user]);

  useEffect(() => {
    if (!user) return;
    apiClient.get(`/users/${user.id}/videos`).then((r) => setVideos(r.data)).catch(() => {});
  }, [user?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  // Une vidéo en cours de traitement (compression + floutage) ? On
  // rafraîchit "Mes Moments" toutes les 3 s jusqu'à la fin.
  const hasProcessing = videos.some((v) => v.status === "processing");
  useEffect(() => {
    if (!hasProcessing || !user) return;
    const t = setInterval(() => {
      apiClient.get(`/users/${user.id}/videos`).then((r) => setVideos(r.data)).catch(() => {});
    }, 3000);
    return () => clearInterval(t);
  }, [hasProcessing, user]);

  // Lien "Vérifier mon identité" depuis la page de publication : défile
  // jusqu'à la section vérification.
  useEffect(() => {
    const target = { "#verification": "verification", "#moments": "moments" }[window.location.hash];
    if (target) document.getElementById(target)?.scrollIntoView({ behavior: "smooth" });
  }, []);

  const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }));
  const toggleInterest = (i) =>
    setForm((f) => {
      if (f.interests.includes(i)) return { ...f, interests: f.interests.filter((x) => x !== i) };
      if (f.interests.length >= MAX_INTERESTS) return f;
      return { ...f, interests: [...f.interests, i] };
    });

  const dirty = JSON.stringify(form) !== JSON.stringify(toForm(user));

  const save = async () => {
    setSaving(true);
    setError("");
    try {
      await apiClient.put("/me/profile", {
        ...form,
        relationship_goal: form.relationship_goal || null,
        children: form.children || null,
      });
      await refresh();
      showToast("Profil enregistré ✨");
    } catch (err) {
      setError(extractErrorMessage(err, "Enregistrement impossible"));
    } finally {
      setSaving(false);
    }
  };

  const addPhoto = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setError("");
    setUploadingPhoto(true);
    try {
      const { url } = await uploadFile(file, "photo");
      const res = await apiClient.post("/me/photos", { url, is_primary: photos.length === 0 });
      setPhotos((prev) => [...prev, res.data]);
    } catch (err) {
      setError(extractErrorMessage(err, "Échec de l'envoi de la photo"));
    } finally {
      setUploadingPhoto(false);
      e.target.value = "";
    }
  };

  const removePhoto = async (photoId) => {
    try {
      await apiClient.delete(`/me/photos/${photoId}`);
      setPhotos((prev) => prev.filter((p) => p.id !== photoId));
    } catch {
      setError("Impossible de supprimer la photo");
    }
  };

  const submitDocument = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setError("");
    setUploadingDoc(true);
    try {
      const { key } = await uploadFile(file, "document");
      await apiClient.post("/me/verification/submit", { document_key: key });
      await refresh();
      showToast("Pièce d'identité envoyée 🛡️");
    } catch (err) {
      setError(extractErrorMessage(err, "Échec de l'envoi de la pièce d'identité"));
    } finally {
      setUploadingDoc(false);
      e.target.value = "";
    }
  };

  if (!user) return null;
  const status = STATUS_LABEL[user.verification_status] || STATUS_LABEL.unverified;
  const totalViews = videos.reduce((sum, v) => sum + (v.views_count || 0), 0);
  const totalLikes = videos.reduce((sum, v) => sum + (v.likes_count || 0), 0);

  return (
    <div className="flex min-h-[100dvh] flex-col bg-white font-display text-ink">
      <header className="flex items-center justify-between px-5 pb-2 pt-5">
        <h1 className="text-2xl font-extrabold">Mon profil</h1>
        <Link to={`/profils/${user.id}`} className="text-sm font-bold text-primary">Aperçu</Link>
      </header>

      <main className="flex-1 px-5 pb-8">
        {/* En-tête : avatar + nom + statut + stats */}
        <div className="mt-2 flex items-center gap-4">
          <div className="rounded-full bg-brand p-[3px]">
            <ProfilePhoto profile={{ ...user, photos }} className="h-20 w-20 rounded-full ring-4 ring-white" />
          </div>
          <div className="min-w-0">
            <p className="flex items-center gap-1 truncate text-xl font-extrabold">
              {user.full_name}
              {user.verification_status === "verified" && <VerifiedBadge className="text-xl" />}
            </p>
            <span className={`mt-1 inline-block rounded-full px-2.5 py-1 text-[11px] font-bold ${status.className}`}>{status.text}</span>
          </div>
        </div>
        <div className="mt-5 grid grid-cols-3 rounded-2xl bg-slate-50 py-3 text-center">
          <Stat value={videos.length} label="Moments" />
          <Stat value={totalViews} label="Vues" />
          <Stat value={totalLikes} label="J'aime" />
        </div>

        {error && <p className="mt-4 rounded-2xl bg-red-50 px-4 py-3 text-sm font-semibold text-red-600">{error}</p>}

        {/* Album photo */}
        <section className="mt-8">
          <h2 className="section-title">Mes photos</h2>
          <div className="grid grid-cols-3 gap-2">
            {photos.map((p) => (
              <div key={p.id} className="relative aspect-[3/4] overflow-hidden rounded-2xl bg-slate-100">
                <img src={p.url} alt="" className="h-full w-full object-cover" />
                <span className="absolute bottom-1.5 left-1.5 rounded-full bg-white/90 px-2 py-0.5 text-[10px] font-bold text-slate-600">
                  {PHOTO_STATUS_LABEL[p.status] || p.status}
                </span>
                <button
                  onClick={() => removePhoto(p.id)}
                  aria-label="Supprimer la photo"
                  className="absolute right-1.5 top-1.5 flex h-7 w-7 items-center justify-center rounded-full bg-white/90 text-primary shadow"
                >
                  <span className="material-symbols-outlined text-base">delete</span>
                </button>
              </div>
            ))}
            <button
              onClick={() => photoInputRef.current?.click()}
              disabled={uploadingPhoto}
              className="flex aspect-[3/4] flex-col items-center justify-center gap-1 rounded-2xl border-2 border-dashed border-slate-200 text-slate-400 transition hover:border-primary hover:text-primary"
            >
              <span className="material-symbols-outlined">add_photo_alternate</span>
              <span className="text-xs font-semibold">{uploadingPhoto ? "Envoi…" : "Ajouter"}</span>
            </button>
            <button
              onClick={() => cameraInputRef.current?.click()}
              disabled={uploadingPhoto}
              className="flex aspect-[3/4] flex-col items-center justify-center gap-1 rounded-2xl border-2 border-dashed border-slate-200 text-slate-400 transition hover:border-primary hover:text-primary"
            >
              <span className="material-symbols-outlined">photo_camera</span>
              <span className="text-xs font-semibold">Prendre</span>
            </button>
            <input ref={photoInputRef} type="file" accept="image/*" hidden onChange={addPhoto} />
            <input ref={cameraInputRef} type="file" accept="image/*" capture="user" hidden onChange={addPhoto} />
          </div>
          <p className="mt-2 text-xs text-slate-400">
            Chaque photo est contrôlée par IA avant publication : votre visage doit être visible, tenue correcte, rien de
            trop suggestif. En cas de doute, un modérateur humain décide.
          </p>
        </section>

        {/* À propos de moi */}
        <section className="mt-8 space-y-4">
          <h2 className="section-title">À propos de moi</h2>
          <Field label="Nom affiché"><input value={form.full_name} onChange={set("full_name")} maxLength={100} className="input" /></Field>
          <Field label={`Ma bio (${form.bio.length}/500)`}>
            <textarea value={form.bio} onChange={set("bio")} maxLength={500} rows={4} placeholder="Ce qui vous fait vibrer, ce que vous cherchez…" className="textarea" />
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Ville"><input value={form.city} onChange={set("city")} maxLength={80} placeholder="Ex. Abidjan" className="input" /></Field>
            <Field label="Pays"><input value={form.country} onChange={set("country")} maxLength={80} placeholder="Ex. Côte d'Ivoire" className="input" /></Field>
          </div>
          <Field label="Profession"><input value={form.profession} onChange={set("profession")} maxLength={80} placeholder="Ex. Infirmière" className="input" /></Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Je recherche">
              <select value={form.relationship_goal} onChange={set("relationship_goal")} className="input select">
                <option value="">—</option>
                {options?.relationship_goals.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
            </Field>
            <Field label="Enfants">
              <select value={form.children} onChange={set("children")} className="input select">
                <option value="">—</option>
                {options?.children.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
            </Field>
          </div>
        </section>

        {/* Centres d'intérêt */}
        <section className="mt-8">
          <h2 className="section-title">Mes centres d'intérêt ({form.interests.length}/{MAX_INTERESTS})</h2>
          <div className="flex flex-wrap gap-2">
            {options?.interests.map((i) => {
              const active = form.interests.includes(i);
              return (
                <button key={i} type="button" onClick={() => toggleInterest(i)} className={`chip ${active ? "chip-active" : ""}`}>
                  {i}
                  <span className="material-symbols-outlined text-base">{active ? "close" : "add"}</span>
                </button>
              );
            })}
          </div>
        </section>

        {/* Mes Moments */}
        <section id="moments" className="mt-8">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="section-title mb-0">Mes Moments</h2>
            <Link to="/moments/publier" className="flex items-center gap-1 text-sm font-bold text-primary">
              <span className="material-symbols-outlined text-lg">add_circle</span> Publier
            </Link>
          </div>
          <VideoGrid videos={videos} emptyText="Publiez votre premier Moment pour vous faire remarquer ✨" />
          <p className="mt-2 text-xs text-slate-400">
            🔒 Sur vos vidéos, votre visage est flouté pour tout le monde (le reste reste visible). Seuls vos matchs et les membres vérifiés que vous
            acceptez les voient en clair.
          </p>
        </section>

        <VideoAccessRequests mode="accepted" />

        {/* Vérification d'identité */}
        <section id="verification" className="mt-8 rounded-3xl bg-gradient-to-br from-sky-50 to-white p-5 ring-1 ring-sky-100">
          <div className="flex items-center gap-3">
            <VerifiedBadge className="text-3xl" />
            <h2 className="text-base font-extrabold">Vérification d'identité</h2>
          </div>
          {user.verification_status === "verified" ? (
            <p className="mt-2 text-sm text-slate-600">
              Votre identité est vérifiée : le badge s'affiche sur votre profil et vous pouvez publier des Moments.
            </p>
          ) : (
            <>
              <p className="mt-2 text-sm text-slate-600">
                Envoyez une photo de votre pièce d'identité (CNI, passeport ou permis) pour obtenir le badge et
                publier des vidéos. Elle n'est jamais visible par les autres membres.
              </p>
              <button
                onClick={() => docInputRef.current?.click()}
                disabled={uploadingDoc || user.verification_status === "pending"}
                className="btn-primary mt-4 w-full"
              >
                {uploadingDoc ? "Envoi…" : user.verification_status === "pending" ? "Vérification en cours…" : "Envoyer ma pièce d'identité"}
              </button>
              <input ref={docInputRef} type="file" accept="image/*" hidden onChange={submitDocument} />
            </>
          )}
        </section>

        {/* Compte */}
        <section className="mt-8">
          <h2 className="section-title">Mon compte</h2>
          <div className="card divide-y divide-slate-100">
            <AccountRow to="/abonnement" icon="workspace_premium" label="Abonnement Premium" />
            <AccountRow to="/portefeuille" icon="account_balance_wallet" label="Portefeuille" />
            <AccountRow to="/parrainage" icon="stars" label="Points de parrainage" value={user.points ?? 0} />
            <AccountRow to="/matchs" icon="local_fire_department" label="Mes matchs" />
          </div>
          <button onClick={logout} className="mt-4 w-full py-3 text-sm font-bold text-slate-400 hover:text-red-500">
            Se déconnecter
          </button>
        </section>
      </main>

      {/* Bouton d'enregistrement flottant, visible dès qu'un champ change */}
      {dirty && (
        <div className="sticky bottom-[72px] z-30 px-5 pb-3">
          <button onClick={save} disabled={saving} className="btn-primary w-full shadow-2xl">
            {saving ? "Enregistrement…" : "Enregistrer les modifications"}
          </button>
        </div>
      )}

      <BottomNav />
      <Toast message={toast} />
    </div>
  );
}

function Stat({ value, label }) {
  return (
    <div>
      <p className="text-lg font-extrabold">{value}</p>
      <p className="text-[11px] font-semibold text-slate-400">{label}</p>
    </div>
  );
}

function Field({ label, children }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-xs font-bold text-slate-500">{label}</span>
      {children}
    </label>
  );
}

function AccountRow({ to, icon, label, value }) {
  return (
    <Link to={to} className="flex items-center gap-3 px-4 py-3.5">
      <span className="flex h-9 w-9 items-center justify-center rounded-full bg-primary/10 text-primary">
        <span className="material-symbols-outlined text-xl">{icon}</span>
      </span>
      <span className="flex-1 text-sm font-semibold">{label}</span>
      {value !== undefined && <span className="text-sm font-extrabold text-primary">{value}</span>}
      <span className="material-symbols-outlined text-slate-300">chevron_right</span>
    </Link>
  );
}
