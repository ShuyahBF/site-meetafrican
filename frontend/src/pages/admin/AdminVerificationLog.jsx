import { useEffect, useState } from "react";
import { apiClient } from "@/lib/api";
import { formatDateTime } from "@/lib/format";

// Types de vérification (filtre)
const KINDS = [
  { key: "", label: "Tout" },
  { key: "photo", label: "Photos" },
  { key: "document", label: "Pièces d'identité" },
  { key: "whatsapp", label: "WhatsApp" },
  { key: "phone", label: "Téléphone" },
];

// Libellés lisibles des actions enregistrées par verification_log.py
const ACTION_LABEL = {
  submitted: "Soumission",
  faces_counted: "Visages comptés",
  auto_rejected_faces: "Refus automatique (trop de visages)",
  ai_approved: "IA : approuvée",
  ai_rejected: "IA : refusée",
  ai_needs_review: "IA : à revoir",
  human_approved: "Modérateur : approuvée",
  human_rejected: "Modérateur : refusée",
  code_sent: "Code envoyé",
  code_send_failed: "Échec d'envoi du code",
  code_wrong: "Code incorrect",
  verified: "Numéro vérifié",
};

/**
 * Journal horodaté de toutes les soumissions et vérifications (photos,
 * pièces d'identité, numéros) : date et heure, membre, action, auteur
 * (membre, IA, système, modérateur), adresse IP et détails.
 */
export default function AdminVerificationLog() {
  const [kind, setKind] = useState("");
  const [data, setData] = useState({ total: 0, items: [] });
  const [loading, setLoading] = useState(true);

  // Rechargement à chaque changement de filtre
  useEffect(() => {
    setLoading(true);
    apiClient
      .get("/admin/verification-events", { params: { kind: kind || undefined, limit: 200 } })
      .then((r) => setData(r.data))
      .finally(() => setLoading(false));
  }, [kind]);

  return (
    <div>
      <h1 className="text-2xl font-bold">Journal des vérifications</h1>
      <p className="mt-1 text-sm text-slate-500">
        Chaque soumission et chaque décision (IA, système, modérateur) est horodatée, avec l'adresse IP.
      </p>

      <div className="mt-4 flex flex-wrap gap-2">
        {KINDS.map((k) => (
          <button
            key={k.key}
            onClick={() => setKind(k.key)}
            className={`rounded-full px-3 py-1 text-sm font-semibold ${kind === k.key ? "bg-primary text-white" : "bg-white text-slate-600"}`}
          >
            {k.label}
          </button>
        ))}
      </div>

      {loading ? (
        <p className="mt-6 text-slate-400">Chargement…</p>
      ) : (
        <div className="mt-4 overflow-x-auto rounded-xl bg-white shadow-sm">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-50 text-xs uppercase text-slate-500">
              <tr>
                <th className="px-3 py-2">Date et heure</th>
                <th className="px-3 py-2">Membre</th>
                <th className="px-3 py-2">Type</th>
                <th className="px-3 py-2">Action</th>
                <th className="px-3 py-2">Par</th>
                <th className="px-3 py-2">IP</th>
                <th className="px-3 py-2">Détails</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {data.items.map((e) => (
                <tr key={e.id} className="align-top">
                  <td className="whitespace-nowrap px-3 py-2">{formatDateTime(e.at)}</td>
                  <td className="px-3 py-2">{e.user?.full_name || e.user_id}</td>
                  <td className="px-3 py-2">{e.kind}</td>
                  <td className="px-3 py-2 font-semibold">{ACTION_LABEL[e.action] || e.action}</td>
                  <td className="px-3 py-2">{e.actor_user?.full_name || e.actor}</td>
                  <td className="px-3 py-2 font-mono text-xs">{e.ip || "—"}</td>
                  <td className="max-w-xs px-3 py-2 text-xs text-slate-500">
                    {Object.entries(e.details || {})
                      .map(([k, v]) => `${k} : ${v}`)
                      .join(" · ")}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {data.items.length === 0 && <p className="px-4 py-6 text-center text-sm text-slate-400">Aucun événement.</p>}
          <p className="px-4 py-2 text-xs text-slate-400">{data.total} événement(s) au total</p>
        </div>
      )}
    </div>
  );
}
