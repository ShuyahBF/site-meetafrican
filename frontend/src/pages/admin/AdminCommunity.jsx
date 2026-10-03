import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { apiClient, FOND } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { etatSignal, useMaintenant } from "@/lib/suivi";

// Libellés de l'historique des alertes de suivi (lot 53)
const TYPES_ALERTE = {
  signal_perdu: { texte: "Signal perdu", classes: "bg-rose-100 text-rose-700" },
  signal_retabli: { texte: "Signal rétabli", classes: "bg-emerald-100 text-emerald-700" },
  arrivee: { texte: "Bien arrivé·e", classes: "bg-sky-100 text-sky-700" },
};

/**
 * Communauté : témoignages à relire (publier / refuser) et suivis
 * « Me suivre » en cours (position en direct accessible à l'équipe).
 */
export default function AdminCommunity() {
  const [testimonials, setTestimonials] = useState([]);
  const [tracking, setTracking] = useState([]);
  const [alertes, setAlertes] = useState([]);
  const maintenant = useMaintenant();

  // Suivis en cours et alertes : relus toutes les 20 s (requêtes de fond)
  const chargerSuivis = () => {
    apiClient.get("/admin/tracking", FOND).then((r) => setTracking(r.data)).catch(() => {});
    apiClient.get("/admin/tracking/alertes", FOND).then((r) => setAlertes(r.data)).catch(() => {});
  };
  const load = () => {
    apiClient.get("/admin/testimonials", { params: { status: "pending" } }).then((r) => setTestimonials(r.data));
    chargerSuivis();
  };
  useEffect(() => {
    load();
    const t = setInterval(chargerSuivis, 20000);
    return () => clearInterval(t);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

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
                {/* Lot 53 — état du signal et alerte en cours */}
                <span className={`mt-1 inline-block rounded-full px-2 py-0.5 text-[11px] font-bold ring-1 ${etatSignal(s, maintenant).classes}`}>
                  {etatSignal(s, maintenant).texte}
                </span>
                {s.alerte_signal && (
                  <span className="ml-2 text-[11px] font-bold text-rose-700">Alerte envoyée le {formatDateTime(s.alerte_signal.alerte_le)}</span>
                )}
              </span>
              <span className="text-sm font-bold text-primary">Voir la carte →</span>
            </Link>
          ))}
        </div>
      </section>

      {/* Lot 53 — historique des alertes de suivi (aussi envoyées par WhatsApp / SMS et e-mail) */}
      <section>
        <h2 className="text-xl font-bold">Alertes de suivi</h2>
        <p className="mt-1 text-sm text-slate-500">
          Signal perdu (aucune position depuis 10 min), signal rétabli et arrivées : envoyées à la personne de confiance et aux administrateurs.
        </p>
        <div className="mt-3 overflow-x-auto rounded-xl bg-white shadow-sm">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-50 text-xs uppercase text-slate-500">
              <tr><th className="px-3 py-2">Date</th><th className="px-3 py-2">Alerte</th><th className="px-3 py-2">Membre → confiance</th><th className="px-3 py-2">Message</th></tr>
            </thead>
            <tbody>
              {alertes.length === 0 && <tr><td colSpan={4} className="px-3 py-3 text-slate-500">Aucune alerte.</td></tr>}
              {alertes.map((a) => (
                <tr key={a.id} className="border-t border-slate-100">
                  <td className="whitespace-nowrap px-3 py-2">{formatDateTime(a.created_at)}</td>
                  <td className="px-3 py-2">
                    <span className={`rounded-full px-2 py-0.5 text-xs font-bold ${(TYPES_ALERTE[a.type] || {}).classes || "bg-slate-100"}`}>
                      {(TYPES_ALERTE[a.type] || {}).texte || a.type}
                    </span>
                  </td>
                  <td className="px-3 py-2">
                    <Link to={`/suivi/${a.session_id}`} className="font-semibold text-primary">{a.owner_name} → {a.guardian_name}</Link>
                  </td>
                  <td className="px-3 py-2 text-xs text-slate-600">{a.texte}</td>
                </tr>
              ))}
            </tbody>
          </table>
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
