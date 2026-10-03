"""Onglet « Usage » du back-office (lot 47) : journal des connexions, présence en
ligne et blocage d'adresses IP ou de comptes.

Demande du propriétaire (super-administrateur, rôle « admin » uniquement) :

1. JOURNAL DES CONNEXIONS — collection `maf_connexions_journal`
   Une ligne par connexion RÉUSSIE (mot de passe, inscription, « Continuer avec
   TikTok ») et par tentative REFUSÉE pour cause de blocage : date, IP réelle du
   visiteur (1re entrée de X-Forwarded-For, voir activity.ip_from_headers),
   compte, méthode, appareil, identifiant de session (« sid »). Purge
   automatique après 180 jours (index TTL sur `date_dt`, voir db.py).

2. PRÉSENCE (pastille en tête de ligne, mêmes règles que SAWALI)
   On réutilise la DERNIÈRE ACTIVITÉ déjà notée sur chaque session
   (sessions_comptes.py : au plus une écriture par minute et par session, jamais
   pour une requête de fond « X-BA-Fond ») :
     - verte  : session ouverte, activité dans les 5 dernières minutes ;
     - orange : session ouverte, sans activité depuis 5 à 10 minutes ;
     - rouge  : plus de 10 minutes sans activité, ou session fermée / expirée.

3. BLOCAGES — collection `maf_blocages` (un document par blocage)
     - type « ip » + portée « tous »   : l'adresse IP est refusée pour TOUS les comptes ;
     - type « ip » + portée « compte » : l'IP est refusée pour CE compte seulement ;
     - type « compte »                 : le compte est refusé quelle que soit l'IP.
   Un blocage levé n'est pas effacé : il passe à `actif = False` (historique).
   Effet : connexion refusée (403, code « acces_suspendu ») ET sessions en cours
   fermées ; à la requête suivante l'appareil reçoit le même 403 et le site
   affiche la page « Accès momentanément suspendu ».
   Le super-administrateur n'est JAMAIS bloqué (ni à la création du blocage, ni
   au contrôle) : impossible de s'enfermer dehors.
   Chaque action (blocage, levée, réglage du contact) est journalisée dans
   `maf_blocages_journal` (qui, quand, quoi) et dans le journal d'activité.
"""
from __future__ import annotations

import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException

from activity import current_ip, log_activity
from db import db

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------
CONSERVATION_JOURS = 180          # durée de conservation du journal des connexions
SEUIL_ACTIF_S = 5 * 60            # pastille verte : activité depuis moins de 5 min
SEUIL_ABSENT_S = 10 * 60          # pastille orange jusqu'à 10 min, rouge au-delà
DUREE_CACHE = 15.0                # blocages relus en base au plus toutes les 15 s

# Code et message renvoyés au site (le frontend affiche alors la page dédiée).
# Volontairement sans détail technique (ni IP, ni motif).
CODE_SUSPENDU = "acces_suspendu"
MESSAGE_SUSPENDU = ("Accès momentanément suspendu. Contactez l'Administrateur pour réclamer "
                    "votre accès ou contester la décision.")

# Libellés lisibles des méthodes de connexion
METHODES = {
    "mot_de_passe": "Mot de passe",
    "inscription": "Inscription",
    "tiktok": "TikTok",
    "session": "Session en cours",
}

# Réglage « contact affiché sur la page de blocage » (collection settings)
ID_CONTACT = "contact_acces_suspendu"

# Liste des blocages actifs gardée en mémoire (lue à chaque requête authentifiée)
_cache: dict = {"lu_a": 0.0, "blocages": None}


def vider_cache() -> None:
    """Oublie la liste en mémoire : elle sera relue en base à la prochaine requête."""
    _cache.update(lu_a=0.0, blocages=None)


def _maintenant() -> datetime:
    return datetime.now(timezone.utc)


def exception_suspendu() -> HTTPException:
    """Réponse 403 qui fait afficher la page « Accès momentanément suspendu »."""
    return HTTPException(403, {"code": CODE_SUSPENDU, "message": MESSAGE_SUSPENDU})


# ---------------------------------------------------------------------------
# Lecture des blocages actifs (avec cache)
# ---------------------------------------------------------------------------
async def blocages_actifs(cache: bool = True) -> list[dict]:
    if cache and _cache["blocages"] is not None and time.monotonic() - _cache["lu_a"] < DUREE_CACHE:
        return _cache["blocages"]
    liste = await db.blocages.find({"actif": True}, {"_id": 0}).to_list(5000)
    _cache.update(lu_a=time.monotonic(), blocages=liste)
    return liste


def motif_blocage(blocages: list[dict], user_id: Optional[str], ip: Optional[str]) -> Optional[str]:
    """Pourquoi ce compte / cette IP est refusé : « compte », « ip » ou None (autorisé)."""
    for b in blocages:
        if b.get("type") == "compte" and user_id and b.get("user_id") == user_id:
            return "compte"
    for b in blocages:
        if b.get("type") != "ip" or not ip or b.get("ip") != ip:
            continue
        if b.get("portee") == "tous" or (user_id and b.get("user_id") == user_id):
            return "ip"
    return None


def etat_ip(blocages: list[dict], user_id: Optional[str], ip: Optional[str]) -> str:
    """État de l'IP pour l'affichage : « bloquee_tous », « bloquee_compte » ou « autorisee »."""
    for b in blocages:
        if b.get("type") == "ip" and ip and b.get("ip") == ip and b.get("portee") == "tous":
            return "bloquee_tous"
    for b in blocages:
        if b.get("type") == "ip" and ip and b.get("ip") == ip and user_id and b.get("user_id") == user_id:
            return "bloquee_compte"
    return "autorisee"


def compte_bloque(blocages: list[dict], user_id: Optional[str]) -> bool:
    return any(b.get("type") == "compte" and b.get("user_id") == user_id for b in blocages)


# ---------------------------------------------------------------------------
# Journal des connexions
# ---------------------------------------------------------------------------
async def journaliser_connexion(user_id: Optional[str], methode: str, etat: str, *,
                                ip: Optional[str] = None, user_agent: Optional[str] = None,
                                sid: Optional[str] = None, motif: Optional[str] = None,
                                identifiant: Optional[str] = None) -> None:
    """Ajoute une ligne au journal des connexions. Ne lève jamais d'exception :
    un échec d'écriture ne doit pas empêcher la connexion."""
    import sessions_comptes  # import différé : sessions_comptes importe ce module

    maintenant = _maintenant()
    try:
        await db.connexions_journal.insert_one({
            "id": str(uuid.uuid4()), "date": maintenant.isoformat(), "date_dt": maintenant,
            "user_id": user_id, "identifiant": identifiant, "ip": ip if ip is not None else current_ip(),
            "methode": methode, "etat": etat, "motif": motif, "sid": sid,
            "appareil": sessions_comptes.appareil(user_agent) if user_agent else None,
            "user_agent": (user_agent or "")[:300] or None,
        })
    except Exception as exc:  # noqa: BLE001
        print(f"[usage] journal des connexions impossible : {exc!r}")


# ---------------------------------------------------------------------------
# Contrôles : à la connexion et à chaque requête authentifiée
# ---------------------------------------------------------------------------
async def controler_connexion(user: Optional[dict], methode: str, user_agent: Optional[str] = None,
                              identifiant: Optional[str] = None) -> None:
    """À appeler AVANT d'ouvrir une session. Compte ou IP bloqué : la tentative
    est journalisée (« refusée ») puis refusée (403 « acces_suspendu »).
    `user` None = inscription (seuls les blocages d'IP « tous les comptes » jouent)."""
    if user and user.get("role") == "admin":
        return  # le super-administrateur n'est jamais bloqué
    ip = current_ip()
    motif = motif_blocage(await blocages_actifs(cache=False), (user or {}).get("id"), ip)
    if not motif:
        return
    await journaliser_connexion((user or {}).get("id"), methode, "refusee", ip=ip, user_agent=user_agent,
                                motif=motif, identifiant=identifiant)
    await log_activity((user or {}).get("id"), "Connexion refusée (accès suspendu)", ip,
                       details={"motif": motif, "methode": methode})
    raise exception_suspendu()


async def controler_requete(user: dict, sid: str) -> None:
    """À chaque requête authentifiée (auth.get_current_user) : si le compte ou
    l'IP de la requête est bloqué, la session est fermée et la requête refusée."""
    if user.get("role") == "admin":
        return
    ip = current_ip()
    motif = motif_blocage(await blocages_actifs(), user.get("id"), ip)
    if not motif:
        return
    import sessions_comptes

    if await sessions_comptes.fermer(sid, "blocage", par=None):
        # Première requête refusée de cette session : une seule ligne au journal
        await journaliser_connexion(user.get("id"), "session", "refusee", ip=ip, sid=sid, motif=motif)
    raise exception_suspendu()


# ---------------------------------------------------------------------------
# Présence (pastille verte / orange / rouge)
# ---------------------------------------------------------------------------
def couleur_presence(session: Optional[dict], maintenant_s: Optional[float] = None) -> dict:
    """Couleur de la pastille d'une session (document de `maf_sessions`)."""
    if not session or session.get("fermee"):
        return {"couleur": "rouge", "libelle": "Déconnecté", "derniere_activite": None}
    expire = session.get("expire_le")
    if isinstance(expire, datetime):
        if expire.tzinfo is None:
            expire = expire.replace(tzinfo=timezone.utc)
        if expire <= _maintenant():
            return {"couleur": "rouge", "libelle": "Déconnecté", "derniere_activite": None}
    derniere = session.get("derniere_activite")
    if derniere is None:
        return {"couleur": "rouge", "libelle": "Déconnecté", "derniere_activite": None}
    if maintenant_s is None:
        import sessions_comptes
        maintenant_s = sessions_comptes._maintenant()  # noqa: SLF001 — même horloge que les sessions
    ecart = maintenant_s - float(derniere)
    iso = datetime.fromtimestamp(float(derniere), timezone.utc).isoformat()
    if ecart <= SEUIL_ACTIF_S:
        return {"couleur": "vert", "libelle": "Connecté et actif", "derniere_activite": iso}
    if ecart <= SEUIL_ABSENT_S:
        return {"couleur": "orange", "libelle": "Connecté, inactif depuis plus de 5 min", "derniere_activite": iso}
    return {"couleur": "rouge", "libelle": "Inactif depuis plus de 10 min", "derniere_activite": iso}


async def presence_sessions(sids: list[str]) -> dict[str, dict]:
    """Pastille de chaque session demandée (sid -> {couleur, libelle, derniere_activite})."""
    sids = [s for s in dict.fromkeys(sids) if s][:500]
    docs = {d["_id"]: d for d in await db.sessions.find(
        {"_id": {"$in": sids}}, {"fermee": 1, "expire_le": 1, "derniere_activite": 1}).to_list(len(sids) or 1)}
    return {sid: couleur_presence(docs.get(sid)) for sid in sids}


# ---------------------------------------------------------------------------
# Création et levée des blocages
# ---------------------------------------------------------------------------
async def journaliser_action(action: str, par: dict, **details) -> None:
    """Journal des actions du super-administrateur (qui, quand, quoi)."""
    await db.blocages_journal.insert_one({
        "id": str(uuid.uuid4()), "date": _maintenant().isoformat(), "action": action,
        "par": par.get("email") or par.get("phone") or par.get("full_name"), "par_id": par.get("id"),
        "details": details})
    await log_activity(par.get("id"), f"Usage : {action}", current_ip(), details=details)


async def _fermer_sessions(filtre: dict) -> int:
    """Ferme les sessions ouvertes correspondant au filtre (jamais celles d'un administrateur principal)."""
    import sessions_comptes

    admins = set(await db.users.distinct("id", {"role": "admin"}))
    docs = await db.sessions.find({**filtre, "fermee": False}, {"_id": 1, "user_id": 1}).to_list(5000)
    n = 0
    for d in docs:
        if d.get("user_id") in admins:
            continue  # le super-administrateur n'est jamais déconnecté par un blocage
        await sessions_comptes.fermer(d["_id"], "blocage", par=None)
        n += 1
    return n


async def bloquer(adm: dict, *, type_: str, ip: Optional[str] = None, user_id: Optional[str] = None,
                  tous_comptes: bool = True, libelle: Optional[str] = None, motif: Optional[str] = None) -> dict:
    """Crée un blocage (voir la docstring du module) et ferme les sessions concernées."""
    ip = (ip or "").strip() or None
    libelle = (libelle or "").strip()[:120] or None
    motif = (motif or "").strip()[:300] or None
    compte = None
    if user_id:
        compte = await db.users.find_one({"id": user_id}, {"_id": 0, "id": 1, "role": 1, "full_name": 1,
                                                           "email": 1, "phone": 1})
        if not compte:
            raise HTTPException(404, "Compte introuvable")
    # --- Règle absolue : le super-administrateur ne peut pas se bloquer lui-même ---
    if compte and (compte["id"] == adm.get("id") or compte.get("role") == "admin"):
        if type_ == "compte" or not tous_comptes:
            raise HTTPException(400, "Vous ne pouvez pas bloquer le compte du super-administrateur "
                                     "(le vôtre) : cela vous empêcherait d'accéder au site.")
    if type_ == "ip" and ip and ip == current_ip():
        raise HTTPException(400, "Vous ne pouvez pas bloquer l'adresse IP que vous utilisez en ce moment : "
                                 "cela vous bloquerait vous-même.")

    if type_ == "compte":
        if not compte:
            raise HTTPException(400, "Compte à bloquer non précisé")
        if await db.blocages.find_one({"actif": True, "type": "compte", "user_id": compte["id"]}):
            raise HTTPException(409, "Ce compte est déjà bloqué")
        doc = {"type": "compte", "portee": "compte", "ip": None, "user_id": compte["id"]}
    elif type_ == "ip":
        if not ip:
            raise HTTPException(400, "Adresse IP à bloquer non précisée")
        if not tous_comptes and not compte:
            raise HTTPException(400, "Compte non précisé pour un blocage limité à ce compte")
        portee = "tous" if tous_comptes else "compte"
        cible = {"actif": True, "type": "ip", "ip": ip, "portee": portee}
        if portee == "compte":
            cible["user_id"] = compte["id"]
        if await db.blocages.find_one(cible):
            raise HTTPException(409, "Cette adresse IP est déjà bloquée")
        doc = {"type": "ip", "portee": portee, "ip": ip, "user_id": compte["id"] if portee == "compte" else None}
    else:
        raise HTTPException(400, "Type de blocage inconnu")

    doc.update({
        "id": str(uuid.uuid4()), "actif": True, "libelle": libelle, "motif": motif,
        "cree_le": _maintenant().isoformat(), "cree_par": adm.get("email") or adm.get("phone"),
        "cree_par_id": adm.get("id"),
        # Pour l'affichage de la liste : compte visé au moment du blocage (s'il y en a un)
        "compte_nom": (compte or {}).get("full_name"),
        "compte_identifiant": (compte or {}).get("email") or (compte or {}).get("phone"),
    })
    await db.blocages.insert_one(doc.copy())
    vider_cache()
    # Effet immédiat : les sessions en cours concernées sont fermées
    if doc["type"] == "compte":
        fermees = await _fermer_sessions({"user_id": doc["user_id"]})
    elif doc["portee"] == "tous":
        fermees = await _fermer_sessions({"ip": ip})
    else:
        fermees = await _fermer_sessions({"ip": ip, "user_id": doc["user_id"]})
    action = {"compte": "Compte bloqué", "tous": "Adresse IP bloquée pour tous les comptes",
              "compte_ip": "Adresse IP bloquée pour ce compte"}[
        "compte" if doc["type"] == "compte" else ("tous" if doc["portee"] == "tous" else "compte_ip")]
    await journaliser_action(action, adm, blocage=doc["id"], ip=doc.get("ip"), membre=doc.get("user_id"),
                             libelle=libelle, motif=motif, sessions_fermees=fermees)
    return {**doc, "sessions_fermees": fermees}


async def lever(adm: dict, blocage_id: str) -> dict:
    """Lève un blocage (« Autoriser ») : il reste dans l'historique, inactif."""
    doc = await db.blocages.find_one({"id": blocage_id, "actif": True}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Blocage introuvable ou déjà levé")
    await db.blocages.update_one({"id": blocage_id}, {"$set": {
        "actif": False, "leve_le": _maintenant().isoformat(), "leve_par": adm.get("email") or adm.get("phone")}})
    vider_cache()
    await journaliser_action("Blocage levé (accès autorisé)", adm, blocage=blocage_id, type=doc.get("type"),
                             portee=doc.get("portee"), ip=doc.get("ip"), membre=doc.get("user_id"))
    return {"ok": True}


async def autoriser(adm: dict, *, type_: str, ip: Optional[str] = None, user_id: Optional[str] = None) -> int:
    """Lève tous les blocages actifs qui touchent cette IP (pour ce compte ou
    pour tous) ou ce compte. Renvoie le nombre de blocages levés."""
    if type_ == "compte":
        filtre = {"actif": True, "type": "compte", "user_id": user_id}
    else:
        filtre = {"actif": True, "type": "ip", "ip": ip,
                  "$or": [{"portee": "tous"}, {"user_id": user_id}] if user_id else [{"portee": "tous"}]}
    ids = [d["id"] for d in await db.blocages.find(filtre, {"_id": 0, "id": 1}).to_list(100)]
    for bid in ids:
        await lever(adm, bid)
    return len(ids)


# ---------------------------------------------------------------------------
# Contact affiché sur la page « Accès momentanément suspendu »
# ---------------------------------------------------------------------------
async def lire_contact() -> dict:
    doc = await db.settings.find_one({"id": ID_CONTACT}, {"_id": 0}) or {}
    return {"email": doc.get("email") or "", "whatsapp": doc.get("whatsapp") or ""}


async def regler_contact(adm: dict, email: Optional[str], whatsapp: Optional[str]) -> dict:
    email = (email or "").strip()[:200]
    whatsapp = (whatsapp or "").strip()[:40]
    if email and ("@" not in email or " " in email):
        raise HTTPException(400, "Adresse e-mail de contact invalide")
    if whatsapp and not all(c.isdigit() or c in "+ " for c in whatsapp):
        raise HTTPException(400, "Numéro WhatsApp invalide (chiffres, espaces et « + » seulement)")
    await db.settings.update_one({"id": ID_CONTACT}, {"$set": {"id": ID_CONTACT, "email": email,
                                                               "whatsapp": whatsapp}}, upsert=True)
    await journaliser_action("Contact de la page de blocage modifié", adm, email=email, whatsapp=whatsapp)
    return await lire_contact()


def debut_periode(jour: Optional[str], fin: bool = False) -> Optional[str]:
    """« AAAA-MM-JJ » → borne ISO (UTC = heure de Ouagadougou). `fin` : lendemain 0 h."""
    if not jour:
        return None
    try:
        d = datetime.strptime(jour, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise HTTPException(400, "Date invalide (format attendu AAAA-MM-JJ)") from exc
    return (d + timedelta(days=1) if fin else d).isoformat()
