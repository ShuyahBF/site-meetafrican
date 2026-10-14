"""Lot 75 — contacts de beAuthentik lus (signés) par SAWALI : signature, confidentialité (prénom + numéro vérifié seulement)."""
import time

import export_contacts_sawali as E
from db import db

CHEMIN = "/api/sawali/contacts"
CLE = "cle-contacts-test"


def _entetes(requete, cle=CLE):
    ts = str(int(time.time()))
    return {"X-Timestamp": ts, "X-Signature": E.signer(cle, ts, CHEMIN, requete)}


def test_signature_et_prenom():
    s = E.signer("k", "1700000000", CHEMIN, "limite=5&page=1")
    assert E.signature_valide("k", "1700000000", s, CHEMIN, "limite=5&page=1", maintenant=1700000100)
    assert not E.signature_valide("k", "1700000000", s, CHEMIN, "limite=5&page=1", maintenant=1700000500)
    assert E.prenom("  Awa   Ouedraogo ") == "Awa" and E.prenom(None) == ""


def test_refus_sans_cle_ou_signature(client, monkeypatch):
    monkeypatch.delenv("SAWALI_CONTACTS_HMAC", raising=False)
    assert client.get(CHEMIN).status_code == 503
    monkeypatch.setenv("SAWALI_CONTACTS_HMAC", CLE)
    assert client.get(CHEMIN).status_code == 401
    assert client.get(f"{CHEMIN}?limite=5&page=1", headers=_entetes("limite=5&page=1", cle="autre")).status_code == 401


def test_membres_au_telephone_verifie_seulement_et_donnees_minimales(client, monkeypatch):
    monkeypatch.setenv("SAWALI_CONTACTS_HMAC", CLE)
    client.portal.call(db.users.insert_many, [
        {"id": "m-sc1", "full_name": "Awa Ouedraogo", "email": "awa@x.bf", "phone": "+22670112233", "phone_verified": True, "is_active": True,
         "gender": "femme", "birthdate": "1995-05-05", "role": "user"},
        {"id": "m-sc2", "full_name": "Non vérifié", "phone": "+22670112244", "phone_verified": False, "is_active": True, "role": "user"},
        {"id": "m-sc3", "full_name": "Suspendu", "phone": "+22670112255", "phone_verified": True, "is_active": False, "role": "user"},
        {"id": "m-sc4", "full_name": "Modérateur", "phone": "+22670112266", "phone_verified": True, "is_active": True, "role": "moderator"},
        {"id": "m-sc5", "full_name": "Sans numéro", "phone_verified": True, "is_active": True, "role": "user"}])
    q = "limite=500&page=1"
    r = client.get(f"{CHEMIN}?{q}", headers=_entetes(q))
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["plateforme"] == "beAuthentik"
    awa = next(c for c in d["contacts"] if c["id"] == "m-sc1")
    assert awa == {"id": "m-sc1", "nom": "Awa", "telephone": "22670112233", "role": "membre", "societe": "beAuthentik"}   # prénom seul, rien d'autre
    ids = {c["id"] for c in d["contacts"]}
    assert not ({"m-sc2", "m-sc3", "m-sc4", "m-sc5"} & ids)
    texte = r.text
    assert "awa@x.bf" not in texte and "1995" not in texte and "femme" not in texte and "Ouedraogo" not in texte
