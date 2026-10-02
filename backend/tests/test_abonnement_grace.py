"""Période de grâce (A) : 3 jours par défaut, réglable par membre (0 à 30), bouton
« +3 jours » limité à 3 fois par échéance, coupure des fonctions payantes à
l'heure exacte (visage en clair), bandeau du membre, droits."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

import abonnement_grace
import parametres_plateforme
from db import db
from routes.subscriptions import has_active_subscription


@pytest.fixture(autouse=True)
def reglages_propres(client):
    client.portal.call(lambda: db.parametres_plateforme.delete_many({}))
    parametres_plateforme.vider_cache()
    yield
    client.portal.call(lambda: db.parametres_plateforme.delete_many({}))
    parametres_plateforme.vider_cache()


def _abonner(client, uid, echeance: datetime):
    sub = {"id": str(uuid.uuid4()), "user_id": uid, "plan_id": "p", "status": "active",
           "started_at": (echeance - timedelta(days=30)).isoformat(), "expires_at": echeance.isoformat(),
           "created_at": datetime.now(timezone.utc).isoformat()}
    client.portal.call(lambda: db.subscriptions.insert_one(dict(sub)))
    return sub


def _admin(client, make_user):
    uid, headers, _ = make_user()
    client.portal.call(lambda: db.users.update_one({"id": uid}, {"$set": {"role": "admin"}}))
    return headers


def _premium(client, uid):
    return client.portal.call(lambda: has_active_subscription(uid))


def test_etats_actif_grace_expire(client, make_user):
    maintenant = datetime.now(timezone.utc)
    uid, h, _ = make_user()
    assert client.get("/api/abonnement/etat", headers=h).json()["statut"] == "aucun"
    _abonner(client, uid, maintenant + timedelta(days=5))
    assert client.get("/api/abonnement/etat", headers=h).json()["statut"] == "actif"
    assert _premium(client, uid)

    uid2, h2, _ = make_user()
    _abonner(client, uid2, maintenant - timedelta(days=1, hours=1))
    etat = client.get("/api/abonnement/etat", headers=h2).json()
    assert etat["statut"] == "grace" and etat["jours_grace_restants"] == 2 and etat["grace_jours"] == 3
    assert _premium(client, uid2)  # accès normal pendant la grâce
    # /subscriptions/me ne dit pas « expiré » pendant la grâce
    assert client.get("/api/subscriptions/me", headers=h2).json()["status"] == "active"

    uid3, h3, _ = make_user()
    _abonner(client, uid3, maintenant - timedelta(days=3, minutes=1))
    etat = client.get("/api/abonnement/etat", headers=h3).json()
    assert etat["statut"] == "expire" and "cycle_vie" in etat
    assert not _premium(client, uid3)
    assert client.get("/api/subscriptions/me", headers=h3).json()["status"] == "expired"


def test_coupure_a_l_heure_exacte(client, make_user, monkeypatch):
    echeance = datetime.now(timezone.utc) - timedelta(days=1)
    uid, _, _ = make_user()
    _abonner(client, uid, echeance)
    fin = echeance + timedelta(days=3)
    monkeypatch.setattr(abonnement_grace, "maintenant", lambda: fin - timedelta(seconds=1))
    assert _premium(client, uid)
    monkeypatch.setattr(abonnement_grace, "maintenant", lambda: fin)
    assert not _premium(client, uid)


def test_photos_floutees_apres_la_grace(client, make_user):
    """Fonction payante coupée côté serveur : la liste des conversations renvoie
    la version masquée des photos de l'autre membre après la grâce."""
    from routes.chat import _masked_photos
    photos = [{"id": "x", "url": "clair.jpg", "masked_url": "flou.jpg", "status": "approved"}]
    assert _masked_photos(photos, True)[0]["url"] == "clair.jpg"
    assert _masked_photos(photos, False)[0]["url"] == "flou.jpg"
    uid, _, _ = make_user()
    _abonner(client, uid, datetime.now(timezone.utc) - timedelta(days=4))
    assert _masked_photos(photos, _premium(client, uid))[0]["url"] == "flou.jpg"


def test_delai_par_membre_et_par_defaut(client, make_user):
    admin = _admin(client, make_user)
    uid, h, _ = make_user()
    _abonner(client, uid, datetime.now(timezone.utc) - timedelta(days=5))
    assert client.get("/api/abonnement/etat", headers=h).json()["statut"] == "expire"
    assert client.put(f"/api/admin/membres/{uid}/grace", json={"jours": 31}, headers=admin).status_code == 400
    assert client.put(f"/api/admin/membres/{uid}/grace", json={"jours": -1}, headers=admin).status_code == 400
    r = client.put(f"/api/admin/membres/{uid}/grace", json={"jours": 10}, headers=admin)
    assert r.status_code == 200 and r.json()["statut"] == "grace" and r.json()["grace_jours"] == 10
    # Retour à la valeur de la plateforme, elle-même réglable (0 à 30)
    client.put(f"/api/admin/membres/{uid}/grace", json={"jours": None}, headers=admin)
    url = "/api/plateforme/parametres/abonnements-sessions"
    assert client.put(url, json={"grace_jours_defaut": 31}, headers=admin).status_code == 400
    assert client.put(url, json={"grace_jours_defaut": 7}, headers=admin).status_code == 200
    assert client.get("/api/abonnement/etat", headers=h).json()["statut"] == "grace"
    # Journalisé
    histo = client.get(f"/api/admin/membres/{uid}/abonnement", headers=admin).json()["historique"]
    assert any(l["action"] == "délai de grâce modifié" for l in histo)


def test_renouveler_la_grace_trois_fois(client, make_user):
    admin = _admin(client, make_user)
    uid, h, _ = make_user()
    # Abonnement actif : pas d'échéance impayée
    sub = _abonner(client, uid, datetime.now(timezone.utc) + timedelta(days=2))
    assert client.post(f"/api/admin/membres/{uid}/grace/renouveler", headers=admin).status_code == 400
    # Échéance impayée depuis 5 jours : expiré, puis +3 j -> grâce (fin à J+6)
    nouvelle = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
    client.portal.call(lambda: db.subscriptions.update_one({"id": sub["id"]}, {"$set": {"expires_at": nouvelle}}))
    for fois in (1, 2, 3):
        r = client.post(f"/api/admin/membres/{uid}/grace/renouveler", headers=admin)
        assert r.status_code == 200, r.text
        assert r.json()["renouvellements_grace"] == fois and r.json()["statut"] == "grace"
    r = client.post(f"/api/admin/membres/{uid}/grace/renouveler", headers=admin)
    assert r.status_code == 400 and "3 fois" in r.json()["detail"]
    assert client.get("/api/abonnement/etat", headers=h).json()["fin_grace"]
    # Nouvelle échéance (paiement) : compteur remis à zéro
    autre = (datetime.now(timezone.utc) - timedelta(days=4)).isoformat()
    client.portal.call(lambda: db.subscriptions.update_one({"id": sub["id"]}, {"$set": {"expires_at": autre}}))
    assert client.post(f"/api/admin/membres/{uid}/grace/renouveler", headers=admin).json()["renouvellements_grace"] == 1
    # Réservé à l'administrateur principal
    assert client.post(f"/api/admin/membres/{uid}/grace/renouveler", headers=h).status_code == 403
    assert client.put(f"/api/admin/membres/{uid}/grace", json={"jours": 5}, headers=h).status_code == 403
