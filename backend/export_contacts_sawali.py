"""Lot 75 — CONTACTS DE beAuthentik LUS PAR SAWALI (groupe « Plateforme beAuthentik » : messages WhatsApp de masse, carrousels).

Pour un développeur WinDev : UNE route de lecture seule, GET /api/sawali/contacts?limite=500&page=1, appelée par SAWALI
chaque nuit. Pas d'utilisateur connecté : la requête est SIGNÉE avec la clé partagée SAWALI_CONTACTS_HMAC (variable
d'environnement saisie par le propriétaire sur Render, même valeur que CONTACTS_HMAC_BEAUTHENTIK côté SAWALI) :
    X-Timestamp = horodatage Unix (secondes), valable 5 minutes ;
    X-Signature = HMAC-SHA256(clé, "<horodatage>.GET <chemin>?<requête>") en hexadécimal.
Clé absente → 503 (route désactivée) ; signature absente, périmée ou fausse → 401.

CONFIDENTIALITÉ (site de rencontre : être membre est déjà une information sensible) — contenu volontairement minimal :
  - seulement les MEMBRES actifs dont le téléphone est VÉRIFIÉ (code reçu), jamais les modérateurs ni les administrateurs ;
  - uniquement le PRÉNOM (premier mot du nom), le numéro et un identifiant ; ni nom de famille, e-mail, genre, âge, ville,
    photo, profil, message, abonnement ni mot de passe ;
  - lot 78 : le consentement WhatsApp (accord ou retrait, avec sa date) est transmis SEULEMENT si la personne l'a donné
    elle-même (case cochée à l'inscription) ; sinon rien : SAWALI ne diffuse un carrousel qu'aux personnes qui ont donné
    leur accord elles-mêmes.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import re
import time
from typing import Any, Dict, List, Optional

VALIDITE_SECONDES = 300
LIMITE_DEFAUT = 500
LIMITE_MAX = 1000
VARIABLE_CLE = "SAWALI_CONTACTS_HMAC"


def cle_partagee() -> str:
    return (os.environ.get(VARIABLE_CLE) or "").strip()


def signer(cle: str, horodatage: str, chemin: str, requete: str) -> str:
    """HMAC-SHA256 hexadécimal de « <horodatage>.GET <chemin>?<requête> » (même calcul que SAWALI)."""
    cible = f"{chemin}?{requete}" if requete else chemin
    return hmac.new(cle.encode("utf-8"), f"{horodatage}.GET {cible}".encode("utf-8"), hashlib.sha256).hexdigest()


def signature_valide(cle: str, horodatage: str, signature: str, chemin: str, requete: str, maintenant: Optional[float] = None) -> bool:
    """Vrai si l'horodatage est récent (± 5 minutes) et la signature exacte (comparaison à temps constant)."""
    try:
        ecart = abs((maintenant if maintenant is not None else time.time()) - int(horodatage))
    except (TypeError, ValueError):
        return False
    return ecart <= VALIDITE_SECONDES and hmac.compare_digest(signer(cle, horodatage, chemin, requete), signature or "")


def prenom(nom_complet: Optional[str]) -> str:
    """Premier mot du nom (« Awa Ouedraogo » → « Awa ») : on ne transmet jamais le nom de famille."""
    mots = (nom_complet or "").split()
    return mots[0][:40] if mots else ""


async def tous_les_contacts(db) -> List[Dict[str, Any]]:
    """Membres actifs au téléphone vérifié, un contact par numéro, triés de façon stable."""
    contacts, vus = [], set()
    async for u in db.users.find({"is_active": {"$ne": False}, "phone_verified": True, "phone": {"$nin": [None, ""]},
                                  "role": {"$nin": ["admin", "moderator"]}},
                                 {"_id": 0, "id": 1, "full_name": 1, "phone": 1, "accepte_whatsapp": 1, "accepte_whatsapp_le": 1}):
        tel = re.sub(r"\D", "", u.get("phone") or "")
        if len(tel) < 8 or tel in vus:
            continue
        vus.add(tel)
        contact = {"id": u["id"], "nom": prenom(u.get("full_name")), "telephone": tel, "role": "membre", "societe": "beAuthentik"}
        if isinstance(u.get("accepte_whatsapp"), bool):      # lot 78 : accord (ou retrait) donné par la personne elle-même
            contact.update({"accepte_whatsapp": u["accepte_whatsapp"], "accepte_le": u.get("accepte_whatsapp_le")})
        contacts.append(contact)
    return sorted(contacts, key=lambda c: c["id"])


async def page_de_contacts(db, page: int, limite: int) -> Dict[str, Any]:
    limite = max(1, min(int(limite or LIMITE_DEFAUT), LIMITE_MAX))
    tous = await tous_les_contacts(db)
    pages = max(1, -(-len(tous) // limite))
    page = max(1, min(int(page or 1), pages))
    return {"plateforme": "beAuthentik", "page": page, "pages": pages, "total": len(tous),
            "contacts": tous[(page - 1) * limite: page * limite]}
