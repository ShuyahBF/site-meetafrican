"""Export / import complets de la base (changement de cluster MongoDB) :
aller-retour avec conservation des types, phrase secrète, fichier altéré,
rôles, modes d'import et restauration initiale sans session.

La « base brute » exportée / importée est remplacée par des bases mongomock
NEUVES (une par test) : la base partagée des autres tests n'est jamais touchée.
"""
import io
import time
import uuid
from datetime import datetime

import pytest
from bson import Binary, Decimal128, Int64, ObjectId
from mongomock_motor import AsyncMongoMockClient

import chiffrement_flux
import transfert_donnees as service
from auth import hash_password
from config import get_settings
from db import db

PHRASE = "une phrase secrète solide"
MDP = "motdepasse123"  # mot de passe des comptes créés par make_user
MDP_ADMIN_FICHIER = "admin-du-fichier-2026"
P = "maf_"


def _nouvelle_base():
    return AsyncMongoMockClient()[f"t_{uuid.uuid4().hex}"]


@pytest.fixture(autouse=True)
def _aucune_tache():
    service._taches.clear()
    yield
    service._taches.clear()


@pytest.fixture
def bases(monkeypatch):
    """Base source (exportée) et base cible (importée), interchangeables."""
    etat = {"source": _nouvelle_base(), "cible": _nouvelle_base(), "active": "source"}
    monkeypatch.setattr(service, "base_brute", lambda: etat[etat["active"]])
    return etat


@pytest.fixture
def admin(client, make_user):
    uid, headers, _ = make_user()
    client.portal.call(lambda: db.users.update_one({"id": uid}, {"$set": {"role": "admin"}}))
    return headers


DATE = datetime(2026, 1, 2, 3, 4, 5, 678000)
OID = ObjectId()


def _remplir_source(client, base):
    """Données de la « vraie » base : types MongoDB variés, index, comptes."""
    async def remplir():
        await base[P + "users"].insert_many([
            {"_id": OID, "id": "u-admin", "email": "chef@beauthentik.net", "role": "admin", "is_active": True,
             "password_hash": hash_password(MDP_ADMIN_FICHIER), "created_at_dt": DATE},
            {"id": "u-membre", "email": "awa@example.com", "role": "member", "is_active": True,
             "password_hash": hash_password("membre-2026"), "points": Int64(2 ** 40)},
        ])
        await base[P + "users"].create_index("email", unique=True, sparse=True)
        await base[P + "payments"].insert_one({
            "deposit_id": "dep-1", "montant": Decimal128("5000.50"), "brut": Binary(b"\x00\x01\xff"),
            "historique": [{"le": DATE, "etat": "ok"}], "flottant": 1.5, "rien": None})
        await base[P + "payments"].create_index("deposit_id", unique=True)
        # Collection d'un AUTRE projet (pas de préfixe maf_) : jamais exportée
        await base["autre_projet"].insert_one({"x": 1})
    client.portal.call(remplir)


def _attendre(client, tache_id, delai=30):
    fin = time.time() + delai
    while time.time() < fin:
        t = client.get(f"/api/plateforme/transfert/taches/{tache_id}").json()
        if t["statut"] != "EN_COURS":
            return t
        time.sleep(0.05)
    raise AssertionError("opération trop longue")


def _exporter(client, admin, bases):
    bases["active"] = "source"
    r = client.post("/api/plateforme/transfert/export", headers=admin,
                    json={"mot_de_passe": MDP, "phrase": PHRASE, "phrase_confirmation": PHRASE})
    assert r.status_code == 202, r.text
    tache = _attendre(client, r.json()["id"])
    assert tache["statut"] == "TERMINE", tache
    url = f"/api/plateforme/transfert/taches/{tache['id']}/fichier"
    assert client.get(url, params={"jeton": "mauvais"}).status_code == 403
    fichier = client.get(url, params={"jeton": r.json()["jeton_telechargement"]})
    assert fichier.status_code == 200
    assert fichier.headers["content-disposition"].endswith('.baexport"')
    # Téléchargement unique : le fichier est effacé du serveur
    assert client.get(url, params={"jeton": r.json()["jeton_telechargement"]}).status_code == 404
    return fichier.content, tache


def _importer(client, admin, contenu, mode="vide", phrase=PHRASE, confirmation="", mot_de_passe=MDP):
    return client.post("/api/plateforme/transfert/import", headers=admin,
                       files={"fichier": ("base.baexport", io.BytesIO(contenu), "application/octet-stream")},
                       data={"phrase": phrase, "mot_de_passe": mot_de_passe, "mode": mode,
                             "confirmation": confirmation})


def _documents(client, base, nom):
    return client.portal.call(lambda: base[P + nom].find({}).sort("_id", 1).to_list(None))


# ---------------------------------------------------------------------------
# Chiffrement
# ---------------------------------------------------------------------------
def test_chiffrement_par_blocs_et_signature(tmp_path):
    cle = chiffrement_flux.cle_signature_serveur("secret-a")
    contenu = bytes(range(256)) * 50  # 12 800 octets -> 13 blocs de 1 Ko
    chemin = tmp_path / "f.baexport"
    with open(chemin, "wb") as f:
        e = chiffrement_flux.EcrivainChiffre(f, PHRASE, cle, taille_bloc=1024)
        e.write(contenu)
        e.fermer_flux()
    lecteur = chiffrement_flux.LecteurChiffre(str(chemin), PHRASE, cle)
    assert lecteur.signature_valide and lecteur.read() == contenu
    lecteur.seek(5000)
    assert lecteur.read(10) == contenu[5000:5010]
    lecteur.close()
    # Autre secret serveur : lisible, mais signature non reconnue
    autre = chiffrement_flux.LecteurChiffre(str(chemin), PHRASE, chiffrement_flux.cle_signature_serveur("b"))
    assert not autre.signature_valide
    autre.close()
    with pytest.raises(chiffrement_flux.PhraseIncorrecte):
        chiffrement_flux.LecteurChiffre(str(chemin), "pas la bonne phrase", cle)
    brut = bytearray(chemin.read_bytes())
    brut[3000] ^= 0x01
    (tmp_path / "altere").write_bytes(bytes(brut))
    with pytest.raises(chiffrement_flux.ErreurChiffrement, match="altéré"):
        chiffrement_flux.LecteurChiffre(str(tmp_path / "altere"), PHRASE, cle)
    (tmp_path / "tronque").write_bytes(chemin.read_bytes()[:-40])
    with pytest.raises(chiffrement_flux.ErreurChiffrement):
        chiffrement_flux.LecteurChiffre(str(tmp_path / "tronque"), PHRASE, cle)


def test_phrase_secrete_controlee():
    with pytest.raises(chiffrement_flux.ErreurChiffrement, match="12"):
        chiffrement_flux.valider_phrase("court")
    with pytest.raises(chiffrement_flux.ErreurChiffrement, match="identiques"):
        chiffrement_flux.valider_phrase(PHRASE, PHRASE + "x")
    # Normalisation NFC : « é » composé ou décomposé donnent la même phrase
    assert chiffrement_flux.valider_phrase("été 2026 soleil") == "été 2026 soleil"


def test_index_texte_reconstruit_depuis_weights():
    definition = {"v": 2, "key": {"statut": 1, "_fts": "text", "_ftsx": 1}, "name": "recherche",
                  "weights": {"titre": 10, "description": 1}, "default_language": "french",
                  "textIndexVersion": 3, "ns": "x.y"}
    cle, options = service.definition_vers_index(definition)
    assert cle == [("statut", 1), ("titre", "text"), ("description", "text")]
    assert options == {"name": "recherche", "weights": {"titre": 10, "description": 1}, "default_language": "french"}


# ---------------------------------------------------------------------------
# Droits
# ---------------------------------------------------------------------------
def test_reserve_a_l_administrateur_principal(client, make_user, admin, bases):
    corps = {"mot_de_passe": MDP, "phrase": PHRASE, "phrase_confirmation": PHRASE}
    assert client.post("/api/plateforme/transfert/export", json=corps).status_code == 401
    _, membre, _ = make_user()
    assert client.post("/api/plateforme/transfert/export", json=corps, headers=membre).status_code == 403
    assert client.get("/api/plateforme/transfert", headers=membre).status_code == 403
    uid, moderateur, _ = make_user()
    client.portal.call(lambda: db.users.update_one({"id": uid}, {"$set": {"role": "moderator"}}))
    assert client.post("/api/plateforme/transfert/export", json=corps, headers=moderateur).status_code == 403
    assert _importer(client, moderateur, b"x").status_code == 403
    # Administrateur : mot de passe redemandé, phrase contrôlée
    r = client.post("/api/plateforme/transfert/export", headers=admin, json={**corps, "mot_de_passe": "faux"})
    assert r.status_code == 403
    r = client.post("/api/plateforme/transfert/export", headers=admin,
                    json={**corps, "phrase": "court", "phrase_confirmation": "court"})
    assert r.status_code == 400
    r = client.post("/api/plateforme/transfert/export", headers=admin, json={**corps, "phrase_confirmation": "autre chose !!"})
    assert r.status_code == 400
    etat = client.get("/api/plateforme/transfert", headers=admin).json()
    assert etat["extension"] == ".baexport"
    assert any(h["statut"] == "MOT_DE_PASSE_REFUSE" for h in etat["historique"])


# ---------------------------------------------------------------------------
# Aller-retour export -> import
# ---------------------------------------------------------------------------
def test_aller_retour_conserve_les_types(client, admin, bases):
    _remplir_source(client, bases["source"])
    contenu, tache = _exporter(client, admin, bases)
    assert {c["nom"] for c in tache["rapport"]["collections"]} == {"users", "payments"}  # pas « autre_projet »

    # Base cible « neuve » : ce que crée le démarrage d'un serveur (compte admin
    # d'amorçage, formules et cadeaux par défaut, journal d'activité, compteur)
    async def demarrage():
        cible = bases["cible"]
        await cible[P + "users"].insert_one({"id": "u-bootstrap", "email": "boot@x.net", "role": "admin"})
        await cible[P + "subscription_plans"].insert_one({"code": "1_mois"})
        await cible[P + "gifts"].insert_one({"code": "rose"})
        await cible[P + "settings"].insert_one({"id": "site_stats", "visits": 3})
        await cible[P + "activity_log"].insert_one({"id": "a1", "action": "Tentative de connexion"})
    client.portal.call(demarrage)

    bases["active"] = "cible"
    r = _importer(client, admin, contenu)
    assert r.status_code == 202, r.text
    t = _attendre(client, r.json()["id"])
    assert t["statut"] == "TERMINE", t
    assert t["rapport"]["conforme"] and t["rapport"]["signature_reconnue"]
    assert {c["nom"]: c["dans_la_base"] for c in t["rapport"]["collections"]} == {"users": 2, "payments": 1}

    source_users = _documents(client, bases["source"], "users")
    cible_users = _documents(client, bases["cible"], "users")
    assert cible_users == source_users  # le compte d'amorçage est remplacé
    assert cible_users[0]["_id"] == OID and isinstance(cible_users[0]["_id"], ObjectId)
    assert cible_users[0]["created_at_dt"] == DATE
    assert cible_users[1]["points"] == 2 ** 40
    paiement = _documents(client, bases["cible"], "payments")[0]
    assert paiement["montant"] == Decimal128("5000.50") and bytes(paiement["brut"]) == b"\x00\x01\xff"
    assert paiement["historique"][0]["le"] == DATE and paiement["flottant"] == 1.5 and paiement["rien"] is None
    # Index recréés
    index = client.portal.call(lambda: bases["cible"][P + "payments"].index_information())
    assert any(v["key"] == [("deposit_id", 1)] and v.get("unique") for v in index.values())
    # Journal d'activité du nouveau serveur conservé (collection fusionnée)
    assert client.portal.call(lambda: bases["cible"][P + "activity_log"].count_documents({})) == 1
    journal = client.get("/api/plateforme/transfert", headers=admin).json()["historique"]
    assert {(h["action"], h["statut"]) for h in journal} >= {("export", "TERMINE"), ("import", "TERMINE"),
                                                             ("telechargement_export", "TERMINE")}


def test_mauvaise_phrase_et_fichier_altere(client, admin, bases):
    _remplir_source(client, bases["source"])
    contenu, _ = _exporter(client, admin, bases)
    bases["active"] = "cible"
    r = _importer(client, admin, contenu, phrase="phrase totalement fausse")
    assert r.status_code == 400 and "Phrase secrète incorrecte" in r.json()["detail"]
    assert _importer(client, admin, contenu, mot_de_passe="faux").status_code == 403
    assert _importer(client, admin, b"pas un export du tout").status_code == 400

    altere = bytearray(contenu)
    altere[len(altere) // 2] ^= 0x01
    t = _attendre(client, _importer(client, admin, bytes(altere)).json()["id"])
    assert t["statut"] == "ECHEC" and "altéré" in t["erreur"]
    t = _attendre(client, _importer(client, admin, contenu[:-100]).json()["id"])
    assert t["statut"] == "ECHEC"
    # Rien n'a été écrit dans la base cible
    assert client.portal.call(lambda: bases["cible"].list_collection_names()) == []


def test_modes_d_import(client, admin, bases):
    _remplir_source(client, bases["source"])
    contenu, _ = _exporter(client, admin, bases)
    # La base cible contient déjà un membre : « Base vide uniquement » refuse
    client.portal.call(lambda: bases["cible"][P + "users"].insert_one({"id": "intrus", "role": "member"}))
    client.portal.call(lambda: bases["cible"][P + "videos"].insert_one({"id": "v-garde"}))
    bases["active"] = "cible"
    t = _attendre(client, _importer(client, admin, contenu).json()["id"])
    assert t["statut"] == "ECHEC" and "contient déjà des données" in t["erreur"] and "users" in t["erreur"]
    assert client.portal.call(lambda: bases["cible"][P + "users"].count_documents({"id": "intrus"})) == 1

    # « Remplacer » exige de taper REMPLACER
    assert _importer(client, admin, contenu, mode="remplacer").status_code == 400
    assert _importer(client, admin, contenu, mode="remplacer", confirmation="remplacer").status_code == 400
    assert _importer(client, admin, contenu, mode="inconnu").status_code == 400
    t = _attendre(client, _importer(client, admin, contenu, mode="remplacer", confirmation="REMPLACER").json()["id"])
    assert t["statut"] == "TERMINE" and t["rapport"]["conforme"], t
    ids = {u["id"] for u in _documents(client, bases["cible"], "users")}
    assert ids == {"u-admin", "u-membre"}
    # Collection absente du fichier : laissée telle quelle
    assert client.portal.call(lambda: bases["cible"][P + "videos"].count_documents({})) == 1


def test_un_seul_transfert_a_la_fois(client, admin, bases):
    service._taches["occupe"] = {"id": "occupe", "type": "export", "statut": "EN_COURS"}
    r = client.post("/api/plateforme/transfert/export", headers=admin,
                    json={"mot_de_passe": MDP, "phrase": PHRASE, "phrase_confirmation": PHRASE})
    assert r.status_code == 409


# ---------------------------------------------------------------------------
# Restauration initiale (base sans aucun compte, sans session)
# ---------------------------------------------------------------------------
def _restaurer(client, contenu, identifiant="chef@beauthentik.net", mot_de_passe=MDP_ADMIN_FICHIER, phrase=PHRASE):
    return client.post("/api/plateforme/transfert/restauration-initiale",
                       files={"fichier": ("base.baexport", io.BytesIO(contenu), "application/octet-stream")},
                       data={"phrase": phrase, "identifiant": identifiant, "mot_de_passe": mot_de_passe})


def test_restauration_initiale(client, admin, bases):
    _remplir_source(client, bases["source"])
    contenu, _ = _exporter(client, admin, bases)
    bases["active"] = "cible"
    assert client.get("/api/plateforme/transfert/restauration-initiale").json()["disponible"] is True

    # Identifiants : membre du fichier, mauvais mot de passe, compte inconnu -> refus avant écriture
    for ident, mdp in (("awa@example.com", "membre-2026"), ("chef@beauthentik.net", "faux-mot-de-passe"),
                       ("inconnu@x.net", MDP_ADMIN_FICHIER)):
        t = _attendre(client, _restaurer(client, contenu, ident, mdp).json()["id"])
        assert t["statut"] == "ECHEC" and "Identifiants refusés" in t["erreur"], t
    assert client.portal.call(lambda: bases["cible"].list_collection_names()) == []
    assert _restaurer(client, contenu, phrase="phrase totalement fausse").status_code == 400

    # Fichier valide mais signé par un serveur au secret JWT différent -> refus
    chemin = service.DOSSIER / "etranger.tmp"
    chemin.write_bytes(contenu)
    lecteur = chiffrement_flux.LecteurChiffre(str(chemin), PHRASE, service._cle_signature())
    clair = lecteur.read()
    lecteur.close()
    chemin.unlink()
    sortie = io.BytesIO()
    ecrivain = chiffrement_flux.EcrivainChiffre(sortie, PHRASE, chiffrement_flux.cle_signature_serveur("autre-secret"))
    ecrivain.write(clair)
    ecrivain.fermer_flux()
    t = _attendre(client, _restaurer(client, sortie.getvalue()).json()["id"])
    assert t["statut"] == "ECHEC" and "JWT_SECRET" in t["erreur"]

    # Bons identifiants d'un administrateur actif du fichier -> restauration complète
    t = _attendre(client, _restaurer(client, contenu).json()["id"])
    assert t["statut"] == "TERMINE" and t["rapport"]["conforme"], t
    assert len(_documents(client, bases["cible"], "users")) == 2
    # La base contient maintenant des comptes : restauration sans session fermée
    etat = client.get("/api/plateforme/transfert/restauration-initiale").json()
    assert etat["disponible"] is False
    r = _restaurer(client, contenu)
    assert r.status_code == 403


def test_restauration_initiale_refusee_avec_le_secret_par_defaut(client, bases, monkeypatch):
    bases["active"] = "cible"
    monkeypatch.setattr(get_settings(), "jwt_secret", service.SECRET_JWT_PAR_DEFAUT)
    etat = client.get("/api/plateforme/transfert/restauration-initiale").json()
    assert etat["disponible"] is False and "JWT_SECRET" in etat["motif"]
    assert _restaurer(client, b"x" * 100).status_code == 403
