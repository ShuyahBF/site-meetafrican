"""Lot 57 — statistiques internes du jour demandées par SAWALI
(POST /api/webhooks/liluvine-retour, type « stats_du_jour »)."""
import hashlib
import hmac
import json
import time
from datetime import datetime, timedelta, timezone

import pytest

ROUTE = "/api/webhooks/liluvine-retour"
CLE = "cle-de-test-non-secrete-stats"


@pytest.fixture
def cle(monkeypatch):
    """Clé HMAC partagée avec SAWALI (valeur de test, jamais une vraie clé)."""
    monkeypatch.setenv("LILUVINE_WA_HMAC", CLE)


def _poster(client, donnees, cle_signature=CLE, decalage=0, signature=None):
    """Envoie la demande signée exactement comme SAWALI."""
    corps = json.dumps(donnees).encode("utf-8")
    ts = str(int(time.time()) + decalage)
    sig = signature or hmac.new(cle_signature.encode(), ts.encode() + b"." + corps, hashlib.sha256).hexdigest()
    return client.post(ROUTE, content=corps, headers={
        "Content-Type": "application/json", "X-Emetteur": "sawali", "X-Timestamp": ts, "X-Signature": sig})


def _periode_du_jour():
    """Période [aujourd'hui 00:00 UTC, demain 00:00 UTC) au format ISO « Z »."""
    debut = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    fin = debut + timedelta(days=1)
    return debut.strftime("%Y-%m-%dT%H:%M:%SZ"), fin.strftime("%Y-%m-%dT%H:%M:%SZ")


def test_stats_signature_valide_renvoie_les_indicateurs(client, make_user, cle):
    # Un membre inscrit (et donc connecté) aujourd'hui, puis actif à l'instant
    _, entetes, _ = make_user()
    assert client.get("/api/auth/me", headers=entetes).status_code == 200
    debut, fin = _periode_du_jour()
    r = _poster(client, {"type": "stats_du_jour", "debut": debut, "fin": fin})
    assert r.status_code == 200, r.text
    corps = r.json()
    assert set(corps) == {"indicateurs", "faits_marquants", "utilisateurs_connectes"}
    # 4 à 10 indicateurs {cle, libelle, valeur numérique}
    assert 4 <= len(corps["indicateurs"]) <= 10
    for ind in corps["indicateurs"]:
        assert set(ind) == {"cle", "libelle", "valeur"} and isinstance(ind["valeur"], (int, float))
    valeurs = {i["cle"]: i["valeur"] for i in corps["indicateurs"]}
    assert valeurs["inscriptions"] >= 1 and valeurs["connexions"] >= 1
    # Faits marquants : 5 au plus, en texte
    assert 1 <= len(corps["faits_marquants"]) <= 5
    assert all(isinstance(f, str) and f for f in corps["faits_marquants"])
    # Le membre qui vient d'agir est compté parmi les connectés
    assert isinstance(corps["utilisateurs_connectes"], int) and corps["utilisateurs_connectes"] >= 1
    assert CLE not in r.text


def test_stats_signature_invalide_401(client, cle):
    debut, fin = _periode_du_jour()
    donnees = {"type": "stats_du_jour", "debut": debut, "fin": fin}
    assert _poster(client, donnees, signature="0" * 64).status_code == 401
    assert _poster(client, donnees, cle_signature="mauvaise-cle").status_code == 401
    # Horodatage hors de la fenêtre de ±300 s
    assert _poster(client, donnees, decalage=-400).status_code == 401


def test_stats_sans_cle_503(client, monkeypatch):
    monkeypatch.delenv("LILUVINE_WA_HMAC", raising=False)
    debut, fin = _periode_du_jour()
    assert _poster(client, {"type": "stats_du_jour", "debut": debut, "fin": fin}).status_code == 503


@pytest.mark.parametrize("periode", [
    {},                                                                   # dates absentes
    {"debut": "hier", "fin": "aujourd'hui"},                              # illisibles
    {"debut": "2026-10-05T00:00:00Z", "fin": "2026-10-04T00:00:00Z"},     # inversée
    {"debut": "2026-10-05T00:00:00Z", "fin": "2026-10-05T00:00:00Z"},     # vide
    {"debut": "2026-08-01T00:00:00Z", "fin": "2026-09-02T00:00:00Z"},     # > 31 jours
])
def test_stats_periode_invalide_422(client, cle, periode):
    assert _poster(client, {"type": "stats_du_jour", **periode}).status_code == 422
