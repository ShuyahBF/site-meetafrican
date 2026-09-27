import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { apiClient } from "@/lib/api";
import { useProfileOptions } from "@/hooks/useProfileOptions";
import ProfileTile from "@/components/ProfileTile";
import BottomNav from "@/components/BottomNav";

// Critères par défaut (bouton "Réinitialiser").
const DEFAULT_FILTERS = {
  age_min: 25,
  age_max: 40,
  city: "",
  country: "",
  relationship_goal: "",
  children: "",
  interests: [],
  verified_only: false,
  online_only: false,
  with_video_only: false,
};
const STORAGE_KEY = "maf_search_filters";
const PAGE_SIZE = 20;

// Critères mémorisés d'une visite à l'autre (confort) — lecture protégée :
// le stockage du navigateur peut être indisponible (navigation privée…).
function loadSavedFilters() {
  try {
    return { ...DEFAULT_FILTERS, ...JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}") };
  } catch {
    return DEFAULT_FILTERS;
  }
}

// Convertit les critères du formulaire en paramètres d'URL de GET /search
// (les critères vides ne sont pas envoyés).
function toParams(f) {
  // Curseur au maximum (70) = "70 ans et plus" : on lève la borne haute.
  const p = { age_min: f.age_min, age_max: f.age_max >= 70 ? 99 : f.age_max };
  if (f.city.trim()) p.city = f.city.trim();
  if (f.country.trim()) p.country = f.country.trim();
  if (f.relationship_goal) p.relationship_goal = f.relationship_goal;
  if (f.children) p.children = f.children;
  if (f.interests.length) p.interests = f.interests.join(",");
  if (f.verified_only) p.verified_only = true;
  if (f.online_only) p.online_only = true;
  if (f.with_video_only) p.with_video_only = true;
  return p;
}

/**
 * Recherche avancée (maquette Stitch n°10), en version fond blanc :
 * critères -> compteur en direct "X profils correspondent" -> grille de résultats.
 */
export default function Search() {
  const navigate = useNavigate();
  const options = useProfileOptions();
  const [filters, setFilters] = useState(loadSavedFilters);
  const [count, setCount] = useState(null);
  const [results, setResults] = useState(null); // null = formulaire affiché
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(false);

  const params = useMemo(() => toParams(filters), [filters]);

  // Compteur en direct, recalculé 400 ms après la dernière modification.
  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(filters));
    } catch {
      // stockage indisponible : les critères ne seront simplement pas mémorisés
    }
    const t = setTimeout(() => {
      apiClient.get("/search", { params: { ...params, limit: 1 } }).then((r) => setCount(r.data.total)).catch(() => {});
    }, 400);
    return () => clearTimeout(t);
  }, [params, filters]);

  const set = (key, value) => setFilters((f) => ({ ...f, [key]: value }));
  const toggleInterest = (i) =>
    set("interests", filters.interests.includes(i) ? filters.interests.filter((x) => x !== i) : [...filters.interests, i]);

  const showResults = async (append = false) => {
    setLoading(true);
    try {
      const skip = append ? results.length : 0;
      const r = await apiClient.get("/search", { params: { ...params, skip, limit: PAGE_SIZE } });
      setResults((prev) => (append ? [...prev, ...r.data.results] : r.data.results));
      setHasMore(skip + r.data.results.length < r.data.total);
      if (!append) window.scrollTo({ top: 0 });
    } finally {
      setLoading(false);
    }
  };

  // --- Grille de résultats -------------------------------------------------
  if (results) {
    return (
      <div className="flex min-h-[100dvh] flex-col bg-white font-display text-ink">
        <header className="sticky top-0 z-10 flex items-center gap-3 bg-white/90 px-4 py-4 backdrop-blur">
          <button onClick={() => setResults(null)} aria-label="Modifier les critères" className="flex h-10 w-10 items-center justify-center rounded-full bg-slate-100">
            <span className="material-symbols-outlined">tune</span>
          </button>
          <div>
            <h1 className="text-lg font-extrabold">Résultats</h1>
            <p className="text-xs text-slate-500">{count ?? results.length} profil{(count ?? 0) > 1 ? "s" : ""} · {filters.age_min}-{filters.age_max} ans</p>
          </div>
        </header>
        <main className="flex-1 px-4 pb-8">
          {results.length === 0 ? (
            <div className="py-20 text-center">
              <p className="text-5xl">🌍</p>
              <p className="mt-3 font-extrabold">Personne ne correspond… pour l'instant</p>
              <p className="mt-1 text-sm text-slate-500">Élargissez la tranche d'âge ou retirez un critère.</p>
              <button onClick={() => setResults(null)} className="btn-ghost mt-5">Modifier les critères</button>
            </div>
          ) : (
            <>
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                {results.map((p) => <ProfileTile key={p.id} profile={p} />)}
              </div>
              {hasMore && (
                <button onClick={() => showResults(true)} disabled={loading} className="btn-ghost mt-6 w-full">
                  {loading ? "Chargement…" : "Voir plus de profils"}
                </button>
              )}
            </>
          )}
        </main>
        <BottomNav />
      </div>
    );
  }

  // --- Formulaire de critères ------------------------------------------------
  return (
    <div className="min-h-[100dvh] bg-white font-display text-ink">
      <header className="sticky top-0 z-10 flex items-center justify-between bg-white/90 px-4 py-4 backdrop-blur">
        <button onClick={() => navigate(-1)} aria-label="Fermer" className="flex h-10 w-10 items-center justify-center rounded-full bg-slate-100">
          <span className="material-symbols-outlined">close</span>
        </button>
        <h1 className="text-base font-extrabold">Recherche avancée</h1>
        <button onClick={() => setFilters(DEFAULT_FILTERS)} className="text-sm font-bold text-primary">Réinitialiser</button>
      </header>

      <main className="mx-auto max-w-lg space-y-8 px-5 pb-36 pt-2">
        <section>
          <h2 className="section-title">Tranche d'âge</h2>
          <AgeRange min={filters.age_min} max={filters.age_max} onChange={(a, b) => setFilters((f) => ({ ...f, age_min: a, age_max: b }))} />
        </section>

        <section className="grid grid-cols-2 gap-3">
          <div>
            <h2 className="section-title">Ville</h2>
            <input value={filters.city} onChange={(e) => set("city", e.target.value)} placeholder="Ex. Dakar" className="input" />
          </div>
          <div>
            <h2 className="section-title">Pays</h2>
            <input value={filters.country} onChange={(e) => set("country", e.target.value)} placeholder="Ex. Sénégal" className="input" />
          </div>
        </section>

        <section>
          <h2 className="section-title">Type de relation</h2>
          <div className="flex flex-wrap gap-2">
            <Choice active={!filters.relationship_goal} onClick={() => set("relationship_goal", "")}>Peu importe</Choice>
            {options?.relationship_goals.map((o) => (
              <Choice key={o.value} active={filters.relationship_goal === o.value} onClick={() => set("relationship_goal", o.value)}>
                {o.label}
              </Choice>
            ))}
          </div>
        </section>

        <section>
          <h2 className="section-title">Enfants</h2>
          <select value={filters.children} onChange={(e) => set("children", e.target.value)} className="input select">
            <option value="">Peu importe</option>
            {options?.children.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
        </section>

        <section>
          <h2 className="section-title">Centres d'intérêt</h2>
          <div className="flex flex-wrap gap-2">
            {options?.interests.map((i) => (
              <Choice key={i} active={filters.interests.includes(i)} onClick={() => toggleInterest(i)}>{i}</Choice>
            ))}
          </div>
        </section>

        <section className="card divide-y divide-slate-100 px-4">
          <Toggle icon="verified" label="Identité vérifiée uniquement" checked={filters.verified_only} onChange={(v) => set("verified_only", v)} />
          <Toggle icon="bolt" label="En ligne maintenant" checked={filters.online_only} onChange={(v) => set("online_only", v)} />
          <Toggle icon="play_circle" label="A publié des Moments" checked={filters.with_video_only} onChange={(v) => set("with_video_only", v)} />
        </section>
      </main>

      {/* Pied fixe : compteur en direct + bouton */}
      <footer className="pb-safe fixed inset-x-0 bottom-0 border-t border-slate-100 bg-white/95 px-5 pt-3 backdrop-blur">
        <div className="mx-auto max-w-lg">
          <p className="mb-2 text-center text-sm text-slate-500">
            <span className="font-extrabold text-ink">{count ?? "…"}</span> profil{count > 1 ? "s" : ""} correspond{count > 1 ? "ent" : ""} à vos critères
          </p>
          <button onClick={() => showResults(false)} disabled={loading} className="btn-primary mb-2 w-full">
            {loading ? "Recherche…" : "Voir les résultats"}
          </button>
        </div>
      </footer>
    </div>
  );
}

function Choice({ active, onClick, children }) {
  return (
    <button type="button" onClick={onClick} className={`chip ${active ? "chip-active" : ""}`}>
      {children}
    </button>
  );
}

function Toggle({ icon, label, checked, onChange }) {
  return (
    <label className="flex cursor-pointer items-center gap-3 py-3.5">
      <span className="material-symbols-outlined text-primary">{icon}</span>
      <span className="flex-1 text-sm font-semibold">{label}</span>
      <input type="checkbox" className="peer sr-only" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      <span className="relative h-7 w-12 rounded-full bg-slate-200 transition peer-checked:bg-primary after:absolute after:left-1 after:top-1 after:h-5 after:w-5 after:rounded-full after:bg-white after:shadow after:transition peer-checked:after:translate-x-5" />
    </label>
  );
}

/**
 * Double curseur d'âge (min / max) : deux <input type="range"> superposés
 * sur une même piste, la portion sélectionnée étant colorée en dégradé.
 */
function AgeRange({ min, max, onChange, lower = 18, upper = 70 }) {
  const pct = (v) => ((v - lower) / (upper - lower)) * 100;
  const thumb =
    "pointer-events-none absolute inset-0 h-7 w-full appearance-none bg-transparent [&::-webkit-slider-thumb]:pointer-events-auto [&::-webkit-slider-thumb]:h-7 [&::-webkit-slider-thumb]:w-7 [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:border-4 [&::-webkit-slider-thumb]:border-white [&::-webkit-slider-thumb]:bg-primary [&::-webkit-slider-thumb]:shadow-lg [&::-moz-range-thumb]:pointer-events-auto [&::-moz-range-thumb]:h-6 [&::-moz-range-thumb]:w-6 [&::-moz-range-thumb]:rounded-full [&::-moz-range-thumb]:border-4 [&::-moz-range-thumb]:border-white [&::-moz-range-thumb]:bg-primary";
  return (
    <div>
      <p className="mb-3 text-2xl font-extrabold">
        {min} <span className="text-slate-300">—</span> {max}
        {max >= upper ? "+" : ""} <span className="text-base font-bold text-slate-400">ans</span>
      </p>
      <div className="relative h-7">
        <div className="absolute inset-x-0 top-1/2 h-1.5 -translate-y-1/2 rounded-full bg-slate-100" />
        <div
          className="absolute top-1/2 h-1.5 -translate-y-1/2 rounded-full bg-brand"
          style={{ left: `${pct(min)}%`, right: `${100 - pct(max)}%` }}
        />
        <input type="range" min={lower} max={upper} value={min} aria-label="Âge minimum"
          onChange={(e) => onChange(Math.min(Number(e.target.value), max), max)} className={thumb} />
        <input type="range" min={lower} max={upper} value={max} aria-label="Âge maximum"
          onChange={(e) => onChange(min, Math.max(Number(e.target.value), min))} className={thumb} />
      </div>
    </div>
  );
}
