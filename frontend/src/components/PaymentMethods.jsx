// Moyens de paiement acceptés, affichés sous forme de pastilles colorées
// (texte, pas de logos officiels : les marques restent la propriété de
// leurs titulaires). Les paiements Mobile Money passent par la page de
// paiement sécurisée de PawaPay.
export const PAYMENT_METHODS = [
  { name: "Orange Money", color: "#ff7900" },
  { name: "Moov Money", color: "#0066b3" },
  { name: "Telecel Money", color: "#e30613" },
  { name: "Sank Money", color: "#00a651" },
  { name: "PawaPay", color: "#5b21b6" },
];

/**
 * `compact` : une ligne discrète (sous un bouton de paiement) ;
 * sinon : pastilles plus grandes avec un titre (page d'accueil).
 */
export default function PaymentMethods({ compact = false, className = "" }) {
  if (compact) {
    return (
      <div className={`flex flex-wrap items-center justify-center gap-1.5 ${className}`}>
        {PAYMENT_METHODS.map((m) => (
          <span key={m.name} className="inline-flex items-center gap-1 rounded-full bg-slate-50 px-2 py-0.5 text-[11px] font-semibold text-slate-600 ring-1 ring-slate-200">
            <span className="h-1.5 w-1.5 rounded-full" style={{ background: m.color }} />
            {m.name}
          </span>
        ))}
      </div>
    );
  }
  return (
    <div className={`text-center ${className}`}>
      <p className="flex items-center justify-center gap-2 text-xs font-bold uppercase tracking-[0.15em] text-slate-400">
        <span className="material-symbols-outlined text-base">lock</span>
        Paiements acceptés
      </p>
      <div className="mt-3 flex flex-wrap items-center justify-center gap-2">
        {PAYMENT_METHODS.map((m) => (
          <span
            key={m.name}
            className="inline-flex items-center gap-2 rounded-full bg-white px-4 py-2 text-sm font-extrabold shadow-sm ring-1 ring-slate-200"
            style={{ color: m.color }}
          >
            <span className="h-2.5 w-2.5 rounded-full" style={{ background: m.color }} />
            {m.name}
          </span>
        ))}
      </div>
      <p className="mt-2 text-xs text-slate-400">Paiement Mobile Money sécurisé via PawaPay · en FCFA · sans carte bancaire</p>
    </div>
  );
}
