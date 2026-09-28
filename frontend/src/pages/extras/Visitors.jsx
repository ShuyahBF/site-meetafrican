import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { apiClient } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import PageShell from "@/components/PageShell";
import VerifiedBadge from "@/components/VerifiedBadge";

/** Petite ligne "membre + date" réutilisée par les deux onglets. */
function PersonRow({ person, at, extra }) {
  return (
    <Link to={`/profils/${person.id}`} className="flex items-center gap-3 rounded-2xl px-2 py-2 hover:bg-slate-50">
      <img
        src={person.avatar_url || "/images/silhouette-homme.svg"}
        alt=""
        className="h-12 w-12 shrink-0 rounded-full bg-slate-100 object-cover"
      />
      <span className="min-w-0 flex-1">
        <span className="flex items-center gap-1 truncate text-sm font-extrabold">
          {person.full_name}
          {person.is_verified && <VerifiedBadge className="text-sm" />}
        </span>
        <span className="block truncate text-xs text-slate-500">
          {formatDateTime(at)}
          {extra ? ` · ${extra}` : ""}
        </span>
      </span>
    </Link>
  );
}

/**
 * « Qui m'a vu » : historique horodaté des visites de mon profil et des
 * vues de mes Moments. Les membres en mode invisible n'y apparaissent pas.
 */
export default function Visitors() {
  const [tab, setTab] = useState("profil");
  const [data, setData] = useState(null);

  useEffect(() => {
    apiClient.get("/me/visitors").then((r) => setData(r.data));
  }, []);

  const tabs = [
    { key: "profil", label: `Mon profil (${data?.profile_visits.length ?? 0})` },
    { key: "moments", label: `Mes Moments (${data?.moment_views.length ?? 0})` },
  ];

  return (
    <PageShell title="Qui m'a vu" subtitle="Visites de votre profil et vues de vos Moments">
      <div className="mt-2 flex gap-2">
        {tabs.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`rounded-full px-4 py-2 text-sm font-bold ${tab === t.key ? "bg-ink text-white" : "bg-slate-100 text-slate-600"}`}
          >
            {t.label}
          </button>
        ))}
      </div>
      {!data ? (
        <p className="mt-6 text-sm text-slate-400">Chargement…</p>
      ) : tab === "profil" ? (
        <div className="mt-3">
          {data.profile_visits.length === 0 && <p className="text-sm text-slate-400">Personne n'a encore visité votre profil.</p>}
          {data.profile_visits.map((v) => (
            <PersonRow key={`${v.visitor.id}-${v.at}`} person={v.visitor} at={v.at} extra={v.count > 1 ? `${v.count} visites ce jour-là` : null} />
          ))}
        </div>
      ) : (
        <div className="mt-3">
          {data.moment_views.length === 0 && <p className="text-sm text-slate-400">Aucune vue sur vos Moments pour le moment.</p>}
          {data.moment_views.map((v) => (
            <PersonRow key={`${v.viewer.id}-${v.video?.id}`} person={v.viewer} at={v.at} extra={v.video?.caption ? `« ${v.video.caption.slice(0, 40)} »` : "a vu un Moment"} />
          ))}
        </div>
      )}
      <p className="mt-6 text-[11px] text-slate-400">
        Astuce : en mode invisible (Réglages), vos propres visites n'apparaissent pas chez les autres.
      </p>
    </PageShell>
  );
}
