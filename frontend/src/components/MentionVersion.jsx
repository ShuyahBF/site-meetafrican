import { DATE_BUILD, LIBELLE_VERSION } from "@/version";

/**
 * Mention discrète « Version X · Lot N · hash » (règle permanente : version et
 * lot visibles sur la page de connexion et dans tout le portail).
 *
 * Les valeurs viennent toutes de src/version.js (source unique).
 * Survol de la souris : la date de compilation s'affiche en info-bulle.
 *
 * `className` : classes supplémentaires (marges, couleur sur fond sombre…).
 */
export default function MentionVersion({ className = "" }) {
  // Date de compilation lisible en français (ex. « 03/10/2026 14:05 »), si connue
  const dateLisible = DATE_BUILD
    ? new Date(DATE_BUILD).toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" })
    : "";

  return (
    <p
      className={`select-text text-center text-[10px] font-medium tracking-wide text-slate-400 ${className}`}
      title={dateLisible ? `Compilé le ${dateLisible}` : undefined}
      data-testid="mention-version"
    >
      {LIBELLE_VERSION}
    </p>
  );
}
