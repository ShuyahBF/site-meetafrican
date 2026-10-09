import { useNavigate } from "react-router-dom";
import BottomSheet from "@/components/BottomSheet";

// Actions proposées par le gros bouton ✚ de la barre du bas.
const CREATE_ACTIONS = [
  { to: "/moments/publier", icon: "videocam", label: "Publier un Moment", text: "Une vidéo de 60 s max, visage flouté pour tous", tint: "bg-primary/10 text-primary" },
  { to: "/me-suivre", icon: "share_location", label: "Me suivre", text: "Partager ma position en direct avec un proche", tint: "bg-emerald-50 text-emerald-600" },
  { to: "/temoignages", icon: "format_quote", label: "Témoignages", text: "Lire et raconter une belle rencontre", tint: "bg-amber-50 text-amber-600" },
  { to: "/support", icon: "support_agent", label: "Écrire au support", text: "Une question, un souci ? On vous répond", tint: "bg-sky-50 text-sky-600" },
  { to: "/visiteurs", icon: "visibility", label: "Qui m'a vu", text: "Visites de mon profil et vues de mes Moments", tint: "bg-purple-50 text-purple-600" },
  { to: "/reglages", icon: "settings", label: "Réglages", text: "Notes vocales, transcription, son des messages, mode invisible", tint: "bg-slate-100 text-slate-600" },
];

/** Tiroir "Créer / Actions" ouvert par le bouton ✚ (le cauri). */
// Prop `support` (lot 60) : { actif, nonLus, ouvrir } fournie par la barre du bas.
//   - actif  : plateforme reliée à SAWALI et membre connecté → option affichée ;
//   - nonLus : réponses du support non lues → pastille rouge sur l'option ;
//   - ouvrir : ouvre la fenêtre de discussion avec le support SAWALI.
export default function CreateSheet({ onClose, support }) {
  const navigate = useNavigate();
  return (
    <BottomSheet title="Que voulez-vous faire ?" onClose={onClose}>
      <div className="grid grid-cols-1 gap-2 px-4 pb-6">
        {CREATE_ACTIONS.map((a) => (
          <button
            key={a.to}
            onClick={() => {
              onClose();
              navigate(a.to);
            }}
            className="flex items-center gap-3 rounded-2xl p-3 text-left transition hover:bg-slate-50 active:scale-[0.99]"
          >
            <span className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl ${a.tint}`}>
              <span className="material-symbols-outlined">{a.icon}</span>
            </span>
            <span className="min-w-0">
              <span className="block text-sm font-extrabold text-ink">{a.label}</span>
              <span className="block truncate text-xs text-slate-500">{a.text}</span>
            </span>
          </button>
        ))}

        {/* Option « Chat instantané avec le support » (lot 60, demande du
            propriétaire du 09/10/2026) : ouvre la fenêtre de discussion avec le
            support technique SAWALI (non-lus, son, requête numérotée SUP-…).
            Cachée si le support SAWALI n'est pas configuré. */}
        {support?.actif && (
          <button
            onClick={() => {
              onClose();        // on ferme d'abord le tiroir…
              support.ouvrir(); // …puis on affiche la fenêtre de discussion
            }}
            className="flex items-center gap-3 rounded-2xl p-3 text-left transition hover:bg-slate-50 active:scale-[0.99]"
          >
            <span className="relative flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-rose-50 text-rose-600">
              <span className="material-symbols-outlined">headset_mic</span>
              {/* Pastille : nombre de réponses du support non lues */}
              {support.nonLus > 0 && (
                <span className="absolute -right-1 -top-1 min-w-[18px] rounded-full bg-primary px-1 text-center text-[10px] font-bold leading-[18px] text-white ring-2 ring-white">
                  {support.nonLus > 9 ? "9+" : support.nonLus}
                </span>
              )}
            </span>
            <span className="min-w-0 flex-1">
              <span className="block text-sm font-extrabold text-ink">Chat instantané avec le support</span>
              <span className="block truncate text-xs text-slate-500">
                {support.nonLus > 0
                  ? `${support.nonLus} réponse${support.nonLus > 1 ? "s" : ""} non lue${support.nonLus > 1 ? "s" : ""} du support`
                  : "Discuter en direct avec l'assistance technique"}
              </span>
            </span>
          </button>
        )}
      </div>
    </BottomSheet>
  );
}
