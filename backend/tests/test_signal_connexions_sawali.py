"""Lot 71 — connexions et visites signalées à SAWALI (alerte WhatsApp du propriétaire).

Les réponses de SAWALI sont SIMULÉES (httpx.MockTransport) : aucun appel réseau réel.
On vérifie : signature HMAC correcte à la connexion, limitation des visites, aucun envoi si SAWALI n'est pas
configuré, aucune exception si SAWALI est injoignable."""
import asyncio
import hashlib
import hmac
import json
import time

import httpx
import pytest

import signal_connexions_sawali as sc

CLE = "cle-de-test-non-secrete"
NAVIGATEUR = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0 Safari/537.36"


def _executer(coro):
    """Exécute une coroutine dans une boucle neuve (tests synchrones)."""
    boucle = asyncio.new_event_loop()
    try:
        return boucle.run_until_complete(coro)
    finally:
        boucle.close()


def _attendre(condition, delai=3.0):
    """Attend (au plus `delai` s) qu'une tâche d'arrière-plan du serveur de test ait fini son envoi."""
    fin = time.time() + delai
    while time.time() < fin:
        if condition():
            return True
        time.sleep(0.02)
    return condition()


@pytest.fixture
def sawali(monkeypatch):
    """SAWALI configuré (clé, adresse) et simulé : chaque requête reçue est mémorisée dans la liste renvoyée."""
    monkeypatch.setenv("SIGNAL_CONNEXIONS_SAWALI", "1")
    monkeypatch.setenv("LILUVINE_WA_HMAC", CLE)
    monkeypatch.delenv("LILUVINE_WA_EMETTEUR", raising=False)   # émetteur par défaut : « beauthentik »
    monkeypatch.setenv("SAWALI_API_URL", "https://sawali.exemple.test")
    recues = []

    def repondre(requete: httpx.Request):
        recues.append({"url": str(requete.url), "entetes": dict(requete.headers),
                       "corps": requete.content.decode("utf-8")})
        return httpx.Response(200, json={"ok": True, "alerte": True, "raison": None})

    monkeypatch.setattr(sc, "_transport", httpx.MockTransport(repondre))
    sc._visites.clear()
    yield recues
    sc._visites.clear()


def _signature_valide(requete) -> bool:
    h = requete["entetes"]
    attendu = hmac.new(CLE.encode(), f"{h['x-timestamp']}.{requete['corps']}".encode(), hashlib.sha256).hexdigest()
    return h["x-signature"] == attendu


def test_connexion_signal_signe(client, sawali):
    """Une connexion réussie (inscription puis mot de passe) envoie un signal « connexion » signé."""
    entetes = {"user-agent": NAVIGATEUR, "x-forwarded-for": "41.202.10.20, 10.0.0.1"}
    r = client.post("/api/auth/register", headers=entetes, json={
        "full_name": "Awa Signal", "email": "awa.signal@example.com", "phone": "70112233",
        "password": "motdepasse123", "gender": "femme", "birthdate": "1995-05-05"})
    assert r.status_code == 201, r.text
    assert _attendre(lambda: len(sawali) >= 1)
    r = client.post("/api/auth/login", headers=entetes,
                    json={"identifier": "awa.signal@example.com", "password": "motdepasse123"})
    assert r.status_code == 200, r.text
    assert _attendre(lambda: len(sawali) >= 2)

    for requete in sawali:
        assert requete["url"] == "https://sawali.exemple.test/api/webhook/plateforme-connexion"
        assert requete["entetes"]["x-emetteur"] == "beauthentik"
        assert _signature_valide(requete)
        corps = json.loads(requete["corps"])
        assert corps["type"] == "connexion"
        assert corps["ip"] == "41.202.10.20"                 # premier élément de X-Forwarded-For
        assert corps["utilisateur"] == "Awa Signal"
        assert corps["telephone"] == "22670112233"            # chiffres + indicatif
        assert corps["role"] == "membre"
        assert corps["agent"] == NAVIGATEUR
        assert corps["url_site"].startswith("http")
        # Jamais de secret ni de mot de passe dans le corps
        assert "motdepasse123" not in requete["corps"] and CLE not in requete["corps"]
        assert "password" not in requete["corps"]


def test_mauvais_mot_de_passe_aucun_signal(client, sawali):
    """Une connexion refusée n'est pas signalée."""
    r = client.post("/api/auth/login", headers={"user-agent": NAVIGATEUR},
                    json={"identifier": "inconnu@example.com", "password": "faux-mot"})
    assert r.status_code == 401
    time.sleep(0.2)
    assert sawali == []


def test_visite_limitee(client, sawali):
    """Visite : un signal, puis rien pendant 30 min pour le même visiteur ou la même IP ; robots ignorés."""
    ip1 = {"user-agent": NAVIGATEUR, "x-forwarded-for": "102.1.1.1"}
    r = client.post("/api/presence/visite", headers=ip1, json={"visiteur": "abc123", "page": "/"})
    assert r.json() == {"ok": True, "signale": True}
    assert _attendre(lambda: len(sawali) == 1)
    corps = json.loads(sawali[0]["corps"])
    assert corps["type"] == "visite" and corps["visiteur"] == "abc123" and corps["page"] == "/"
    assert corps["utilisateur"] is None and corps["ip"] == "102.1.1.1"
    assert _signature_valide(sawali[0])

    # Même visiteur depuis une autre IP, ou autre visiteur depuis la même IP : ignorés (30 min)
    assert client.post("/api/presence/visite", headers={**ip1, "x-forwarded-for": "102.9.9.9"},
                       json={"visiteur": "abc123"}).json()["signale"] is False
    assert client.post("/api/presence/visite", headers=ip1, json={"visiteur": "autre"}).json()["signale"] is False
    # Robot évident : ignoré
    assert client.post("/api/presence/visite", headers={"user-agent": "Googlebot/2.1", "x-forwarded-for": "8.8.8.8"},
                       json={"visiteur": "robot"}).json()["signale"] is False
    # Requête d'un membre connecté (jeton) : ignorée
    assert client.post("/api/presence/visite", headers={"user-agent": NAVIGATEUR, "x-forwarded-for": "9.9.9.9",
                                                        "authorization": "Bearer x"},
                       json={"visiteur": "membre"}).json()["signale"] is False
    time.sleep(0.2)
    assert len(sawali) == 1


def test_limite_expire_apres_30_minutes(sawali):
    """Au-delà de 30 minutes, la même visite peut de nouveau être signalée."""
    t0 = 1_000_000.0
    assert sc.visite_a_signaler("v1", "1.2.3.4", t0) is True
    assert sc.visite_a_signaler("v1", "1.2.3.4", t0 + 60) is False
    assert sc.visite_a_signaler("v1", "1.2.3.4", t0 + sc.INTERVALLE_VISITE + 1) is True


def test_rien_si_non_configure(client, sawali, monkeypatch):
    """Sans clé SAWALI : aucun envoi (connexion comme visite), et la connexion fonctionne normalement."""
    monkeypatch.delenv("LILUVINE_WA_HMAC", raising=False)
    assert sc.actif() is False
    assert sc.signaler_connexion("u1", ip="1.1.1.1", user_agent=NAVIGATEUR) is False
    r = client.post("/api/presence/visite", headers={"user-agent": NAVIGATEUR, "x-forwarded-for": "5.5.5.5"},
                    json={"visiteur": "x1"})
    assert r.json()["signale"] is False
    assert _executer(sc.envoyer(sc.corps_signal("visite", ip="1.1.1.1", agent=NAVIGATEUR))) is None
    time.sleep(0.2)
    assert sawali == []


def test_desactivable(sawali, monkeypatch):
    """SIGNAL_CONNEXIONS_SAWALI=0 coupe le signal même si la clé est saisie."""
    monkeypatch.setenv("SIGNAL_CONNEXIONS_SAWALI", "0")
    assert sc.actif() is False


def test_aucune_exception_si_injoignable(sawali, monkeypatch):
    """SAWALI injoignable, en erreur ou réponse illisible : None, jamais d'exception."""
    def panne(requete):
        raise httpx.ConnectError("injoignable", request=requete)

    corps = sc.corps_signal("connexion", ip="1.1.1.1", agent=NAVIGATEUR, utilisateur="Test")
    monkeypatch.setattr(sc, "_transport", httpx.MockTransport(panne))
    assert _executer(sc.envoyer(corps)) is None
    monkeypatch.setattr(sc, "_transport", httpx.MockTransport(lambda r: httpx.Response(500, text="erreur")))
    assert _executer(sc.envoyer(corps)) is None
    monkeypatch.setattr(sc, "_transport", httpx.MockTransport(lambda r: httpx.Response(200, text="pas du json")))
    assert _executer(sc.envoyer(corps)) is None
    # Hors boucle asyncio : la programmation échoue proprement (faux), sans exception
    assert sc.signaler_connexion("u1", ip="1.1.1.1", user_agent=NAVIGATEUR) is False


def test_connexion_reussie_meme_si_sawali_en_panne(client, sawali, monkeypatch):
    """La connexion n'est jamais bloquée par SAWALI."""
    def panne(requete):
        raise httpx.ConnectTimeout("délai dépassé", request=requete)

    monkeypatch.setattr(sc, "_transport", httpx.MockTransport(panne))
    r = client.post("/api/auth/register", headers={"user-agent": NAVIGATEUR}, json={
        "full_name": "Ben Panne", "email": "ben.panne@example.com", "password": "motdepasse123",
        "gender": "homme", "birthdate": "1990-01-01"})
    assert r.status_code == 201, r.text
