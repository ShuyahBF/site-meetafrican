"""Maintenance de la plateforme (déconnexion de tous les utilisateurs) :
phases, refus après l'échéance, administrateur jamais bloqué, annulation,
réactivation (sessions antérieures invalidées) et routes non bloquées.

Les phases sont normalement atteintes au fil des minutes : ici, les dates de
l'annonce sont réécrites directement en base pour ne pas attendre.
"""
import time
from datetime import datetime, timedelta, timezone

import pytest
from starlette.websockets import WebSocketDisconnect

import maintenance_plateforme as service
from db import db

MDP = "motdepasse123"
URL = "/api/plateforme/deconnexion-generale"


def _effacer(client):
    async def effacer():
        await db.maintenance_plateforme.delete_many({})
        await db.maintenance_plateforme_journal.delete_many({})
    client.portal.call(effacer)
    service.vider_cache()


@pytest.fixture(autouse=True)
def etat_propre(client):
    """Aucune maintenance avant ni après chaque test (la base est partagée)."""
    _effacer(client)
    yield
    _effacer(client)


def _compte(client, make_user, role=None):
    uid, headers, _ = make_user()
    if role:
        client.portal.call(lambda: db.users.update_one({"id": uid}, {"$set": {"role": role}}))
    email = client.portal.call(lambda: db.users.find_one({"id": uid}))["email"]
    return uid, headers, email


def _decaler(client, debut_verrouillage_s, echeance_s):
    """Place le début du verrouillage et l'échéance à N secondes de maintenant."""
    maintenant = datetime.now(timezone.utc)
    client.portal.call(lambda: db.maintenance_plateforme.update_one({"_id": service.ID_ETAT}, {"$set": {
        "debut_verrouillage": (maintenant + timedelta(seconds=debut_verrouillage_s)).isoformat(),
        "echeance": (maintenant + timedelta(seconds=echeance_s)).isoformat()}}))
    service.vider_cache()


def _annoncer(client, admin, **champs):
    corps = {"message": "Transfert de la base vers le nouveau cluster", **champs}
    return client.post(URL, json=corps, headers=admin)


def test_etat_public_sans_maintenance(client):
    etat = client.get("/api/maintenance/etat").json()
    assert etat["phase"] == "aucune" and etat["active"] is False and "maintenant_serveur" in etat


def test_reglages_et_droits(client, make_user):
    _, admin, _ = _compte(client, make_user, "admin")
    _, membre, _ = _compte(client, make_user)
    _, moderateur, _ = _compte(client, make_user, "moderator")
    assert client.post(URL, json={"message": "x"}).status_code == 401
    assert client.post(URL, json={"message": "x"}, headers=membre).status_code == 403
    assert client.post(URL, json={"message": "x"}, headers=moderateur).status_code == 403
    assert client.get(URL, headers=moderateur).status_code == 403
    assert _annoncer(client, admin, message="   ").status_code == 422
    assert _annoncer(client, admin, duree_minutes=0).status_code == 422
    assert _annoncer(client, admin, duree_minutes=121).status_code == 422
    assert _annoncer(client, admin, part_verrouillage=101).status_code == 422

    # Valeurs par défaut : 5 minutes, 80 % verrouillées -> verrouillage à 1 minute
    r = _annoncer(client, admin)
    assert r.status_code == 200, r.text
    etat = r.json()
    assert etat["phase"] == "annonce" and etat["duree_minutes"] == 5 and etat["part_verrouillage"] == 80
    annonce = datetime.fromisoformat(etat["annonce_le"])
    assert datetime.fromisoformat(etat["debut_verrouillage"]) - annonce == timedelta(minutes=1)
    assert datetime.fromisoformat(etat["echeance"]) - annonce == timedelta(minutes=5)
    assert 295 <= etat["secondes_restantes"] <= 300
    assert etat["journal"][0]["action"] == "ANNONCE"
    # Une seule annonce à la fois
    assert _annoncer(client, admin).status_code == 409
    # L'état public ne contient ni l'auteur ni le journal
    public = client.get("/api/maintenance/etat").json()
    assert public["phase"] == "annonce" and public["message"].startswith("Transfert")
    assert "journal" not in public and "annonce_par" not in public


def test_annonce_verrouillage_puis_annulation(client, make_user):
    _, admin, _ = _compte(client, make_user, "admin")
    _, membre, _ = _compte(client, make_user)
    _annoncer(client, admin)
    # Annonce et verrouillage : les membres travaillent encore (le site affiche le décompte)
    assert client.get("/api/auth/me", headers=membre).status_code == 200
    _decaler(client, -1, 30)
    etat = client.get("/api/maintenance/etat").json()
    assert etat["phase"] == "verrouillage" and 0 < etat["secondes_restantes"] <= 30
    assert client.get("/api/auth/me", headers=membre).status_code == 200
    # Annulation avant l'échéance : personne n'est déconnecté
    r = client.post(f"{URL}/annuler", headers=admin)
    assert r.status_code == 200 and r.json()["phase"] == "aucune"
    assert r.json()["journal"][0]["action"] == "ANNULATION"
    assert client.get("/api/auth/me", headers=membre).status_code == 200
    assert client.post(f"{URL}/annuler", headers=admin).status_code == 409
    assert client.post(f"{URL}/reactiver", headers=admin).status_code == 409


def test_maintenance_bloque_les_membres_pas_l_administrateur(client, make_user):
    _, admin, email_admin = _compte(client, make_user, "admin")
    _, membre, email_membre = _compte(client, make_user)
    _, moderateur, _ = _compte(client, make_user, "moderator")
    _annoncer(client, admin)
    _decaler(client, -2, -1)
    assert client.get("/api/maintenance/etat").json()["phase"] == "maintenance"

    # Membres et modérateurs : refus serveur (503), connexion et inscription bloquées
    r = client.get("/api/auth/me", headers=membre)
    assert r.status_code == 503 and "maintenance" in r.json()["detail"]
    assert client.get("/api/conversations", headers=membre).status_code == 503
    assert client.get("/api/auth/me", headers=moderateur).status_code == 503
    assert client.post("/api/auth/login", json={"identifier": email_membre, "password": MDP}).status_code == 503
    r = client.post("/api/auth/register", json={"full_name": "Nouveau", "email": "nouveau-maint@example.com",
                                                "password": MDP, "gender": "homme", "birthdate": "1990-01-01"})
    assert r.status_code == 503
    # Chat temps réel refusé
    jeton = membre["Authorization"].split()[1]
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect(f"/api/ws/conversations/inconnue?token={jeton}") as ws:
            ws.receive_json()
    assert exc.value.code == 4401

    # Administrateur principal : jamais bloqué, peut se connecter
    assert client.get("/api/auth/me", headers=admin).status_code == 200
    assert client.get("/api/admin/team", headers=admin).status_code == 200
    assert client.post("/api/auth/login", json={"identifier": email_admin, "password": MDP}).status_code == 200
    # Annuler n'est plus possible après l'échéance
    assert client.post(f"{URL}/annuler", headers=admin).status_code == 409


def test_routes_non_bloquees(client, make_user):
    _, admin, _ = _compte(client, make_user, "admin")
    _annoncer(client, admin)
    _decaler(client, -2, -1)
    for url in ("/api/health", "/api/maintenance/etat", "/api/appearance", "/api/stats/public",
                "/api/testimonials", "/api/subscriptions/plans", "/api/gifts", "/api/profile-options",
                "/api/auth/tiktok/config", "/api/plateforme/transfert/restauration-initiale"):
        assert client.get(url).status_code == 200, url
    assert client.post("/api/stats/visit").status_code == 200
    # Webhook PawaPay : jamais 503 (ici 403, secret de test invalide)
    r = client.post("/api/payments/pawapay/webhooks/deposits/secret-invalide", json={})
    assert r.status_code == 403
    # Retour OAuth TikTok : redirection vers le site, jamais 503
    r = client.get("/api/auth/tiktok/callback", params={"error": "access_denied"}, follow_redirects=False)
    assert r.status_code in (302, 307) and "/connexion" in r.headers["location"]


def test_reactivation_invalide_les_sessions_anterieures(client, make_user):
    _, admin, _ = _compte(client, make_user, "admin")
    _, membre, email_membre = _compte(client, make_user)
    _annoncer(client, admin)
    time.sleep(0.05)  # l'échéance tombe APRÈS l'ouverture de la session du membre
    _decaler(client, -1, 0)
    assert client.get("/api/auth/me", headers=membre).status_code == 503

    r = client.post(f"{URL}/reactiver", headers=admin)
    assert r.status_code == 200, r.text
    etat = r.json()
    assert etat["phase"] == "aucune" and etat["sessions_valides_apres"]
    assert etat["journal"][0]["action"] == "REACTIVATION"
    # Ancienne session : refusée (401), il faut se reconnecter
    r = client.get("/api/auth/me", headers=membre)
    assert r.status_code == 401
    # Nouvelle connexion : acceptée
    r = client.post("/api/auth/login", json={"identifier": email_membre, "password": MDP})
    assert r.status_code == 200
    nouveau = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert client.get("/api/auth/me", headers=nouveau).status_code == 200
    # L'administrateur (exempté) garde sa session
    assert client.get("/api/auth/me", headers=admin).status_code == 200
