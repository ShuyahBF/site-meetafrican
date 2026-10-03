import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import DerniereSauvegarde from "@/components/DerniereSauvegarde";
import MentionVersion from "@/components/MentionVersion";

const NAV = [
  { to: "/admin", label: "Tableau de bord", end: true },
  { to: "/admin/chronologie", label: "Chronologie" },
  { to: "/admin/photos", label: "Photos" },
  { to: "/admin/videos", label: "Vidéos" },
  { to: "/admin/verifications", label: "Vérifications" },
  { to: "/admin/journal-verifications", label: "Journal" },
  { to: "/admin/paiements", label: "Paiements" },
  { to: "/admin/signalements", label: "Signalements" },
  { to: "/admin/support", label: "Support" },
  { to: "/admin/communaute", label: "Témoignages & suivis" },
  { to: "/admin/abonnements", label: "Abonnements" },
  { to: "/admin/activite", label: "Activité & IP" },
  { to: "/admin/donnees-test", label: "Données de test" },
  { to: "/admin/parametres", label: "Paramètres" },
  { to: "/admin/equipe", label: "Équipe", adminOnly: true },
  { to: "/admin/donnees-maintenance", label: "Données & maintenance", adminOnly: true },
  { to: "/admin/abonnements-sessions", label: "Sessions, sauvegardes & cycle de vie", adminOnly: true },
  { to: "/admin/envoi-emails", label: "Envoi des e-mails", adminOnly: true },
  // Lot 47 — historique des connexions, présence en ligne, blocage d'IP / de comptes
  { to: "/admin/usage", label: "Usage", adminOnly: true },
];

export default function AdminLayout() {
  const { user, logout } = useAuth();

  return (
    <div className="min-h-screen bg-slate-100 font-display text-slate-900">
      <header className="flex items-center justify-between border-b border-slate-200 bg-white px-6 py-4">
        <div>
          <p className="text-lg font-bold text-primary">beAuthentik — Administration</p>
          <p className="text-xs text-slate-500">Connecté en tant que {user?.full_name}</p>
        </div>
        <button onClick={logout} className="text-sm font-semibold text-slate-500 hover:text-primary">
          Déconnexion
        </button>
      </header>

      <nav className="flex flex-wrap gap-1 border-b border-slate-200 bg-white px-4">
        {/* "Équipe", "Données & maintenance" : réservés à l'administrateur principal (pas aux modérateurs) */}
        {NAV.filter((item) => !item.adminOnly || user?.role === "admin").map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            className={({ isActive }) =>
              `border-b-2 px-4 py-3 text-sm font-semibold ${
                isActive ? "border-primary text-primary" : "border-transparent text-slate-500 hover:text-slate-800"
              }`
            }
          >
            {item.label}
          </NavLink>
        ))}
      </nav>

      <main className="mx-auto max-w-5xl px-6 py-8">
        <Outlet />
      </main>
      {/* Pied de page discret : dernière sauvegarde générale, puis version et
          lot du déploiement en cours (règle permanente) */}
      <footer className="pb-6 text-center">
        <DerniereSauvegarde />
        <MentionVersion className="mt-2" />
      </footer>
    </div>
  );
}
