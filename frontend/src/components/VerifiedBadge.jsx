// Badge "identité vérifiée" (coche bleue) — le signe d'authenticité du site,
// affiché partout où apparaît un nom de membre vérifié.
export default function VerifiedBadge({ className = "text-base" }) {
  return (
    <span
      title="Identité vérifiée"
      aria-label="Identité vérifiée"
      className={`material-symbols-outlined icon-filled align-middle text-sky-500 ${className}`}
    >
      verified
    </span>
  );
}
