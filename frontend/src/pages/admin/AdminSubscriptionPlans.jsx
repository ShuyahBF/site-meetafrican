import { useEffect, useState } from "react";
import { apiClient, extractErrorMessage } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { formatDateTime } from "@/lib/format";

const EMPTY_PLAN = {
  code: "", name: "", duration_days: 30, price_xof: 0, savings_pct: "",
  features: "", featured: false, badge: "", active: true, autorise_mode_invisible: false,
};

function toFormState(plan) {
  return {
    ...plan,
    savings_pct: plan.savings_pct ?? "",
    badge: plan.badge ?? "",
    features: (plan.features || []).join("\n"),
  };
}

function toApiPayload(form) {
  return {
    ...form,
    duration_days: Number(form.duration_days),
    price_xof: Number(form.price_xof),
    savings_pct: form.savings_pct === "" ? null : Number(form.savings_pct),
    badge: form.badge || null,
    features: form.features.split("\n").map((f) => f.trim()).filter(Boolean),
  };
}

export default function AdminSubscriptionPlans() {
  // Super-administrateur (rôle « admin ») : seul à voir et régler le Mode Invisible
  const { user } = useAuth();
  const superAdmin = user?.role === "admin";
  const [plans, setPlans] = useState([]);
  const [loading, setLoading] = useState(true);
  const [editingId, setEditingId] = useState(null);
  const [form, setForm] = useState(EMPTY_PLAN);
  const [creating, setCreating] = useState(false);
  const [saving, setSaving] = useState(false);

  const load = () => {
    setLoading(true);
    apiClient.get("/admin/subscription-plans").then((r) => setPlans(r.data)).finally(() => setLoading(false));
  };

  useEffect(load, []);

  const startEdit = (plan) => {
    setEditingId(plan.id);
    setCreating(false);
    setForm(toFormState(plan));
  };

  const startCreate = () => {
    setCreating(true);
    setEditingId(null);
    setForm(EMPTY_PLAN);
  };

  const cancel = () => {
    setEditingId(null);
    setCreating(false);
  };

  const save = async () => {
    setSaving(true);
    try {
      const payload = toApiPayload(form);
      if (creating) {
        await apiClient.post("/admin/subscription-plans", payload);
      } else {
        await apiClient.put(`/admin/subscription-plans/${editingId}`, payload);
      }
      cancel();
      load();
    } finally {
      setSaving(false);
    }
  };

  const update = (key) => (e) => {
    const value = e.target.type === "checkbox" ? e.target.checked : e.target.value;
    setForm({ ...form, [key]: value });
  };

  const editing = creating || editingId;

  return (
    <div>
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Formules d'abonnement</h1>
        {!editing && (
          <button onClick={startCreate} className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-white">
            + Nouvelle formule
          </button>
        )}
      </div>

      {editing && (
        <div className="mt-6 rounded-xl border border-primary/30 bg-white p-5">
          <h2 className="font-bold">{creating ? "Nouvelle formule" : "Modifier la formule"}</h2>
          <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Field label="Code (identifiant unique)">
              <input value={form.code} onChange={update("code")} className="admin-input" />
            </Field>
            <Field label="Nom">
              <input value={form.name} onChange={update("name")} className="admin-input" />
            </Field>
            <Field label="Durée (jours)">
              <input type="number" value={form.duration_days} onChange={update("duration_days")} className="admin-input" />
            </Field>
            <Field label="Prix (XOF)">
              <input type="number" value={form.price_xof} onChange={update("price_xof")} className="admin-input" />
            </Field>
            <Field label="Économie affichée (%)">
              <input type="number" value={form.savings_pct} onChange={update("savings_pct")} className="admin-input" />
            </Field>
            <Field label="Badge (ex: Meilleure offre)">
              <input value={form.badge} onChange={update("badge")} className="admin-input" />
            </Field>
          </div>
          <Field label="Fonctionnalités (une par ligne)">
            <textarea value={form.features} onChange={update("features")} rows={4} className="admin-input" />
          </Field>
          <div className="mt-3 flex gap-4">
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={form.featured} onChange={update("featured")} /> Mise en avant
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={form.active} onChange={update("active")} /> Active
            </label>
            {/* Réservé au super-administrateur (le serveur ignore cette case pour les modérateurs) */}
            {superAdmin && (
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={!!form.autorise_mode_invisible} onChange={update("autorise_mode_invisible")} />
                Autorise le Mode Invisible
              </label>
            )}
          </div>
          <div className="mt-4 flex gap-2">
            <button onClick={save} disabled={saving} className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">
              {saving ? "Enregistrement…" : "Enregistrer"}
            </button>
            <button onClick={cancel} className="rounded-lg bg-slate-200 px-4 py-2 text-sm font-semibold text-slate-700">
              Annuler
            </button>
          </div>
        </div>
      )}

      {loading ? (
        <p className="mt-6 text-slate-400">Chargement…</p>
      ) : (
        <div className="mt-6 flex flex-col gap-3">
          {plans.map((p) => (
            <div key={p.id} className="flex items-center justify-between rounded-xl border border-slate-200 bg-white p-4">
              <div>
                <p className="font-semibold">
                  {p.name} {!p.active && <span className="ml-2 text-xs text-slate-400">(inactive)</span>}
                </p>
                <p className="text-sm text-slate-500">
                  {p.price_xof.toLocaleString("fr-FR")} XOF · {p.duration_days} jours · {p.code}
                  {p.autorise_mode_invisible && <span className="ml-2 font-semibold text-primary">· Mode Invisible inclus</span>}
                </p>
              </div>
              <button onClick={() => startEdit(p)} className="rounded-lg bg-slate-100 px-4 py-2 text-sm font-semibold text-slate-700">
                Modifier
              </button>
            </div>
          ))}
        </div>
      )}

      {superAdmin && <PrixBonusInvisible />}
    </div>
  );
}

/**
 * Prix du bonus Mode Invisible (super-administrateur seulement) : achat
 * ponctuel payé avec le portefeuille, qui active le mode pour 14 jours.
 * Champ vide = achat indisponible pour les membres.
 */
function PrixBonusInvisible() {
  const [reglage, setReglage] = useState(null);
  const [prix, setPrix] = useState("");
  const [message, setMessage] = useState("");

  useEffect(() => {
    apiClient.get("/admin/mode-invisible").then((r) => {
      setReglage(r.data);
      setPrix(r.data.prix_bonus_xof ?? "");
    }).catch(() => {});
  }, []);

  const enregistrer = async (e) => {
    e.preventDefault();
    setMessage("");
    try {
      const valeur = String(prix).trim() === "" ? null : Number(prix);
      const r = await apiClient.put("/admin/mode-invisible", { prix_bonus_xof: valeur });
      setReglage(r.data);
      setMessage(valeur === null ? "Prix effacé : l'achat du bonus est indisponible." : "Prix enregistré.");
    } catch (err) {
      setMessage(extractErrorMessage(err, "Prix refusé"));
    }
  };

  if (!reglage) return null;
  return (
    <section className="mt-8 rounded-xl border border-slate-200 bg-white p-5">
      <h2 className="font-bold">Bonus « Mode Invisible »</h2>
      <p className="mt-1 text-sm text-slate-500">
        Achat ponctuel payé avec le portefeuille du membre : le Mode Invisible est activé pour {reglage.duree_jours} jours.
        Les membres dont la formule porte la case « Autorise le Mode Invisible » n'ont pas besoin du bonus.
      </p>
      <form onSubmit={enregistrer} className="mt-3 flex flex-wrap items-end gap-2">
        <Field label="Prix du bonus (XOF) — vide = achat indisponible">
          <input type="number" min={1} value={prix} onChange={(e) => setPrix(e.target.value)} className="admin-input" />
        </Field>
        <button type="submit" className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-white">Enregistrer</button>
      </form>
      {reglage.modifie_le && (
        <p className="mt-2 text-xs text-slate-400">Modifié le {formatDateTime(reglage.modifie_le)} par {reglage.modifie_par || "—"}</p>
      )}
      {message && <p className="mt-2 text-sm text-slate-600">{message}</p>}
    </section>
  );
}

function Field({ label, children }) {
  return (
    <label className="mt-3 flex flex-col gap-1 text-sm font-semibold text-slate-600">
      {label}
      {children}
    </label>
  );
}
