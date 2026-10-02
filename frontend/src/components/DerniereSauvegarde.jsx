import { useEffect, useState } from "react";
import { apiClient, FOND } from "@/lib/api";

/** JJ/MM/AAAA HH:MM (heure locale). */
function dateHeure(iso) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const p = (n) => String(n).padStart(2, "0");
  return `${p(d.getDate())}/${p(d.getMonth() + 1)}/${d.getFullYear()} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

/**
 * « Dernière sauvegarde générale : JJ/MM/AAAA HH:MM » (sauvegarde automatique de
 * toute la plateforme, backend/sauvegarde_auto.py), ou « Aucune sauvegarde
 * enregistrée » en orange. beAuthentik n'a pas de sauvegarde propre à chaque
 * membre : seule la sauvegarde générale est affichée.
 */
export default function DerniereSauvegarde({ className = "" }) {
  const [date, setDate] = useState(undefined);
  useEffect(() => {
    apiClient.get("/sauvegarde-auto/derniere", FOND).then((r) => setDate(r.data.date)).catch(() => setDate(undefined));
  }, []);
  if (date === undefined) return null;
  return date ? (
    <p className={`text-xs text-slate-400 ${className}`}>Dernière sauvegarde générale : {dateHeure(date)}</p>
  ) : (
    <p className={`text-xs font-semibold text-amber-600 ${className}`}>Aucune sauvegarde enregistrée</p>
  );
}
