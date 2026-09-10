import { NavLink, Outlet } from "react-router-dom";

// Coquille de la zone "/secure" : une sidebar fixe à 3 entrées (Sécurisation,
// Posologie, Admin médecins) + la maquette active en plein cadre à droite.
// Cette route n'est référencée nulle part dans la navigation du site
// (Welcome, BottomNav...) : elle n'est atteignable qu'en tapant l'URL
// directement, comme demandé ("hidden route").
const links = [
  { to: "securisation", label: "Sécurisation" },
  { to: "posologie", label: "Posologie" },
  { to: "admin", label: "Admin (médecins)" },
];

export default function SecureLayout() {
  return (
    <div style={{ display: "flex", height: "100dvh", width: "100%", background: "#0e1f3d" }}>
      <aside
        style={{
          width: 220,
          flex: "0 0 220px",
          background: "#0e1f3d",
          color: "#fff",
          padding: "20px 14px",
          boxSizing: "border-box",
        }}
      >
        <div style={{ fontFamily: "sans-serif", fontWeight: 700, fontSize: 15, opacity: 0.7, marginBottom: 18, letterSpacing: 0.4 }}>
          VIDAL — zone test
        </div>
        <nav style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          {links.map((l) => (
            <NavLink
              key={l.to}
              to={l.to}
              style={({ isActive }) => ({
                display: "block",
                padding: "10px 12px",
                borderRadius: 10,
                fontFamily: "sans-serif",
                fontSize: 14,
                fontWeight: 600,
                textDecoration: "none",
                color: "#fff",
                background: isActive ? "rgba(255,255,255,0.16)" : "transparent",
              })}
            >
              {l.label}
            </NavLink>
          ))}
        </nav>
      </aside>
      <main style={{ flex: 1, minWidth: 0, background: "#eef1f6" }}>
        <Outlet />
      </main>
    </div>
  );
}
