import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { apiClient, extractErrorMessage } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import PageShell from "@/components/PageShell";

const DURATIONS = [
  { value: 30, label: "30 minutes" },
  { value: 60, label: "1 heure" },
  { value: 120, label: "2 heures" },
  { value: 240, label: "4 heures" },
  { value: 480, label: "8 heures" },
  { value: 720, label: "12 heures" },
];

/** Prévient l'émetteur (TrackingBeacon) qu'un suivi a démarré ou s'est arrêté. */
const notifyBeacon = () => window.dispatchEvent(new Event("tracking:changed"));

/**
 * « Me suivre » : partager sa position en temps réel avec un compte
 * beAuthentik de confiance (et l'équipe beAuthentik), pour une durée
 * choisie — par exemple pendant un premier rendez-vous.
 * Affiche aussi les suivis que d'autres membres partagent avec moi.
 */
export default function FollowMe() {
  const [params] = useSearchParams();
  const [data, setData] = useState({ mine: [], watching: [] });
  const [contacts, setContacts] = useState([]);
  const [form, setForm] = useState({ guardian_id: params.get("guardian") || "", guardian_email: "", duration_minutes: 120, note: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const load = () => apiClient.get("/tracking/me").then((r) => setData(r.data));
  useEffect(() => {
    load();
    // Mes matchs = contacts proposés (on peut aussi saisir un email)
    apiClient.get("/conversations").then((r) => setContacts(r.data.map((c) => c.other_user)));
    const t = setInterval(load, 15000);
    return () => clearInterval(t);
  }, []);

  const active = data.mine.find((s) => s.status === "active");

  // Démarrer : on demande d'abord l'autorisation de géolocalisation
  const start = async (e) => {
    e.preventDefault();
    setError("");
    if (!navigator.geolocation) return setError("Votre navigateur ne permet pas la géolocalisation.");
    setBusy(true);
    navigator.geolocation.getCurrentPosition(
      async () => {
        try {
          const payload = { duration_minutes: Number(form.duration_minutes), note: form.note || null };
          if (form.guardian_id) payload.guardian_id = form.guardian_id;
          else payload.guardian_email = form.guardian_email.trim();
          await apiClient.post("/tracking/sessions", payload);
          await load();
          notifyBeacon();
        } catch (err) {
          setError(extractErrorMessage(err, "Impossible de démarrer le suivi"));
        } finally {
          setBusy(false);
        }
      },
      () => {
        setBusy(false);
        setError("Autorisez l'accès à votre position pour ce site (icône 🔒 à côté de l'adresse), puis réessayez.");
      },
      { enableHighAccuracy: true, timeout: 20000 },
    );
  };

  const stop = async () => {
    await apiClient.post(`/tracking/sessions/${active.id}/stop`);
    await load();
    notifyBeacon();
  };

  const watchingActive = data.watching.filter((s) => s.status === "active");

  return (
    <PageShell title="Me suivre" subtitle="Partage de position en direct, pour votre sécurité">
      {watchingActive.length > 0 && (
        <section className="mt-2 space-y-2">
          <h2 className="section-title">Ils partagent leur position avec vous</h2>
          {watchingActive.map((s) => (
            <Link key={s.id} to={`/suivi/${s.id}`} className="card flex items-center gap-3 p-4">
              <span className="material-symbols-outlined text-emerald-600">share_location</span>
              <span className="min-w-0 flex-1">
                <span className="block text-sm font-extrabold">{s.owner_name}</span>
                <span className="block text-xs text-slate-500">
                  {s.last_point ? `Dernière position : ${formatDateTime(s.last_point.at)}` : "En attente de la première position"}
                </span>
              </span>
              <span className="material-symbols-outlined text-slate-400">chevron_right</span>
            </Link>
          ))}
        </section>
      )}

      {active ? (
        <section className="mt-4 rounded-3xl bg-emerald-50 p-5 ring-1 ring-emerald-100">
          <p className="flex items-center gap-2 text-base font-extrabold text-emerald-800">
            <span className="h-2.5 w-2.5 animate-pulse rounded-full bg-emerald-500" /> Suivi actif
          </p>
          <p className="mt-2 text-sm text-emerald-900">
            {active.guardian_name} et l'équipe beAuthentik voient votre position jusqu'au {formatDateTime(active.ends_at)}.
          </p>
          <p className="mt-1 text-xs text-emerald-800/80">
            {active.last_point ? `Dernière position envoyée : ${formatDateTime(active.last_point.at)}` : "Envoi de la première position…"}
          </p>
          <p className="mt-2 text-xs text-emerald-800/80">
            Gardez beAuthentik ouvert et l'écran allumé : un navigateur ne peut pas envoyer votre position site fermé.
          </p>
          <button onClick={stop} className="mt-4 h-11 w-full rounded-full bg-white text-sm font-extrabold text-rose-600 ring-1 ring-rose-100">
            Arrêter le suivi
          </button>
        </section>
      ) : (
        <form onSubmit={start} className="card mt-4 space-y-3 p-4">
          <p className="text-sm text-slate-600">
            Un rendez-vous ? Choisissez un proche inscrit sur beAuthentik : il verra votre position en direct, sur une carte,
            pendant la durée choisie. Vous pouvez arrêter à tout moment.
          </p>
          <label className="block text-xs font-bold text-slate-500">Qui peut me suivre ?</label>
          <select
            value={form.guardian_id}
            onChange={(e) => setForm({ ...form, guardian_id: e.target.value })}
            className="h-11 w-full rounded-xl bg-slate-100 px-3 text-sm"
          >
            <option value="">— Saisir l'email d'un compte beAuthentik —</option>
            {params.get("guardian") && !contacts.some((c) => c.id === params.get("guardian")) && (
              <option value={params.get("guardian")}>{params.get("name") || "Ce membre"}</option>
            )}
            {contacts.map((c) => (
              <option key={c.id} value={c.id}>{c.full_name}</option>
            ))}
          </select>
          {!form.guardian_id && (
            <input
              type="email"
              required
              value={form.guardian_email}
              onChange={(e) => setForm({ ...form, guardian_email: e.target.value })}
              placeholder="Email de son compte beAuthentik"
              className="h-11 w-full rounded-xl bg-slate-100 px-3 text-sm outline-none focus:ring-2 focus:ring-primary/30"
            />
          )}
          <label className="block text-xs font-bold text-slate-500">Pendant combien de temps ?</label>
          <select
            value={form.duration_minutes}
            onChange={(e) => setForm({ ...form, duration_minutes: e.target.value })}
            className="h-11 w-full rounded-xl bg-slate-100 px-3 text-sm"
          >
            {DURATIONS.map((d) => (
              <option key={d.value} value={d.value}>{d.label}</option>
            ))}
          </select>
          <input
            value={form.note}
            onChange={(e) => setForm({ ...form, note: e.target.value })}
            maxLength={300}
            placeholder="Note (facultatif) : lieu, personne rencontrée…"
            className="h-11 w-full rounded-xl bg-slate-100 px-3 text-sm outline-none focus:ring-2 focus:ring-primary/30"
          />
          <button disabled={busy} className="btn-primary w-full">
            <span className="material-symbols-outlined text-lg">share_location</span>
            {busy ? "Démarrage…" : "Démarrer le suivi"}
          </button>
          {error && <p className="text-xs font-semibold text-rose-600">{error}</p>}
          <p className="text-[11px] text-slate-400">
            Votre position précise est transmise au serveur beAuthentik et au compte choisi uniquement pendant le suivi, puis
            effacée automatiquement après 30 jours.
          </p>
        </form>
      )}

      {data.mine.filter((s) => s.status !== "active").length > 0 && (
        <section className="mt-6">
          <h2 className="section-title">Mes suivis précédents</h2>
          {data.mine
            .filter((s) => s.status !== "active")
            .map((s) => (
              <p key={s.id} className="mb-2 rounded-xl bg-slate-50 px-3 py-2 text-xs text-slate-600">
                Avec {s.guardian_name} · du {formatDateTime(s.started_at)} {s.stopped_at ? `au ${formatDateTime(s.stopped_at)}` : "(terminé)"}
              </p>
            ))}
        </section>
      )}
    </PageShell>
  );
}
