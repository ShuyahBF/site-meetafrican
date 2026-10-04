"""Transmission WhatsApp (transmission_wa.py) : WABA propre en priorité, sinon
Transmission WA Universelle Liluvine. Les réponses HTTP sont SIMULÉES
(httpx.MockTransport) : aucun appel réseau réel."""
import asyncio
import hashlib
import hmac
import json

import httpx
import pytest

import otp_senders
import transmission_wa as twu
from config import get_settings

URL = "https://sawali.exemple/api/webhook/liluvine-send"
CLE = "cle-de-test-non-secrete"


@pytest.fixture
def simulateur(monkeypatch):
    """Installe un transport simulé ; `reponses` = liste de codes HTTP ou d'exceptions,
    consommée dans l'ordre. Renvoie la liste des requêtes reçues."""
    requetes = []

    def installer(*reponses):
        file = list(reponses)

        def traiter(requete: httpx.Request):
            requetes.append(requete)
            suivante = file.pop(0) if file else 200
            if isinstance(suivante, Exception):
                raise suivante
            if suivante == 200 and "graph.facebook.com" in str(requete.url):
                return httpx.Response(200, json={"messages": [{"id": "wamid.TEST"}]})
            if suivante == 200:
                return httpx.Response(200, json={"ok": True, "message_id": "wamid.LILU", "doublon": False})
            return httpx.Response(suivante, json={"detail": "erreur simulée"})

        monkeypatch.setattr(twu, "_transport", httpx.MockTransport(traiter))
        return requetes

    return installer


@pytest.fixture
def sans_waba(monkeypatch):
    monkeypatch.setattr(otp_senders, "whatsapp_configured", lambda: False)


@pytest.fixture
def liluvine(monkeypatch):
    monkeypatch.setenv("LILUVINE_WA_URL", URL)
    monkeypatch.setenv("LILUVINE_WA_HMAC", CLE)
    monkeypatch.setenv("LILUVINE_WA_EMETTEUR", "beauthentik")


def _envoyer(numero="+22670000000", message="Bonjour", **kw):
    return asyncio.run(twu.envoyer_whatsapp(numero, message, **kw))


def test_repli_liluvine_sans_waba_et_signature_hmac(simulateur, sans_waba, liluvine):
    requetes = simulateur(200)
    res = _envoyer(message="Alerte « Me suivre » é")
    assert res == {"ok": True, "canal": "liluvine", "message_id": "wamid.LILU", "erreur": None}
    assert len(requetes) == 1
    r = requetes[0]
    assert str(r.url) == URL
    corps_brut = r.content.decode("utf-8")
    corps = json.loads(corps_brut)
    # Corps du protocole : id uuid4, numéro international, message, source par défaut
    assert set(corps) == {"id", "to", "message", "source"}
    assert corps["to"] == "+22670000000"
    assert corps["message"] == "Alerte « Me suivre » é"
    assert corps["source"] == "beAuthentik"
    assert len(corps["id"]) == 36
    # Signature calculée sur le corps EXACT envoyé
    attendu = hmac.new(CLE.encode(), f"{r.headers['X-Timestamp']}.{corps_brut}".encode(), hashlib.sha256).hexdigest()
    assert r.headers["X-Signature"] == attendu
    assert r.headers["X-Emetteur"] == "beauthentik"
    assert r.headers["Content-Type"] == "application/json"
    # La clé n'apparaît jamais dans la requête
    assert CLE not in corps_brut and CLE not in str(dict(r.headers))


def test_source_personnalisee(simulateur, sans_waba, liluvine):
    requetes = simulateur(200)
    _envoyer(source="beAuthentik — Me suivre")
    assert json.loads(requetes[0].content)["source"] == "beAuthentik — Me suivre"


def test_priorite_waba_si_configure(simulateur, liluvine, monkeypatch):
    monkeypatch.setattr(otp_senders, "whatsapp_configured", lambda: True)
    s = get_settings()
    monkeypatch.setattr(s, "whatsapp_access_token", "jeton-test")
    monkeypatch.setattr(s, "whatsapp_phone_number_id", "12345")
    requetes = simulateur(200)
    res = _envoyer()
    assert res == {"ok": True, "canal": "waba", "message_id": "wamid.TEST", "erreur": None}
    assert len(requetes) == 1 and "graph.facebook.com/v21.0/12345/messages" in str(requetes[0].url)
    assert json.loads(requetes[0].content)["to"] == "22670000000"


def test_nouvel_essai_meme_id_sur_5xx(simulateur, sans_waba, liluvine):
    requetes = simulateur(500, 200)
    res = _envoyer()
    assert res["ok"] is True and res["canal"] == "liluvine"
    assert len(requetes) == 2
    ids = [json.loads(r.content)["id"] for r in requetes]
    assert ids[0] == ids[1]
    # Corps identique, signature recalculée pour chaque essai
    assert requetes[0].content == requetes[1].content
    for r in requetes:
        attendu = hmac.new(CLE.encode(), r.headers["X-Timestamp"].encode() + b"." + r.content, hashlib.sha256).hexdigest()
        assert r.headers["X-Signature"] == attendu


def test_nouvel_essai_meme_id_sur_erreur_reseau(simulateur, sans_waba, liluvine):
    requetes = simulateur(httpx.ConnectError("coupure"), 200)
    res = _envoyer()
    assert res["ok"] is True
    assert len(requetes) == 2
    assert json.loads(requetes[0].content)["id"] == json.loads(requetes[1].content)["id"]


def test_un_seul_nouvel_essai(simulateur, sans_waba, liluvine):
    requetes = simulateur(503, 503, 200)
    res = _envoyer()
    assert res["ok"] is False and res["canal"] == "liluvine" and res["erreur"]
    assert len(requetes) == 2


@pytest.mark.parametrize("code", [401, 422, 429])
def test_pas_de_nouvel_essai_sur_4xx(simulateur, sans_waba, liluvine, code):
    requetes = simulateur(code, 200)
    res = _envoyer()
    assert res["ok"] is False and res["canal"] == "liluvine"
    assert len(requetes) == 1


def test_desactivation_propre_si_variables_absentes(simulateur, sans_waba, monkeypatch):
    monkeypatch.delenv("LILUVINE_WA_URL", raising=False)
    monkeypatch.setenv("LILUVINE_WA_HMAC", CLE)
    requetes = simulateur(200)
    res = _envoyer()
    assert res["ok"] is False and res["canal"] is None and "non configuré" in res["erreur"]
    assert requetes == []
    assert twu.etat() == {"waba_configure": False, "liluvine_configure": False, "emetteur": "beauthentik"}


def test_jamais_d_exception(sans_waba, liluvine, monkeypatch):
    def panne(*a, **k):
        raise RuntimeError("panne inattendue")
    monkeypatch.setattr(twu, "_envoyer_liluvine", panne)
    res = _envoyer()
    assert res["ok"] is False and res["erreur"]


def test_envoi_messages_passe_par_la_transmission(simulateur, sans_waba, liluvine, monkeypatch):
    """Les alertes (« Me suivre », cycle de vie, sauvegardes) partent par la Transmission
    universelle quand WABA n'est pas configuré, sans passer au SMS."""
    import envoi_messages
    requetes = simulateur(200)
    res = asyncio.run(envoi_messages.envoyer({"whatsapp": "70000000"}, "Signal perdu"))
    assert res == {"ok": True, "canal": "whatsapp", "erreur": None}
    assert json.loads(requetes[0].content)["to"] == "+22670000000"


def test_routes_administrateur(client, make_user, simulateur, sans_waba, liluvine):
    from db import db
    _, membre = make_user()[:2]
    # Membre ordinaire : refusé
    assert client.get("/api/admin/transmission-wa/etat", headers=membre).status_code == 403
    assert client.post("/api/admin/transmission-wa/test", json={"numero": "+22670000000"},
                       headers=membre).status_code == 403
    # Administrateur : état (sans aucun secret) et essai
    uid, admin = make_user()[:2]
    client.portal.call(lambda: db.users.update_one({"id": uid}, {"$set": {"role": "admin"}}))
    r = client.get("/api/admin/transmission-wa/etat", headers=admin)
    assert r.status_code == 200
    assert r.json() == {"waba_configure": False, "liluvine_configure": True, "emetteur": "beauthentik"}
    assert CLE not in r.text
    requetes = simulateur(200)
    r = client.post("/api/admin/transmission-wa/test", json={"numero": "+22670000000"}, headers=admin)
    assert r.status_code == 200 and r.json()["ok"] is True and r.json()["canal"] == "liluvine"
    assert json.loads(requetes[0].content)["message"] == "Test de transmission WhatsApp depuis beAuthentik"
