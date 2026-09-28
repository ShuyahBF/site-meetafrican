import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { apiClient } from "@/lib/api";
import { formatDateTime } from "@/lib/format";

/**
 * Communauté : témoignages à relire (publier / refuser) et suivis
 * « Me suivre » en cours (position en direct accessible à l'équipe).
 */
export default function AdminCommunity() {
  const [testimonials, setTestimonials] = useState([]);
  const [tracking, setTracking] = useState([]);

  const load = () => {
    apiClient.get("/admin/testimonials", { params: { status: "pending" } }).then((r) => setTestimonials(r.data));
    apiClient.get("/admin/tracking").then((r) => setTracking(r.data));
  };
  useEffect(load, []);

  const review = async (t, approve) => {
    await apiClient.post(`/admin/testimonials/${t.id}/review`, null, { params: { approve } });
    load();
  };

  return (
    <div className="space-y-8">
      <section>
        <h1 className="text-2xl font-bold">Suivis « Me suivre » en cours</h1>
        <p className="mt-1 text-sm text-slate-500">Membres qui partagent leur position en direct (sécurité pendant un rendez-vous).</p>
        <div className="mt-3 space-y-2">
          {tracking.length === 0 && <p className="text-sm text-slate-500">Aucun suivi actif.</p>}
          {tracking.map((s) => (
            <Link key={s.id} to={`/suivi/${s.id}`} className="flex items-center justify-between rounded-xl bg-white p-4 shadow-sm">
              <span>
                <span className="block font-bold">{s.owner_name} → {s.guardian_name}</span>
                <span className="block text-xs text-slate-500">
                  Depuis le {formatDateTime(s.started_at)} · jusqu'au {formatDateTime(s.ends_at)}
                  {s.last_point ? ` · dernière position ${formatDateTime(s.last_point.at)}` : ""}
                </span>
              </span>
              <span className="text-sm font-bold text-primary">Voir la carte →</span>
            </Link>
          ))}
        </div>
      </section>

      <section>
        <h2 className="text-2xl font-bold">Témoignages à relire</h2>
        <div className="mt-3 space-y-3">
          {testimonials.length === 0 && <p className="text-sm text-slate-500">Aucun témoignage en attente.</p>}
          {testimonials.map((t) => (
            <div key={t.id} className="rounded-xl bg-white p-4 shadow-sm">
              <p className="text-xs text-slate-500">
                {t.author_name}{t.author_city ? `, ${t.author_city}` : ""} · {"★".repeat(t.rating)} · envoyé le {formatDateTime(t.created_at)}
              </p>
              <p className="mt-2 whitespace-pre-wrap text-sm">{t.text}</p>
              <div className="mt-3 flex gap-2">
                <button onClick={() => review(t, true)} className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-bold text-white">Publier</button>
                <button onClick={() => review(t, false)} className="rounded-lg bg-red-600 px-4 py-2 text-sm font-bold text-white">Refuser</button>
              </div>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
