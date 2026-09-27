import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { apiClient } from "@/lib/api";
import VerifiedBadge from "@/components/VerifiedBadge";

/**
 * Gestion des accès "Voir mes Moments en clair" (mes vidéos sont floutées
 * pour tout le monde, sauf pour les membres vérifiés que j'accepte).
 *   mode="pending"  -> demandes reçues à accepter / refuser (boîte de réception) ;
 *   mode="accepted" -> membres déjà autorisés, avec "Retirer" (Mon profil).
 * N'affiche rien s'il n'y a rien à montrer.
 */
export default function VideoAccessRequests({ mode = "pending" }) {
  const [items, setItems] = useState([]);
  const [busyId, setBusyId] = useState(null);

  useEffect(() => {
    apiClient
      .get("/me/video-access/requests")
      .then((r) => setItems(r.data.filter((x) => x.status === mode)))
      .catch(() => {});
  }, [mode]);

  const decide = async (req, accept) => {
    setBusyId(req.id);
    try {
      await apiClient.post(`/me/video-access/requests/${req.id}`, { accept });
      setItems((prev) => prev.filter((x) => x.id !== req.id));
    } finally {
      setBusyId(null);
    }
  };

  if (!items.length) return null;

  return (
    <section className={mode === "pending" ? "mt-2 px-5" : "mt-8"}>
      <h2 className="section-title">
        {mode === "pending" ? "Demandes pour voir vos Moments en clair" : "Membres autorisés à voir mes Moments en clair"}
      </h2>
      <div className="card divide-y divide-slate-100">
        {items.map((req) => (
          <div key={req.id} className="flex items-center gap-3 px-4 py-3">
            <Link to={`/profils/${req.requester.id}`} className="h-11 w-11 shrink-0 overflow-hidden rounded-full bg-slate-100">
              {req.requester.avatar_url ? (
                <img src={req.requester.avatar_url} alt="" className="h-full w-full object-cover" />
              ) : (
                <span className="flex h-full w-full items-center justify-center bg-brand font-bold text-white">{req.requester.full_name[0]}</span>
              )}
            </Link>
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-extrabold">
                {req.requester.full_name} {req.requester.is_verified && <VerifiedBadge className="text-sm" />}
              </p>
              <p className="text-[11px] leading-tight text-slate-400">
                {mode === "pending" ? "veut voir vos Moments en clair" : [req.requester.city, req.requester.country].filter(Boolean).join(", ")}
              </p>
            </div>
            {mode === "pending" ? (
              <div className="flex shrink-0 gap-2">
                <button
                  onClick={() => decide(req, false)}
                  disabled={busyId === req.id}
                  aria-label="Refuser"
                  className="flex h-9 w-9 items-center justify-center rounded-full bg-slate-100 text-slate-500 disabled:opacity-50"
                >
                  <span className="material-symbols-outlined text-lg">close</span>
                </button>
                <button
                  onClick={() => decide(req, true)}
                  disabled={busyId === req.id}
                  className="flex h-9 items-center gap-1 rounded-full bg-brand px-3 text-xs font-bold text-white disabled:opacity-50"
                >
                  <span className="material-symbols-outlined text-base">check</span>
                  OK
                </button>
              </div>
            ) : (
              <button
                onClick={() => decide(req, false)}
                disabled={busyId === req.id}
                className="shrink-0 text-xs font-bold text-slate-400 hover:text-red-500 disabled:opacity-50"
              >
                Retirer
              </button>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}
