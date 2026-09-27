import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { apiClient, extractErrorMessage } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import VerifiedBadge from "@/components/VerifiedBadge";

// Limites alignées sur le backend (config.py : max_video_*) ; le serveur
// revérifie de toute façon.
const MAX_DURATION_S = 60;
const MAX_SIZE_MB = 50;
const CAPTION_MAX = 300;
// Suggestions de hashtags si aucune tendance n'existe encore.
const DEFAULT_TAGS = ["abidjan", "dakar", "ouaga", "diaspora", "danse", "cuisine", "afrobeat", "love"];

/**
 * Page BLANCHE de publication d'un "Moment" (vidéo courte) :
 * choix/filmage de la vidéo -> aperçu en boucle -> légende + #hashtags en
 * un tap -> envoi avec barre de progression -> retour au fil.
 * Réservée aux identités vérifiées (gage d'authenticité du fil).
 */
export default function PublishVideo() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const inputRef = useRef(null);
  const [file, setFile] = useState(null);
  const [previewUrl, setPreviewUrl] = useState("");
  const [duration, setDuration] = useState(null);
  const [caption, setCaption] = useState("");
  const [tags, setTags] = useState(DEFAULT_TAGS);
  const [progress, setProgress] = useState(0);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");

  const verified = user?.verification_status === "verified";

  // Hashtags tendance du moment (sinon suggestions par défaut).
  useEffect(() => {
    apiClient
      .get("/videos/trending-tags")
      .then((r) => r.data.length && setTags(r.data.map((t) => t.tag)))
      .catch(() => {});
  }, []);

  // Libère l'URL d'aperçu locale quand on change de fichier / quitte la page.
  useEffect(() => () => previewUrl && URL.revokeObjectURL(previewUrl), [previewUrl]);

  const pickFile = (e) => {
    const f = e.target.files?.[0];
    e.target.value = "";
    if (!f) return;
    setError("");
    if (f.size > MAX_SIZE_MB * 1024 * 1024) {
      setError(`Vidéo trop lourde (${MAX_SIZE_MB} Mo max). Raccourcissez-la ou filmez en qualité standard.`);
      return;
    }
    setDuration(null);
    setFile(f);
    setPreviewUrl(URL.createObjectURL(f));
  };

  // Durée lue sur les métadonnées de l'aperçu — contrôle avant envoi.
  const onMetadata = (e) => {
    const d = e.currentTarget.duration;
    if (Number.isFinite(d)) {
      setDuration(d);
      if (d > MAX_DURATION_S + 1) setError(`Vidéo trop longue : ${Math.round(d)} s (${MAX_DURATION_S} s max).`);
    }
  };

  // Ajoute (ou retire) un #hashtag suggéré à la fin de la légende.
  const toggleTag = (t) => {
    const token = `#${t}`;
    setCaption((c) =>
      c.includes(token) ? c.replace(new RegExp(`\\s?${token}\\b`), "").trim() : `${c.trim()} ${token}`.trim().slice(0, CAPTION_MAX),
    );
  };

  const publish = async () => {
    if (!file || uploading || (duration && duration > MAX_DURATION_S + 1)) return;
    setUploading(true);
    setError("");
    setProgress(0);
    const form = new FormData();
    form.append("file", file);
    form.append("caption", caption.trim());
    if (duration) form.append("duration_seconds", String(duration));
    try {
      const res = await apiClient.post("/videos", form, {
        headers: { "Content-Type": "multipart/form-data" },
        onUploadProgress: (ev) => ev.total && setProgress(Math.round((ev.loaded / ev.total) * 100)),
      });
      // La vidéo est compressée + floutée en arrière-plan : on renvoie vers
      // "Mes Moments", où elle apparaît "Traitement…" puis publiée.
      if (res.data.id) navigate("/profil#moments", { replace: true });
    } catch (err) {
      setError(extractErrorMessage(err, "La publication a échoué, réessayez."));
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="min-h-[100dvh] bg-white font-display text-ink">
      <header className="sticky top-0 z-10 flex items-center justify-between bg-white/90 px-4 py-4 backdrop-blur">
        <button onClick={() => navigate(-1)} aria-label="Retour" className="flex h-10 w-10 items-center justify-center rounded-full bg-slate-100">
          <span className="material-symbols-outlined">close</span>
        </button>
        <h1 className="text-base font-extrabold">Nouveau Moment</h1>
        <span className="w-10" />
      </header>

      {!verified ? (
        // Portail d'authenticité : on explique pourquoi et comment débloquer.
        <main className="mx-auto max-w-md px-6 pt-10 text-center">
          <div className="mx-auto flex h-24 w-24 items-center justify-center rounded-full bg-sky-50">
            <VerifiedBadge className="text-6xl" />
          </div>
          <h2 className="mt-6 text-2xl font-extrabold">Vérifiez votre identité pour publier</h2>
          <p className="mt-3 text-sm leading-relaxed text-slate-500">
            Sur bAuthentik, chaque vidéo vient d'une personne réelle. Envoyez votre pièce d'identité : le badge
            <VerifiedBadge className="mx-1 text-sm" /> s'affichera sur votre profil et vos Moments.
          </p>
          {user?.verification_status === "pending" ? (
            <p className="mt-6 rounded-2xl bg-amber-50 px-4 py-3 text-sm font-semibold text-amber-700">
              ⏳ Votre vérification est en cours d'examen.
            </p>
          ) : (
            <Link to="/profil#verification" className="btn-primary mt-8 w-full">
              Vérifier mon identité
            </Link>
          )}
        </main>
      ) : (
        <main className="mx-auto max-w-md px-4 pb-10">
          {/* Zone vidéo : aperçu ou invitation à choisir */}
          {previewUrl ? (
            <div className="relative mx-auto aspect-[9/16] max-h-[60dvh] overflow-hidden rounded-[1.75rem] bg-black shadow-xl">
              <video src={previewUrl} className="h-full w-full object-cover" autoPlay loop muted playsInline onLoadedMetadata={onMetadata} />
              {duration && (
                <span className="glass absolute left-3 top-3 rounded-full px-2.5 py-1 text-xs font-bold text-white">
                  {Math.round(duration)} s
                </span>
              )}
              <button onClick={() => inputRef.current?.click()} className="glass absolute bottom-3 right-3 rounded-full px-3 py-1.5 text-xs font-bold text-white">
                Changer
              </button>
            </div>
          ) : (
            <button
              onClick={() => inputRef.current?.click()}
              className="flex aspect-[9/16] max-h-[60dvh] w-full flex-col items-center justify-center gap-4 rounded-[1.75rem] border-2 border-dashed border-primary/30 bg-gradient-to-b from-primary/5 to-sunset/5 transition active:scale-[0.99]"
            >
              <span className="flex h-20 w-20 items-center justify-center rounded-full bg-brand text-white shadow-lg shadow-primary/30">
                <span className="material-symbols-outlined text-4xl">videocam</span>
              </span>
              <span className="text-lg font-extrabold">Filmer ou choisir une vidéo</span>
              <span className="text-xs text-slate-500">{MAX_DURATION_S} secondes max · MP4, MOV ou WebM</span>
            </button>
          )}
          <input ref={inputRef} type="file" accept="video/mp4,video/quicktime,video/webm,video/*" hidden onChange={pickFile} />

          {/* Légende */}
          <div className="mt-6">
            <label className="section-title block" htmlFor="caption">Légende</label>
            <textarea
              id="caption"
              value={caption}
              onChange={(e) => setCaption(e.target.value.slice(0, CAPTION_MAX))}
              rows={3}
              placeholder="Présentez-vous, racontez votre journée… #hashtags"
              className="textarea"
            />
            <p className="mt-1 text-right text-xs text-slate-400">{caption.length}/{CAPTION_MAX}</p>
          </div>

          {/* Hashtags en un tap */}
          <div className="no-scrollbar -mx-4 flex gap-2 overflow-x-auto px-4 pb-1">
            {tags.map((t) => (
              <button key={t} onClick={() => toggleTag(t)} className={`chip shrink-0 ${caption.includes(`#${t}`) ? "chip-active" : ""}`}>
                #{t}
              </button>
            ))}
          </div>

          <p className="mt-4 flex gap-2 rounded-2xl bg-slate-50 px-4 py-3 text-xs leading-relaxed text-slate-500">
            <span className="material-symbols-outlined icon-filled text-base text-primary">lock</span>
            Votre vidéo sera compressée et entièrement floutée pour tous. Seuls vos matchs et les membres vérifiés
            que vous acceptez la verront en clair.
          </p>

          {error && <p className="mt-4 rounded-2xl bg-red-50 px-4 py-3 text-sm font-semibold text-red-600">{error}</p>}

          {uploading && (
            <div className="mt-6">
              <div className="h-2 overflow-hidden rounded-full bg-slate-100">
                <div className="h-full bg-brand transition-all" style={{ width: `${progress}%` }} />
              </div>
              <p className="mt-1 text-center text-xs font-semibold text-slate-500">Envoi… {progress}%</p>
            </div>
          )}

          <button onClick={publish} disabled={!file || uploading || (duration && duration > MAX_DURATION_S + 1)} className="btn-primary mt-6 w-full">
            <span className="material-symbols-outlined text-lg">rocket_launch</span>
            {uploading ? "Publication…" : "Publier"}
          </button>
        </main>
      )}
    </div>
  );
}
