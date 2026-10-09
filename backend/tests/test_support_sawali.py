"""Assistance SAWALI (SAWALI lot 90) — relais signé (HMAC) vers le support SAWALI, identité réduite du membre,
erreurs lisibles. Les réponses HTTP sont SIMULÉES (httpx.MockTransport) : aucun appel réseau réel."""
import asyncio
import hashlib
import hmac
import json

import httpx
import pytest
from fastapi import HTTPException

import support_sawali as ss

CLE = "cle-de-test-non-secrete"


def _executer(coro):
    """Exécute une coroutine dans une boucle neuve (tests synchrones)."""
    boucle = asyncio.new_event_loop()
    try:
        return boucle.run_until_complete(coro)
    finally:
        boucle.close()


def test_relais_signe(monkeypatch):
    """Le corps part signé avec la clé d'émetteur, vers l'adresse déduite de LILUVINE_WA_URL."""
    monkeypatch.setenv("LILUVINE_WA_HMAC", CLE)
    monkeypatch.delenv("LILUVINE_WA_EMETTEUR", raising=False)     # émetteur par défaut : « beauthentik »
    monkeypatch.setenv("LILUVINE_WA_URL", "https://api.exemple.test/api/webhook/liluvine-send")
    monkeypatch.delenv("SAWALI_API_URL", raising=False)
    vus = {}

    def repondre(requete: httpx.Request):
        # On mémorise ce que SAWALI aurait reçu
        vus["url"] = str(requete.url)
        vus["entetes"] = requete.headers
        vus["corps"] = requete.content.decode()
        return httpx.Response(200, json={"ok": True, "requete": {"numero": "SUP-1", "statut": "attente"}})

    monkeypatch.setattr(ss, "_transport", httpx.MockTransport(repondre))
    r = _executer(ss.appeler_sawali("/support-plateforme/messages",
                                    {"utilisateur": {"id": "u1"}, "texte": "Bonjour é"}))
    assert r["ok"] is True
    assert vus["url"] == "https://api.exemple.test/api/support-plateforme/messages"
    h = vus["entetes"]
    attendu = hmac.new(CLE.encode(), f"{h['X-Timestamp']}.{vus['corps']}".encode(), hashlib.sha256).hexdigest()
    assert h["X-Emetteur"] == "beauthentik"
    assert h["X-Signature"] == attendu
    assert json.loads(vus["corps"])["texte"] == "Bonjour é"


def test_adresse_directe_prioritaire(monkeypatch):
    """SAWALI_API_URL l'emporte sur LILUVINE_WA_URL ; sans aucune des deux : adresse par défaut."""
    monkeypatch.setenv("SAWALI_API_URL", "https://sawali.direct/")
    monkeypatch.setenv("LILUVINE_WA_URL", "https://autre.test/api/x")
    assert ss.url_sawali() == "https://sawali.direct"
    monkeypatch.delenv("SAWALI_API_URL")
    monkeypatch.delenv("LILUVINE_WA_URL")
    assert ss.url_sawali() == ss.SAWALI_PAR_DEFAUT


def test_identite_reduite():
    """Seuls id, nom, rôle, contexte, e-mail et téléphone partent vers SAWALI."""
    membre = {"id": "m1", "full_name": "Awa", "role": "user", "email": "a@b.c", "phone": "+22670000000",
              "birthdate": "1990-01-01", "password_hash": "x", "city": "Ouaga", "bio": "…"}
    ident = ss.identite(membre)
    assert ident == {"id": "m1", "nom": "Awa", "role": "user", "contexte": "membre beAuthentik",
                     "email": "a@b.c", "telephone": "+22670000000"}


def test_erreurs_lisibles(monkeypatch):
    """Sans clé : 503 ; support non activé chez SAWALI (403) : message clair ; jamais la clé dans l'erreur."""
    monkeypatch.delenv("LILUVINE_WA_HMAC", raising=False)
    with pytest.raises(HTTPException) as e:
        _executer(ss.appeler_sawali("/x", {}))
    assert e.value.status_code == 503
    monkeypatch.setenv("LILUVINE_WA_HMAC", CLE)
    monkeypatch.setattr(ss, "_transport", httpx.MockTransport(lambda r: httpx.Response(403, json={})))
    with pytest.raises(HTTPException) as e:
        _executer(ss.appeler_sawali("/x", {}))
    assert "pas encore activée" in e.value.detail and CLE not in e.value.detail


def test_routes_reservees_aux_membres(client):
    """Sans connexion, les routes de l'assistance SAWALI répondent 401."""
    assert client.get("/api/support-sawali/etat").status_code == 401
    assert client.post("/api/support-sawali/messages", json={"texte": "x"}).status_code == 401
