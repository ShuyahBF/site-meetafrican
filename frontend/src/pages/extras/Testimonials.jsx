import { useEffect, useState } from "react";
import { apiClient, extractErrorMessage } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import PageShell from "@/components/PageShell";

const STATUS = { pending: "En relecture", approved: "Publié", rejected: "Non publié" };

/**
 * Témoignages : lecture des témoignages publiés + formulaire pour raconter
 * sa propre expérience (relu par l'équipe avant publication).
 */
export default function Testimonials() {
  const [items, setItems] = useState([]);
  const [mine, setMine] = useState([]);
  const [text, setText] = useState("");
  const [rating, setRating] = useState(5);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");

  // Chargement des témoignages publiés et des miens
  const load = () => {
    apiClient.get("/testimonials").then((r) => setItems(r.data));
    apiClient.get("/me/testimonials").then((r) => setMine(r.data));
  };
  useEffect(load, []);

  // Envoi d'un témoignage (statut "En relecture")
  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setNotice("");
    try {
      await apiClient.post("/testimonials", { text, rating });
      setText("");
      setNotice("Merci ! Votre témoignage sera publié après relecture par l'équipe.");
      load();
    } catch (err) {
      setNotice(extractErrorMessage(err, "Envoi impossible"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <PageShell title="Témoignages" subtitle="Ils se sont rencontrés sur beAuthentik">
      <form onSubmit={submit} className="card mt-2 space-y-3 p-4">
        <p className="text-sm font-extrabold">Racontez votre expérience</p>
        <div className="flex gap-1">
          {[1, 2, 3, 4, 5].map((n) => (
            <button type="button" key={n} onClick={() => setRating(n)} aria-label={`${n} étoiles`}>
              <span className={`material-symbols-outlined icon-filled text-2xl ${n <= rating ? "text-amber-400" : "text-slate-200"}`}>star</span>
            </button>
          ))}
        </div>
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={4}
          minLength={20}
          maxLength={1200}
          required
          placeholder="Votre rencontre, ce qui vous a plu… (20 caractères minimum)"
          className="w-full rounded-2xl bg-slate-100 p-3 text-sm outline-none focus:ring-2 focus:ring-primary/30"
        />
        <button disabled={busy || text.trim().length < 20} className="btn-primary w-full">
          {busy ? "Envoi…" : "Publier mon témoignage"}
        </button>
        {notice && <p className="text-xs font-semibold text-slate-600">{notice}</p>}
        <p className="text-[11px] text-slate-400">Seuls votre prénom et votre ville seront affichés.</p>
      </form>

      {mine.length > 0 && (
        <section className="mt-6">
          <h2 className="section-title">Mes témoignages</h2>
          {mine.map((t) => (
            <p key={t.id} className="mb-2 rounded-xl bg-slate-50 px-3 py-2 text-xs text-slate-600">
              <span className="font-bold">{STATUS[t.status] || t.status}</span> · envoyé le {formatDateTime(t.created_at)}
            </p>
          ))}
        </section>
      )}

      <section className="mt-6 space-y-3">
        <h2 className="section-title">Ils témoignent</h2>
        {items.length === 0 && <p className="text-sm text-slate-400">Soyez le premier à raconter votre histoire ✨</p>}
        {items.map((t) => (
          <figure key={t.id} className="card p-4">
            <div className="flex gap-0.5">
              {Array.from({ length: t.rating }).map((_, i) => (
                <span key={i} className="material-symbols-outlined icon-filled text-base text-amber-400">star</span>
              ))}
            </div>
            <blockquote className="mt-2 text-sm leading-relaxed text-slate-700">« {t.text} »</blockquote>
            <figcaption className="mt-2 text-xs font-bold text-slate-500">
              {t.author_name}
              {t.author_city ? `, ${t.author_city}` : ""}
            </figcaption>
          </figure>
        ))}
      </section>
    </PageShell>
  );
}
