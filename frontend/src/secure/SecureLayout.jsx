import { NavLink, Outlet } from "react-router-dom";

// Coquille de la zone "/secure" : sidebar à 3 entrées (Sécurisation,
// Posologie, Admin médecins) + la maquette active en plein cadre.
// Cette route n'est référencée nulle part dans la navigation du site
// (Welcome, BottomNav...) : elle n'est atteignable qu'en tapant l'URL
// directement, comme demandé ("hidden route").
//
// Sur mobile (<640px), une sidebar large en dur mangeait tout l'écran et ne
// laissait pas de place pour la maquette : on bascule alors en barre
// horizontale compacte en haut, la maquette prenant tout le reste.
const links = [
  { to: "securisation", label: "Sécurisation" },
  { to: "posologie", label: "Posologie" },
  { to: "admin", label: "Admin (médecins)" },
];

export default function SecureLayout() {
  return (
    <div className="secure-shell">
      <style>{`
        .secure-shell {
          display: flex;
          flex-direction: row;
          height: 100dvh;
          width: 100%;
          background: #0e1f3d;
        }
        .secure-sidebar {
          width: 220px;
          flex: 0 0 220px;
          background: #0e1f3d;
          color: #fff;
          padding: 20px 14px;
          box-sizing: border-box;
          overflow-y: auto;
        }
        .secure-sidebar-title {
          font-family: sans-serif;
          font-weight: 700;
          font-size: 15px;
          opacity: 0.7;
          margin-bottom: 18px;
          letter-spacing: 0.4px;
        }
        .secure-nav {
          display: flex;
          flex-direction: column;
          gap: 6px;
        }
        .secure-nav a {
          display: block;
          padding: 10px 12px;
          border-radius: 10px;
          font-family: sans-serif;
          font-size: 14px;
          font-weight: 600;
          text-decoration: none;
          color: #fff;
          background: transparent;
          white-space: nowrap;
        }
        .secure-nav a.active {
          background: rgba(255,255,255,0.16);
        }
        .secure-main {
          flex: 1;
          min-width: 0;
          background: #eef1f6;
        }
        @media (max-width: 640px) {
          .secure-shell {
            flex-direction: column;
          }
          .secure-sidebar {
            width: 100%;
            flex: 0 0 auto;
            padding: 10px 12px;
          }
          .secure-sidebar-title {
            margin-bottom: 8px;
          }
          .secure-nav {
            flex-direction: row;
            flex-wrap: wrap;
            gap: 8px;
          }
          .secure-nav a {
            padding: 8px 10px;
            font-size: 13px;
          }
          .secure-main {
            flex: 1;
            min-height: 0;
          }
        }
      `}</style>
      <aside className="secure-sidebar">
        <div className="secure-sidebar-title">VIDAL — zone test</div>
        <nav className="secure-nav">
          {links.map((l) => (
            <NavLink
              key={l.to}
              to={l.to}
              className={({ isActive }) => (isActive ? "active" : undefined)}
            >
              {l.label}
            </NavLink>
          ))}
        </nav>
      </aside>
      <main className="secure-main">
        <Outlet />
      </main>
    </div>
  );
}
