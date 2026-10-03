// Pastille « Test » : signale un profil fictif généré pour tester le site
// (données marquées is_test_data côté serveur, supprimables d'un clic
// depuis l'admin). `dark` : version pour fond sombre (vidéos).
import { useAuth } from "@/context/AuthContext";

// Lot 50 — information réservée au super-administrateur : invisible pour les membres.
export default function TestBadge({ dark = false, className = "" }) {
  const { user } = useAuth();
  if (user?.role !== "admin") return null;
  return (
    <span
      title="Profil de test (données fictives)"
      className={`inline-flex items-center rounded-md px-1.5 py-0.5 align-middle text-[10px] font-extrabold uppercase tracking-wider ${
        dark ? "bg-white/25 text-white" : "bg-amber-100 text-amber-700"
      } ${className}`}
    >
      Test
    </span>
  );
}
