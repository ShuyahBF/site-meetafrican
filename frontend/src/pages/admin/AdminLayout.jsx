import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";

const NAV = [
  { to: "/admin", label: "Tableau de bord", end: true },
  { to: "/admin/comptes", label: "Comptes" },
  { to: "/admin/photos", label: "Photos" },
  { to: "/admin/verifications", label: "Vérifications" },
  { to: "/admin/paiements", label: "Paiements" },
  { to: "/admin/signalements", label: "Signalements" },
  { to: "/admin/abonnements", label: "Abonnements" },
  { to: "/admin/parametres", label: "Paramètres" },
];

export default function AdminLayout() {
  const { user, logout } = useAuth();

  return (
    <div className="min-h-screen bg-slate-100 font-display text-slate-900">
      <header className="flex items-center justify-between border-b border-slate-200 bg-white px-6 py-4">
        <div>
          <p className="text-lg font-bold text-primary">MeetAfrican — Administration</p>
          <p className="text-xs text-slate-500">Connecté en tant que {user?.full_name}</p>
        </div>
        <button onClick={logout} className="text-sm font-semibold text-slate-500 hover:text-primary">
          Déconnexion
        </button>
      </header>

      <nav className="flex flex-wrap gap-1 border-b border-slate-200 bg-white px-4">
        {NAV.map((item) => (
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
    </div>
  );
}
