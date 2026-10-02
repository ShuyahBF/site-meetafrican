// Éléments communs au transfert des données (espace d'administration et page
// publique de restauration initiale) : suivi d'une tâche de fond, barre de
// progression, rapport d'import, fenêtre.
import { useEffect, useState } from "react";
import { apiClient } from "@/lib/api";

export const PHRASE_MIN = 12;
export const EXTENSION = ".baexport";

/** Taille lisible : « 12,4 Mo ». */
export function tailleLisible(octets) {
  if (!octets && octets !== 0) return "";
  const unites = ["o", "Ko", "Mo", "Go"];
  let valeur = octets;
  let i = 0;
  while (valeur >= 1024 && i < unites.length - 1) { valeur /= 1024; i += 1; }
  return `${valeur.toLocaleString("fr-FR", { maximumFractionDigits: 1 })} ${unites[i]}`;
}

/** Date et heure locales : « 02/10/2026 14:05 ». */
export function dateHeure(iso) {
  if (!iso) return "";
  return new Date(iso).toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" });
}

/** Suivi d'une opération en tâche de fond (interrogation toutes les secondes). */
export function useSuiviTache(tacheId) {
  const [tache, setTache] = useState(null);
  useEffect(() => {
    if (!tacheId) { setTache(null); return undefined; }
    let actif = true;
    let minuteur;
    async function interroger() {
      try {
        const { data } = await apiClient.get(`/plateforme/transfert/taches/${tacheId}`);
        if (!actif) return;
        setTache(data);
        if (data.statut === "EN_COURS") minuteur = setTimeout(interroger, 1000);
      } catch {
        // Coupure réseau passagère : on réessaie un peu plus tard
        if (actif) minuteur = setTimeout(interroger, 3000);
      }
    }
    interroger();
    return () => { actif = false; clearTimeout(minuteur); };
  }, [tacheId]);
  return tache;
}

export function BarreProgression({ tache, envoi }) {
  const pourcentage = envoi != null ? envoi : (tache?.progression ?? 0);
  return (
    <div className="space-y-2">
      <p className="text-sm font-semibold">{envoi != null ? "Envoi du fichier vers le serveur…" : tache?.etape || "Préparation…"}</p>
      <div className="h-3 overflow-hidden rounded-full bg-slate-200">
        <div className="h-full rounded-full bg-gradient-to-r from-primary to-sunset transition-all" style={{ width: `${pourcentage}%` }} />
      </div>
      <p className="text-xs text-slate-500">
        {pourcentage} %{tache?.documents_total ? ` · ${tache.documents_traites.toLocaleString("fr-FR")} / ${tache.documents_total.toLocaleString("fr-FR")} élément(s)` : ""}
      </p>
      <p className="text-xs text-slate-500">Patientez sur cette page ; ne fermez pas l'onglet.</p>
    </div>
  );
}

/** Rapport de fin d'import : nombres attendus / importés / présents, avertissements. */
export function RapportImport({ tache }) {
  const rapport = tache?.rapport;
  return (
    <div className="space-y-4">
      <div className={`rounded-xl p-3 text-sm ${rapport?.conforme ? "bg-emerald-50 text-emerald-900" : "bg-amber-50 text-amber-900"}`}>
        <p className="font-bold">{rapport?.conforme ? "✅ Import terminé : tous les nombres correspondent" : "⚠️ Import terminé avec des écarts"}</p>
        <p>{rapport?.documents?.toLocaleString("fr-FR")} élément(s) importé(s){tache.source?.date_utc ? ` · export du ${dateHeure(tache.source.date_utc)}` : ""}.</p>
      </div>
      {rapport?.avertissements?.length > 0 && (
        <ul className="list-inside list-disc rounded-xl bg-amber-50 p-3 text-xs text-amber-900">
          {rapport.avertissements.map((a) => <li key={a}>{a}</li>)}
        </ul>
      )}
      <div className="max-h-72 overflow-auto rounded-xl border border-slate-100">
        <table className="w-full text-sm">
          <thead className="sticky top-0 bg-slate-50 text-left text-xs uppercase text-slate-500">
            <tr><th className="px-3 py-2">Collection</th><th className="px-3 py-2 text-right">Fichier</th><th className="px-3 py-2 text-right">Importés</th><th className="px-3 py-2 text-right">Dans la base</th></tr>
          </thead>
          <tbody>
            {(rapport?.collections || []).map((c) => (
              <tr key={c.nom} className={`border-t border-slate-100 ${c.dans_la_base < c.attendus ? "bg-rose-50" : ""}`}>
                <td className="break-all px-3 py-1.5 font-mono text-xs">{c.nom}</td>
                <td className="px-3 py-1.5 text-right font-mono">{c.attendus}</td>
                <td className="px-3 py-1.5 text-right font-mono">{c.importes}</td>
                <td className="px-3 py-1.5 text-right font-mono">{c.dans_la_base}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/** Fenêtre simple (fond assombri). `large` : pour le rapport d'import. */
export function Fenetre({ titre, onFermer, large = false, children }) {
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/60 p-4 sm:items-center">
      <div role="dialog" aria-modal="true" aria-label={titre}
        className={`w-full ${large ? "max-w-2xl" : "max-w-lg"} rounded-2xl bg-white p-5 text-ink shadow-2xl`}>
        <div className="mb-4 flex items-start justify-between gap-4">
          <h2 className="text-lg font-bold">{titre}</h2>
          <button type="button" onClick={onFermer} aria-label="Fermer" className="rounded-full px-2 py-1 text-slate-500 hover:bg-slate-100">✕</button>
        </div>
        {children}
      </div>
    </div>
  );
}

/** Champ de formulaire avec libellé et aide. */
export function Champ({ label, aide, children }) {
  return (
    <label className="block text-sm">
      <span className="mb-1 block font-semibold text-slate-700">{label}</span>
      {children}
      {aide && <span className="mt-1 block text-xs text-slate-500">{aide}</span>}
    </label>
  );
}

/** Encadré d'explication de la phrase secrète. */
export function AvertissementPhrase() {
  return (
    <div className="rounded-xl border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
      <p className="font-bold">🔑 La phrase secrète protège le fichier</p>
      <ul className="mt-1 list-inside list-disc space-y-0.5">
        <li>Le fichier contient toutes les données des membres (profils, messages, paiements…) : il est <b>entièrement chiffré</b> avec cette phrase.</li>
        <li>Elle sera <b>indispensable</b> pour importer le fichier. Elle n'est enregistrée nulle part : <b>si vous l'oubliez, personne ne pourra la retrouver</b> et le fichier sera inutilisable.</li>
        <li>Choisissez au moins {PHRASE_MIN} caractères (par exemple quelques mots sans rapport entre eux) et notez-la en lieu sûr, à part du fichier.</li>
      </ul>
    </div>
  );
}
