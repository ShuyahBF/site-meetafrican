import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { apiClient } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { useAuth } from "@/context/AuthContext";
import AbonnementSessionsMembre from "@/components/admin/AbonnementSessionsMembre";

const REASON = { fake_profile: "Faux profil", abus: "Comportement abusif", autre: "Autre" };

/** Bloc titré de la fiche. */
function Block({ title, children }) {
  return (
    <section className="rounded-xl bg-white p-4 shadow-sm">
      <h2 className="mb-2 font-bold">{title}</h2>
      {children}
    </section>
  );
}

/**
 * Fiche membre, en LECTURE SEULE et en INVISIBLE : aucune visite n'est
 * enregistrée dans son historique « Qui m'a vu ». Photos non masquées,
 * Moments, paiements, signalements reçus et émis, vérifications.
 * Utile pour traiter un signalement.
 */
export default function AdminMember() {
  const { userId } = useParams();
  const { user: moi } = useAuth();
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    apiClient.get(`/admin/members/${userId}`).then((r) => setData(r.data)).catch(() => setError("Membre introuvable"));
  }, [userId]);

  if (error) return <p className="text-sm text-slate-500">{error}</p>;
  if (!data) return <p className="text-sm text-slate-400">Chargement…</p>;
  const u = data.user;
  const settings = u.settings || {};

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="text-xs font-bold uppercase tracking-wider text-slate-400">Fiche membre · consultation invisible</p>
          <h1 className="text-2xl font-bold">
            {u.full_name} {u.is_test_data && <span className="text-sm text-amber-600">(TEST)</span>}
          </h1>
          <p className="text-sm text-slate-500">
            {[u.gender, u.birthdate, u.city, u.country].filter(Boolean).join(" · ")}
          </p>
        </div>
        <div className="flex gap-2">
          <Link to={`/admin/chronologie?user=${u.id}`} className="rounded-lg bg-white px-3 py-2 text-sm font-bold text-slate-600 shadow-sm">
            Son historique
          </Link>
          <Link to={`/profils/${u.id}`} className="rounded-lg bg-primary px-3 py-2 text-sm font-bold text-white">
            Voir son profil public
          </Link>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <Block title="Compte">
          <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-sm">
            <dt className="text-slate-500">Email</dt><dd>{u.email || "—"}</dd>
            <dt className="text-slate-500">Téléphone</dt><dd>{u.phone || "—"} {u.phone_verified && "✅"}</dd>
            <dt className="text-slate-500">WhatsApp</dt><dd>{u.whatsapp || "—"} {u.whatsapp_verified && "✅"}</dd>
            <dt className="text-slate-500">Identité</dt><dd>{u.verification_status}</dd>
            <dt className="text-slate-500">Rôle</dt><dd>{u.role}</dd>
            <dt className="text-slate-500">Actif</dt><dd>{u.is_active === false ? "Désactivé" : "Oui"}</dd>
            <dt className="text-slate-500">Inscrit le</dt><dd>{formatDateTime(u.created_at)}</dd>
            <dt className="text-slate-500">IP d'inscription</dt><dd className="font-mono text-xs">{u.registration_ip || "—"}</dd>
            <dt className="text-slate-500">Dernière connexion</dt><dd>{formatDateTime(u.last_login_at)} <span className="font-mono text-xs">{u.last_login_ip}</span></dd>
            <dt className="text-slate-500">Mode invisible</dt><dd>{settings.invisible_mode ? "Oui" : "Non"}</dd>
            <dt className="text-slate-500">Matchs / messages</dt><dd>{data.counts.matches} / {data.counts.messages_sent}</dd>
          </dl>
          {u.bio && <p className="mt-2 rounded-lg bg-slate-50 p-2 text-sm">{u.bio}</p>}
        </Block>

        <Block title={`Photos (${(u.photos || []).length})`}>
          <div className="grid grid-cols-3 gap-2">
            {(u.photos || []).map((p) => (
              <div key={p.id} className="relative">
                <img src={p.url} alt="" className="aspect-[3/4] w-full rounded-lg object-cover" />
                <span className="absolute bottom-1 left-1 rounded bg-white/90 px-1 text-[10px] font-bold">{p.status}</span>
              </div>
            ))}
          </div>
        </Block>
      </div>

      {/* Abonnement (grâce), sessions et inactivité : administrateur principal uniquement */}
      {moi?.role === "admin" && <AbonnementSessionsMembre userId={u.id} />}

      <Block title={`Signalements reçus (${data.reports_received.length})`}>
        {data.reports_received.length === 0 && <p className="text-sm text-slate-400">Aucun.</p>}
        {data.reports_received.map((r) => (
          <p key={r.id} className="border-b border-slate-100 py-1.5 text-sm last:border-0">
            <span className="font-semibold">{REASON[r.reason] || r.reason}</span> · par{" "}
            <Link to={`/admin/membres/${r.reporter_user_id}`} className="text-primary">{r.reporter_name || "?"}</Link> ·{" "}
            {formatDateTime(r.created_at)} · {r.status}
            {r.details && <span className="block text-xs text-slate-500">{r.details}</span>}
          </p>
        ))}
      </Block>

      <Block title={`Moments (${data.videos.length})`}>
        <div className="grid grid-cols-3 gap-2 sm:grid-cols-6">
          {data.videos.map((v) => (
            <div key={v.id} className="text-xs">
              <img src={v.poster_url} alt="" className="aspect-[9/16] w-full rounded-lg bg-slate-100 object-cover" />
              <p className="mt-1 truncate">{v.caption}</p>
              <p className="text-slate-400">{v.status} · {v.reports_count || 0} signal.</p>
            </div>
          ))}
        </div>
      </Block>

      <div className="grid gap-4 md:grid-cols-2">
        <Block title={`Paiements (${data.payments.length})`}>
          {data.payments.length === 0 && <p className="text-sm text-slate-400">Aucun.</p>}
          {data.payments.map((p) => (
            <p key={p.id} className="border-b border-slate-100 py-1.5 text-sm last:border-0">
              {formatDateTime(p.created_at)} · {p.amount} {p.currency} · {p.purpose} · <span className="font-semibold">{p.status}</span>
            </p>
          ))}
        </Block>
        <Block title="Vérifications d'identité / signalements émis">
          {data.verifications.map((v) => (
            <p key={v.id} className="text-sm">Pièce envoyée le {formatDateTime(v.created_at)} · {v.status}{v.ai_reason ? ` · IA : ${v.ai_reason}` : ""}</p>
          ))}
          {data.reports_sent.map((r) => (
            <p key={r.id} className="text-sm">
              A signalé <Link to={`/admin/membres/${r.reported_user_id}`} className="text-primary">{r.reported_name || "?"}</Link> le {formatDateTime(r.created_at)}
            </p>
          ))}
          {data.verifications.length + data.reports_sent.length === 0 && <p className="text-sm text-slate-400">Aucune.</p>}
        </Block>
      </div>
    </div>
  );
}
