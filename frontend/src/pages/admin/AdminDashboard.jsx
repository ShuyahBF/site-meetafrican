import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { apiClient } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";

const CARDS = [
  { key: "photos", label: "Photos en attente", to: "/admin/photos", fetch: (c) => c.get("/admin/photos/pending") },
  // 09/10/2026 — pièces d'identité : réservées au super-administrateur (carte masquée pour les modérateurs)
  { key: "verifications", label: "Vérifications en attente", to: "/admin/verifications", fetch: (c) => c.get("/admin/verification/pending"), adminOnly: true },
  { key: "proofs", label: "Preuves de paiement en attente", to: "/admin/paiements", fetch: (c) => c.get("/subscriptions/payment-proofs/pending") },
  { key: "reports", label: "Signalements ouverts", to: "/admin/signalements", fetch: (c) => c.get("/admin/reports", { params: { status: "open" } }) },
];

export default function AdminDashboard() {
  const { user } = useAuth();
  const cartes = CARDS.filter((c) => !c.adminOnly || user?.role === "admin");
  const [counts, setCounts] = useState({});
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all(
      cartes.map((c) =>
        c.fetch(apiClient).then((r) => [c.key, r.data.length]).catch(() => [c.key, "—"])
      )
    ).then((entries) => {
      setCounts(Object.fromEntries(entries));
      setLoading(false);
    });
  }, []);   // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div>
      <h1 className="text-2xl font-bold">Tableau de bord</h1>
      <p className="mt-1 text-sm text-slate-500">Vue d'ensemble des files d'attente de modération.</p>

      <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {cartes.map((c) => (
          <Link
            key={c.key}
            to={c.to}
            className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm transition hover:border-primary"
          >
            <p className="text-3xl font-bold text-primary">{loading ? "…" : counts[c.key]}</p>
            <p className="mt-1 text-sm font-semibold text-slate-600">{c.label}</p>
          </Link>
        ))}
      </div>
    </div>
  );
}
