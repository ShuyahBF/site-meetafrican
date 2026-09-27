import { Link } from "react-router-dom";
import ProfilePhoto from "@/components/ProfilePhoto";
import VerifiedBadge from "@/components/VerifiedBadge";

// Vignette de profil (grille de résultats de recherche) : photo en
// portrait, nom/âge/ville en surimpression, pastille "en ligne".
export default function ProfileTile({ profile }) {
  return (
    <Link to={`/profils/${profile.id}`} className="group relative block aspect-[3/4] overflow-hidden rounded-3xl bg-slate-100 shadow-sm">
      <ProfilePhoto profile={profile} className="h-full w-full transition duration-300 group-hover:scale-105" />
      <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/75 to-transparent p-3 pt-10 text-white">
        <p className="truncate text-sm font-extrabold">
          {profile.full_name.split(" ")[0]}
          {profile.age ? `, ${profile.age}` : ""} {profile.verification_status === "verified" && <VerifiedBadge className="text-sm" />}
        </p>
        {profile.city && <p className="truncate text-[11px] font-semibold text-white/80">{profile.city}</p>}
      </div>
      {profile.is_online && (
        <span className="absolute right-2.5 top-2.5 rounded-full bg-emerald-500 px-2 py-0.5 text-[10px] font-bold text-white shadow">
          En ligne
        </span>
      )}
    </Link>
  );
}
