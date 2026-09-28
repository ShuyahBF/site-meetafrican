import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { apiClient, extractErrorMessage } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import PageShell from "@/components/PageShell";

const REFRESH_MS = 10000;

/** Carte OpenStreetMap intégrée, centrée sur la position (sans bibliothèque). */
function OsmMap({ lat, lng }) {
  const d = 0.008; // ~1 km autour du point
  const src = `https://www.openstreetmap.org/export/embed.html?bbox=${lng - d}%2C${lat - d}%2C${lng + d}%2C${lat + d}&layer=mapnik&marker=${lat}%2C${lng}`;
  return <iframe title="Position en direct" src={src} className="h-72 w-full rounded-2xl border-0 ring-1 ring-slate-200" loading="lazy" />;
}

/**
 * Vue du compte désigné (ou de l'équipe) : position en direct d'un membre
 * qui a activé « Me suivre », rafraîchie toutes les 10 s, avec le trajet
 * horodaté.
 */
export default function TrackingView() {
  const { sessionId } = useParams();
  const [session, setSession] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    const load = () =>
      apiClient
        .get(`/tracking/sessions/${sessionId}`)
        .then((r) => setSession(r.data))
        .catch((err) => setError(extractErrorMessage(err, "Suivi introuvable")));
    load();
    const t = setInterval(load, REFRESH_MS);
    return () => clearInterval(t);
  }, [sessionId]);

  if (error) return <PageShell title="Suivi" back="/me-suivre"><p className="mt-6 text-sm text-slate-500">{error}</p></PageShell>;
  if (!session) return null;
  const p = session.last_point;
  const live = session.status === "active";

  return (
    <PageShell title={`Position de ${session.owner_name}`} subtitle={live ? "En direct · actualisé toutes les 10 s" : "Suivi terminé"} back="/me-suivre">
      {session.note && <p className="mt-2 rounded-xl bg-amber-50 px-3 py-2 text-sm text-amber-800">📝 {session.note}</p>}
      {p ? (
        <>
          <div className="mt-3">
            <OsmMap lat={p.lat} lng={p.lng} />
          </div>
          <p className="mt-2 text-sm">
            <span className="font-bold">Dernière position :</span> {formatDateTime(p.at)}
            {p.accuracy ? ` (précision ~${Math.round(p.accuracy)} m)` : ""}
          </p>
          <a
            href={`https://www.google.com/maps?q=${p.lat},${p.lng}`}
            target="_blank"
            rel="noreferrer"
            className="btn-primary mt-3 w-full"
          >
            <span className="material-symbols-outlined text-lg">map</span> Ouvrir dans Google Maps
          </a>
        </>
      ) : (
        <p className="mt-6 text-sm text-slate-500">En attente de la première position…</p>
      )}
      <p className="mt-3 text-xs text-slate-500">
        Suivi démarré le {formatDateTime(session.started_at)} · {live ? `jusqu'au ${formatDateTime(session.ends_at)}` : "terminé"}
      </p>

      {session.points.length > 1 && (
        <section className="mt-5">
          <h2 className="section-title">Trajet ({session.points.length} positions)</h2>
          <ul className="space-y-1 text-xs text-slate-600">
            {[...session.points].reverse().slice(0, 30).map((pt) => (
              <li key={pt.at} className="flex justify-between rounded-lg bg-slate-50 px-3 py-1.5">
                <span>{formatDateTime(pt.at)}</span>
                <a className="font-semibold text-primary" href={`https://www.google.com/maps?q=${pt.lat},${pt.lng}`} target="_blank" rel="noreferrer">
                  {pt.lat.toFixed(5)}, {pt.lng.toFixed(5)}
                </a>
              </li>
            ))}
          </ul>
        </section>
      )}
    </PageShell>
  );
}
