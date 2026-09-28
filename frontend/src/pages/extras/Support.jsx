import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { apiClient, extractErrorMessage } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import PageShell from "@/components/PageShell";

const TOPICS = [
  { value: "compte", label: "Mon compte" },
  { value: "paiement", label: "Paiement / abonnement" },
  { value: "verification", label: "Vérification (identité, photos, numéros)" },
  { value: "securite", label: "Sécurité" },
  { value: "signalement", label: "Signaler un membre" },
  { value: "autre", label: "Autre" },
];
const STATUS = { open: "En attente", answered: "Réponse reçue", closed: "Clôturée" };

/**
 * Écrire au support : nouvelle demande + suivi des demandes (fil de
 * messages horodatés avec l'équipe beAuthentik).
 */
export default function Support() {
  const [params] = useSearchParams();
  const aboutName = params.get("name");
  const [tickets, setTickets] = useState([]);
  const [openId, setOpenId] = useState(null);
  const [form, setForm] = useState({
    topic: aboutName ? "signalement" : "autre",
    subject: aboutName ? `À propos de ${aboutName}` : "",
    message: aboutName ? `Profil concerné : ${aboutName} (id ${params.get("about")})\n\n` : "",
  });
  const [reply, setReply] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const load = () => apiClient.get("/me/support/tickets").then((r) => setTickets(r.data));
  useEffect(() => {
    load();
  }, []);

  // Nouvelle demande
  const create = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const r = await apiClient.post("/support/tickets", form);
      setForm({ topic: "autre", subject: "", message: "" });
      await load();
      setOpenId(r.data.id);
    } catch (err) {
      setError(extractErrorMessage(err, "Envoi impossible"));
    } finally {
      setBusy(false);
    }
  };

  // Ouvrir une demande (et marquer la réponse comme lue)
  const toggle = (t) => {
    setOpenId(openId === t.id ? null : t.id);
    if (t.unread_by_member) apiClient.post(`/me/support/tickets/${t.id}/seen`).then(load);
  };

  // Répondre dans une demande
  const send = async (ticketId) => {
    if (!reply.trim()) return;
    setBusy(true);
    try {
      await apiClient.post(`/support/tickets/${ticketId}/messages`, { message: reply });
      setReply("");
      await load();
    } finally {
      setBusy(false);
    }
  };

  return (
    <PageShell title="Écrire au support" subtitle="L'équipe beAuthentik vous répond ici">
      <form onSubmit={create} className="card mt-2 space-y-3 p-4">
        <select value={form.topic} onChange={(e) => setForm({ ...form, topic: e.target.value })} className="h-11 w-full rounded-xl bg-slate-100 px-3 text-sm">
          {TOPICS.map((t) => (
            <option key={t.value} value={t.value}>{t.label}</option>
          ))}
        </select>
        <input
          value={form.subject}
          onChange={(e) => setForm({ ...form, subject: e.target.value })}
          required
          minLength={3}
          maxLength={120}
          placeholder="Objet"
          className="h-11 w-full rounded-xl bg-slate-100 px-3 text-sm outline-none focus:ring-2 focus:ring-primary/30"
        />
        <textarea
          value={form.message}
          onChange={(e) => setForm({ ...form, message: e.target.value })}
          required
          minLength={5}
          rows={4}
          placeholder="Décrivez votre demande"
          className="w-full rounded-2xl bg-slate-100 p-3 text-sm outline-none focus:ring-2 focus:ring-primary/30"
        />
        <button disabled={busy} className="btn-primary w-full">{busy ? "Envoi…" : "Envoyer"}</button>
        {error && <p className="text-xs font-semibold text-rose-600">{error}</p>}
      </form>

      <section className="mt-6 space-y-2">
        <h2 className="section-title">Mes demandes</h2>
        {tickets.length === 0 && <p className="text-sm text-slate-400">Aucune demande pour le moment.</p>}
        {tickets.map((t) => (
          <div key={t.id} className="card p-0">
            <button onClick={() => toggle(t)} className="flex w-full items-center justify-between gap-2 p-4 text-left">
              <span className="min-w-0">
                <span className="block truncate text-sm font-extrabold">{t.subject}</span>
                <span className="block text-xs text-slate-500">
                  {STATUS[t.status] || t.status} · {formatDateTime(t.updated_at)}
                </span>
              </span>
              {t.unread_by_member && <span className="chip bg-primary text-[11px] text-white">Nouveau</span>}
            </button>
            {openId === t.id && (
              <div className="space-y-2 border-t border-slate-100 p-4">
                {t.messages.map((m) => (
                  <div key={m.id} className={`rounded-2xl px-3 py-2 text-sm ${m.from_staff ? "bg-sky-50" : "bg-slate-100"}`}>
                    <p className="text-[11px] font-bold text-slate-500">
                      {m.author_name} · {formatDateTime(m.at)}
                    </p>
                    <p className="whitespace-pre-wrap">{m.text}</p>
                  </div>
                ))}
                <div className="flex gap-2">
                  <input
                    value={reply}
                    onChange={(e) => setReply(e.target.value)}
                    placeholder="Votre réponse…"
                    className="h-11 min-w-0 flex-1 rounded-full bg-slate-100 px-4 text-sm outline-none"
                  />
                  <button onClick={() => send(t.id)} disabled={busy || !reply.trim()} className="btn-primary h-11 px-4 text-sm">
                    Envoyer
                  </button>
                </div>
              </div>
            )}
          </div>
        ))}
      </section>
    </PageShell>
  );
}
