import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { apiClient } from "@/lib/api";
import { formatDateTime } from "@/lib/format";

const FILTERS = [
  { key: "open", label: "À traiter" },
  { key: "answered", label: "Répondues" },
  { key: "closed", label: "Clôturées" },
];

/** Demandes de support : lecture, réponse (horodatée) et clôture. */
export default function AdminSupport() {
  const [status, setStatus] = useState("open");
  const [tickets, setTickets] = useState([]);
  const [replies, setReplies] = useState({});

  const load = () => apiClient.get("/admin/support/tickets", { params: { status } }).then((r) => setTickets(r.data));
  useEffect(() => {
    load();
  }, [status]); // eslint-disable-line react-hooks/exhaustive-deps

  const reply = async (t) => {
    const message = (replies[t.id] || "").trim();
    if (!message) return;
    await apiClient.post(`/support/tickets/${t.id}/messages`, { message });
    setReplies({ ...replies, [t.id]: "" });
    load();
  };
  const close = async (t) => {
    await apiClient.post(`/admin/support/tickets/${t.id}/close`);
    load();
  };

  return (
    <div>
      <h1 className="text-2xl font-bold">Support</h1>
      <div className="mt-4 flex gap-2">
        {FILTERS.map((f) => (
          <button key={f.key} onClick={() => setStatus(f.key)} className={`rounded-full px-3 py-1 text-sm font-semibold ${status === f.key ? "bg-primary text-white" : "bg-white text-slate-600"}`}>
            {f.label}
          </button>
        ))}
      </div>
      <div className="mt-4 space-y-4">
        {tickets.length === 0 && <p className="text-sm text-slate-500">Aucune demande.</p>}
        {tickets.map((t) => (
          <div key={t.id} className="rounded-xl bg-white p-4 shadow-sm">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="font-bold">{t.subject}</p>
              <span className="text-xs text-slate-400">{t.topic} · ouverte le {formatDateTime(t.created_at)}</span>
            </div>
            <p className="text-xs text-slate-500">
              De <Link to={`/profils/${t.user_id}`} className="font-semibold text-primary">{t.user_name}</Link>
            </p>
            <div className="mt-3 space-y-2">
              {t.messages.map((m) => (
                <div key={m.id} className={`rounded-lg px-3 py-2 text-sm ${m.from_staff ? "bg-sky-50" : "bg-slate-50"}`}>
                  <p className="text-[11px] font-bold text-slate-500">{m.author_name} · {formatDateTime(m.at)}</p>
                  <p className="whitespace-pre-wrap">{m.text}</p>
                </div>
              ))}
            </div>
            {t.status !== "closed" && (
              <div className="mt-3 flex flex-wrap gap-2">
                <input
                  value={replies[t.id] || ""}
                  onChange={(e) => setReplies({ ...replies, [t.id]: e.target.value })}
                  placeholder="Réponse de l'équipe…"
                  className="min-w-[200px] flex-1 rounded-lg border border-slate-200 px-3 py-2 text-sm"
                />
                <button onClick={() => reply(t)} className="rounded-lg bg-primary px-4 py-2 text-sm font-bold text-white">Répondre</button>
                <button onClick={() => close(t)} className="rounded-lg bg-slate-100 px-4 py-2 text-sm font-bold text-slate-600">Clôturer</button>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
