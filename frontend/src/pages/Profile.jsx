import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { apiClient, extractErrorMessage } from "@/lib/api";
import { uploadFile } from "@/lib/upload";
import { useAuth } from "@/context/AuthContext";
import BottomNav from "@/components/BottomNav";

const STATUS_LABEL = {
  unverified: { text: "Non vérifié", color: "text-slate-400" },
  pending: { text: "En cours de vérification", color: "text-amber-400" },
  verified: { text: "Identité vérifiée", color: "text-emerald-400" },
  rejected: { text: "Vérification refusée", color: "text-red-400" },
};

const PHOTO_STATUS_LABEL = {
  pending: "En attente",
  approved: "Approuvée",
  rejected: "Refusée",
  needs_review: "En revue",
};

export default function Profile() {
  const { user, logout, refresh } = useAuth();
  const [photos, setPhotos] = useState(user?.photos || []);
  const [uploadingPhoto, setUploadingPhoto] = useState(false);
  const [uploadingDoc, setUploadingDoc] = useState(false);
  const [error, setError] = useState("");
  const photoInputRef = useRef(null);
  const docInputRef = useRef(null);

  useEffect(() => {
    setPhotos(user?.photos || []);
  }, [user]);

  const addPhoto = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setError("");
    setUploadingPhoto(true);
    try {
      const { url } = await uploadFile(file);
      const res = await apiClient.post("/me/photos", { url });
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
      const { url } = await uploadFile(file);
      await apiClient.post("/me/verification/submit", { document_url: url });
      await refresh();
    } catch (err) {
      setError(extractErrorMessage(err, "Échec de l'envoi de la pièce d'identité"));
    } finally {
      setUploadingDoc(false);
      e.target.value = "";
    }
  };

  const statusInfo = STATUS_LABEL[user?.verification_status] || STATUS_LABEL.unverified;

  return (
    <div className="flex min-h-screen flex-col bg-background-light font-display dark:bg-background-dark">
      <header className="flex items-center justify-between px-4 py-4">
        <h1 className="text-xl font-bold text-slate-900 dark:text-white">Mon profil</h1>
        <button onClick={logout} className="text-sm text-slate-500 dark:text-slate-400">Déconnexion</button>
      </header>

      <main className="flex-1 px-4 pb-6">
        <p className="text-lg font-bold text-slate-900 dark:text-white">{user?.full_name}</p>
        <p className={`text-sm font-semibold ${statusInfo.color}`}>{statusInfo.text}</p>
        {error && <p className="mt-2 text-sm text-red-400">{error}</p>}

        <Link
          to="/parrainage"
          className="mt-4 flex items-center justify-between rounded-xl bg-primary/10 px-4 py-3"
        >
          <span className="text-sm font-semibold text-slate-800 dark:text-white">Points de parrainage</span>
          <span className="flex items-center gap-1 font-bold text-primary">
            {user?.points ?? 0}
            <span className="material-symbols-outlined text-base">chevron_right</span>
          </span>
        </Link>

        <section className="mt-6">
          <h2 className="mb-3 text-sm font-bold uppercase tracking-wide text-slate-500 dark:text-slate-400">
            Album photo
          </h2>
          <div className="grid grid-cols-3 gap-2">
            {photos.map((p) => (
              <div key={p.id} className="relative aspect-square overflow-hidden rounded-xl bg-slate-800/10">
                <img src={p.url} alt="" className="h-full w-full object-cover" />
                <span className="absolute bottom-1 left-1 rounded-full bg-black/60 px-2 py-0.5 text-[10px] font-semibold text-white">
                  {PHOTO_STATUS_LABEL[p.status] || p.status}
                </span>
                <button
                  onClick={() => removePhoto(p.id)}
                  className="absolute right-1 top-1 flex h-6 w-6 items-center justify-center rounded-full bg-black/60 text-white"
                >
                  <span className="material-symbols-outlined text-sm">close</span>
                </button>
              </div>
            ))}
            <button
              onClick={() => photoInputRef.current?.click()}
              disabled={uploadingPhoto}
              className="flex aspect-square flex-col items-center justify-center gap-1 rounded-xl border-2 border-dashed border-slate-300 text-slate-400 dark:border-white/20"
            >
              <span className="material-symbols-outlined">add_a_photo</span>
              <span className="text-xs">{uploadingPhoto ? "Envoi…" : "Ajouter"}</span>
            </button>
            <input ref={photoInputRef} type="file" accept="image/*" hidden onChange={addPhoto} />
          </div>
          <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">
            Chaque photo est analysée automatiquement avant publication ; en cas de doute, une modération humaine prend le relai.
          </p>
        </section>

        <section className="mt-8">
          <h2 className="mb-3 text-sm font-bold uppercase tracking-wide text-slate-500 dark:text-slate-400">
            Vérification d'identité
          </h2>
          <p className="text-sm text-slate-600 dark:text-slate-300">
            Pour confirmer votre profil, envoyez une photo de votre pièce d'identité
            (carte nationale, passeport ou permis).
          </p>
          <button
            onClick={() => docInputRef.current?.click()}
            disabled={uploadingDoc}
            className="mt-3 h-12 w-full rounded-full bg-primary text-sm font-bold text-white disabled:opacity-50"
          >
            {uploadingDoc ? "Envoi…" : "Envoyer ma pièce d'identité"}
          </button>
          <input ref={docInputRef} type="file" accept="image/*" hidden onChange={submitDocument} />
        </section>
      </main>

      <BottomNav />
    </div>
  );
}
