"""Lot 66 — Page Facebook de beAuthentik animée par Liluvine (SAWALI).

Demande du propriétaire (09/10/2026) : « Liluvine anime une page Facebook ; elle y publiera quelques photos de membres
avec leur propre message » ; puis : « visage masqué ; le texte est celui que le membre a mis dans sa bio, mais modéré
par l'IA ».

Règles (pour un développeur WinDev : ce fichier est la « procédure globale » du partage Facebook) :
  - seul un membre qui a coché « J'accepte que beAuthentik publie ma photo masquée et ma bio sur sa page Facebook »
    (champ `partage_facebook` de sa fiche) peut être proposé ; il peut décocher à tout moment ;
  - la photo publiée est TOUJOURS la version masquée (bandeau ou masque sanitaire + logo) d'une photo approuvée ;
  - on ne transmet que le prénom, l'âge, la ville et la bio : jamais le nom complet, l'e-mail, le téléphone ;
  - la bio est modérée par l'IA côté SAWALI avant publication (une bio refusée n'est pas publiée) ;
  - un membre n'est pas reproposé avant DELAI_REPUBLICATION_JOURS jours.

Échanges avec SAWALI : par le canal signé existant (routes/transmission_wa.py, route /api/webhooks/liluvine-retour,
signature HMAC avec la clé LILUVINE_WA_HMAC déjà partagée) :
  {"type": "facebook_candidats", "nombre": 3}            → {"candidats": [...]}
  {"type": "facebook_publie", "membre_id": "…", "post_id": "…"} → {"ok": true}
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from db import db
from models import _age_from_birthdate

TYPE_CANDIDATS = "facebook_candidats"
TYPE_PUBLIE = "facebook_publie"
DELAI_REPUBLICATION_JOURS = 60     # un même membre n'est pas republié avant 60 jours
NOMBRE_MAX = 10                    # au plus 10 candidats par demande


def _maintenant() -> datetime:
    return datetime.now(timezone.utc)


def _prenom(nom_complet: str) -> str:
    """Prénom seul (premier mot du nom affiché) : le nom de famille n'est jamais publié."""
    return (nom_complet or "").strip().split(" ")[0][:40]


def _photo_masquee(photos: List[Dict[str, Any]]) -> Optional[str]:
    """Version masquée de la photo principale approuvée (sinon de la première photo approuvée)."""
    approuvees = [p for p in photos or [] if p.get("status") == "approved" and p.get("masked_url")]
    if not approuvees:
        return None
    principale = next((p for p in approuvees if p.get("is_primary")), approuvees[0])
    return principale["masked_url"]


async def candidats(nombre: int = 3) -> List[Dict[str, Any]]:
    """Membres consentants, photo masquée approuvée et bio renseignée, pas publiés depuis 60 jours.
    Les moins récemment publiés (ou jamais publiés) d'abord, puis les plus actifs."""
    nombre = max(1, min(int(nombre or 3), NOMBRE_MAX))
    limite = (_maintenant() - timedelta(days=DELAI_REPUBLICATION_JOURS)).isoformat()
    filtre = {
        "partage_facebook": True, "is_active": {"$ne": False}, "role": "user", "is_test_data": {"$ne": True},
        "bio": {"$nin": [None, ""]},
        "photos": {"$elemMatch": {"status": "approved", "masked_url": {"$nin": [None, ""]}}},
        "$or": [{"facebook_publie_le": {"$exists": False}}, {"facebook_publie_le": None},
                {"facebook_publie_le": {"$lt": limite}}],
    }
    docs = await db.users.find(filtre, {"_id": 0, "id": 1, "full_name": 1, "birthdate": 1, "city": 1,
                                        "country": 1, "bio": 1, "photos": 1, "facebook_publie_le": 1,
                                        "last_seen_at": 1}) \
        .sort([("facebook_publie_le", 1), ("last_seen_at", -1)]).to_list(nombre)
    sortie = []
    for d in docs:
        photo = _photo_masquee(d.get("photos"))
        if not photo:
            continue
        sortie.append({
            "membre_id": d["id"], "prenom": _prenom(d.get("full_name")), "age": _age_from_birthdate(d.get("birthdate")),
            "ville": d.get("city"), "pays": d.get("country"), "bio": (d.get("bio") or "")[:500], "photo_url": photo,
        })
    return sortie


async def marquer_publie(membre_id: str, post_id: Optional[str]) -> bool:
    """Note la publication (date et identifiant du post Facebook) sur la fiche du membre."""
    r = await db.users.update_one({"id": str(membre_id or "")}, {"$set": {
        "facebook_publie_le": _maintenant().isoformat(), "facebook_post_id": (post_id or None)}})
    return r.matched_count == 1


async def traiter(donnees: Dict[str, Any]) -> Dict[str, Any]:
    """Réponse aux demandes signées de SAWALI (types facebook_candidats / facebook_publie)."""
    if donnees.get("type") == TYPE_CANDIDATS:
        return {"candidats": await candidats(donnees.get("nombre") or 3)}
    return {"ok": await marquer_publie(donnees.get("membre_id"), donnees.get("post_id"))}
