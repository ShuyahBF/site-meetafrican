import { useAuth } from "@/context/AuthContext";
import DeconnexionGenerale from "@/components/DeconnexionGenerale";
import TransfertDonnees from "@/components/transfert/TransfertDonnees";

/**
 * Données & maintenance (administrateur principal uniquement, jamais les
 * modérateurs) : déconnexion programmée de tous les utilisateurs, puis
 * export / import complets de la base pour changer de cluster MongoDB.
 * Ordre conseillé pour un transfert : 1) maintenance, 2) export, 3) changement
 * de MONGO_URL dans Render, 4) import, 5) réactivation des connexions.
 */
export default function AdminDonneesMaintenance() {
  const { user } = useAuth();
  if (user?.role !== "admin") {
    return <p className="rounded-2xl bg-white p-6 text-sm text-slate-500 shadow-sm">Cette page est réservée à l'administrateur principal.</p>;
  }
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Données & maintenance</h1>
        <p className="mt-1 text-sm text-slate-500">
          Pour un transfert de la base : annoncez d'abord une maintenance (les membres sont prévenus puis déconnectés),
          exportez les données, changez l'adresse de la base dans Render, importez le fichier, puis réactivez les connexions.
        </p>
      </div>
      <DeconnexionGenerale />
      <TransfertDonnees />
    </div>
  );
}
