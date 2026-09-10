import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";

// Coquille de la zone "/secure" : sidebar à 3 entrées (Sécurisation,
// Posologie, Admin médecins) + la maquette active en plein cadre.
// Cette route n'est référencée nulle part dans la navigation du site
// (Welcome, BottomNav...) : elle n'est atteignable qu'en tapant l'URL
// directement, comme demandé ("hidden route").
//
// Desktop (>=640px) : sidebar colonne fixe, toujours visible.
// Mobile (<640px) : sidebar en tiroir (drawer) replié par défaut derrière un
// bouton ☰ — une barre horizontale fixe mangeait sinon l'écran. Le tiroir se
// referme dès qu'on choisit une page, ou qu'on tape n'importe où sur le
// fond assombri qui recouvre le contenu tant qu'il est ouvert (la maquette
// vit dans un <iframe> : un clic dedans ne remonte pas au parent, d'où ce
// fond qui capte le premier tap pour refermer plutôt que le laisser passer).
const links = [
  { to: "securisation", label: "Sécurisation" },
  { to: "posologie", label: "Posologie" },
  { to: "admin", label: "Admin (médecins)" },
];

export default function SecureLayout() {
  const [open, setOpen] = useState(false);
  const location = useLocation();

  useEffect(() => {
    setOpen(false);
  }, [location.pathname]);

  return (
    <div className="secure-shell">
      <style>{`
        .secure-shell {
          display: flex;
          flex-direction: row;
          height: 100dvh;
          width: 100%;
          background: #eef1f6;
          position: relative;
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
        .secure-menu-btn {
          display: none;
        }
        .secure-backdrop {
          display: none;
        }
        @media (max-width: 640px) {
          .secure-sidebar {
            position: fixed;
            inset: 0 auto 0 0;
            z-index: 30;
            transform: translateX(-100%);
            transition: transform 0.22s ease;
            box-shadow: 2px 0 16px rgba(0,0,0,0.3);
          }
          .secure-sidebar.open {
            transform: translateX(0);
          }
          .secure-menu-btn {
            display: flex;
            align-items: center;
            justify-content: center;
            position: fixed;
            top: 12px;
            left: 12px;
            z-index: 40;
            width: 40px;
            height: 40px;
            border-radius: 10px;
            border: none;
            background: #0e1f3d;
            color: #fff;
            font-size: 20px;
            font-family: sans-serif;
            box-shadow: 0 2px 8px rgba(0,0,0,0.3);
          }
          .secure-backdrop.open {
            display: block;
            position: fixed;
            inset: 0;
            z-index: 20;
            background: rgba(0,0,0,0.35);
          }
          .secure-main {
            width: 100%;
          }
        }
      `}</style>

      <button
        type="button"
        className="secure-menu-btn"
        aria-label={open ? "Fermer le menu" : "Ouvrir le menu"}
        onClick={() => setOpen((v) => !v)}
      >
        {open ? "✕" : "☰"}
      </button>

      <div
        className={`secure-backdrop${open ? " open" : ""}`}
        onClick={() => setOpen(false)}
      />

      <aside className={`secure-sidebar${open ? " open" : ""}`}>
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

      <main className="secure-main" onClick={() => open && setOpen(false)}>
        <Outlet />
      </main>
    </div>
  );
}
