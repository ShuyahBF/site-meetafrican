import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { apiClient, extractErrorMessage } from "@/lib/api";

const PLATFORMS = [
  { key: "whatsapp", label: "WhatsApp", icon: "chat" },
  { key: "facebook", label: "Facebook", icon: "thumb_up" },
  { key: "instagram", label: "Instagram", icon: "photo_camera" },
  { key: "tiktok", label: "TikTok", icon: "music_note" },
];

const SHARE_MESSAGE = "Rejoins-moi sur MeetAfrican, le site de rencontre africain ! 💕";

export default function Referrals() {
  const [data, setData] = useState(null);
  const [busyPlatform, setBusyPlatform] = useState(null);
  const [notice, setNotice] = useState("");

  const load = () => {
    apiClient.get("/me/referrals").then((r) => setData(r.data));
  };

  useEffect(load, []);

  const handleShare = async (platform) => {
    if (!data) return;
    const encodedText = encodeURIComponent(`${SHARE_MESSAGE} ${data.referral_link}`);

    if (platform === "whatsapp") {
      window.open(`https://wa.me/?text=${encodedText}`, "_blank");
    } else if (platform === "facebook") {
      window.open(`https://www.facebook.com/sharer/sharer.php?u=${encodeURIComponent(data.referral_link)}`, "_blank");
    } else {
      try {
        await navigator.clipboard.writeText(`${SHARE_MESSAGE} ${data.referral_link}`);
        setNotice("Lien copié — collez-le dans votre story ou votre bio.");
      } catch {
        setNotice("Copiez ce lien : " + data.referral_link);
      }
    }

    setBusyPlatform(platform);
    try {
      await apiClient.post("/me/referrals/share", { platform });
      load();
    } catch (err) {
      setNotice(extractErrorMessage(err, "Partage non comptabilisé"));
    } finally {
      setBusyPlatform(null);
    }
  };

  if (!data) return null;

  return (
    <div className="min-h-screen bg-background-light px-4 py-6 font-display dark:bg-background-dark">
      <Link to="/profil" className="text-slate-500 dark:text-slate-400">
        <span className="material-symbols-outlined align-middle">arrow_back</span>
      </Link>

      <h1 className="mt-3 text-2xl font-bold text-slate-900 dark:text-white">Parrainage</h1>
      <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
        Partagez MeetAfrican et gagnez des points à chaque partage.
      </p>

      <div className="mt-4 rounded-xl bg-primary/10 p-4 text-center">
        <p className="text-3xl font-bold text-primary">{data.points}</p>
        <p className="text-sm text-slate-600 dark:text-slate-300">points cumulés</p>
      </div>

      <div className="mt-6 grid grid-cols-2 gap-3">
        {PLATFORMS.map((p) => (
          <button
            key={p.key}
            onClick={() => handleShare(p.key)}
            disabled={busyPlatform === p.key}
            className="flex flex-col items-center gap-2 rounded-xl border border-slate-300 py-4 disabled:opacity-50 dark:border-white/10"
          >
            <span className="material-symbols-outlined text-2xl text-primary">{p.icon}</span>
            <span className="text-sm font-semibold text-slate-800 dark:text-white">{p.label}</span>
          </button>
        ))}
      </div>

      {notice && <p className="mt-3 text-sm text-slate-500 dark:text-slate-400">{notice}</p>}

      <p className="mt-6 break-all text-xs text-slate-400">{data.referral_link}</p>

      {data.history.length > 0 && (
        <div className="mt-6">
          <h2 className="text-sm font-bold uppercase tracking-wide text-slate-500 dark:text-slate-400">
            Historique
          </h2>
          <ul className="mt-2 flex flex-col divide-y divide-slate-800/10 dark:divide-white/10">
            {data.history.map((h) => (
              <li key={h.id} className="flex items-center justify-between py-2 text-sm">
                <span className="capitalize text-slate-700 dark:text-slate-200">{h.platform}</span>
                <span className="font-semibold text-primary">+{h.points_awarded}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
