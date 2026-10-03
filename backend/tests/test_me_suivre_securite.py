"""Lot 53 — « Me suivre » renforcé : positions renvoyées après une coupure d'Internet,
« Je suis arrivé·e », alerte « signal perdu » (personne de confiance + administrateurs),
pas de déconnexion pour inactivité pendant un suivi, liste complète des comptes de test."""
import asyncio
from datetime import datetime, timedelta, timezone

import pytest

import envoi_email
import envoi_messages
import inactivite
import parametres_plateforme
import sessions_comptes
from db import db
from routes import tracking


@pytest.fixture(autouse=True)
def envois_simules(client, monkeypatch):
    """Aucun envoi réel : on note seulement qui aurait été prévenu."""
    notes = {"membres": [], "admins": [], "emails": []}

    async def envoyer(user, texte):
        notes["membres"].append((user.get("id"), texte))
        return {"ok": True, "canal": "whatsapp", "erreur": None}

    async def alerter(texte, corps_email=None):
        notes["admins"].append(texte)
        return 1

    async def email(dest, sujet, corps, contexte, user_id=None):
        notes["emails"].append((dest, contexte))
        return {"statut": "ENVOYE", "erreur": None, "fournisseur": "test"}

    monkeypatch.setattr(envoi_messages, "envoyer", envoyer)
    monkeypatch.setattr(envoi_messages, "alerter_administrateurs", alerter)
    monkeypatch.setattr(envoi_email, "envoyer_journalise", email)
    tracking._vider_cache_suivi()
    yield notes
    tracking._vider_cache_suivi()


def _attendre(client):
    """Les alertes partent en tâche de fond : on leur laisse le temps de s'exécuter."""
    client.portal.call(asyncio.sleep, 0.2)


def _suivi(client, make_user, minutes=60):
    owner_id, owner, _ = make_user()
    guardian_id, guardian, _ = make_user()
    email = client.portal.call(lambda: db.users.find_one({"id": guardian_id}))["email"]
    s = client.post("/api/tracking/sessions", json={"guardian_email": email, "duration_minutes": minutes}, headers=owner).json()
    return s, (owner_id, owner), (guardian_id, guardian)


def test_positions_hors_connexion_renvoyees_avec_leur_heure(client, make_user):
    s, (_, owner), (_, guardian) = _suivi(client, make_user)
    maintenant = datetime.now(timezone.utc)
    points = [
        {"lat": 12.30, "lng": -1.50, "accuracy": 20, "at": (maintenant - timedelta(seconds=40)).isoformat()},
        {"lat": 12.31, "lng": -1.51, "accuracy": 20, "at": (maintenant - timedelta(seconds=20)).isoformat()},
        # Prise AVANT le début du suivi : ignorée
        {"lat": 1, "lng": 1, "accuracy": 20, "at": (maintenant - timedelta(hours=2)).isoformat()},
    ]
    r = client.post(f"/api/tracking/sessions/{s['id']}/points/lot", json={"points": points}, headers=owner)
    assert r.status_code == 200 and r.json() == {"ok": True, "enregistres": 2, "ignores": 1}
    vu = client.get(f"/api/tracking/sessions/{s['id']}", headers=guardian).json()
    assert [p["lat"] for p in vu["points"]] == [12.30, 12.31]
    assert vu["last_point"]["lat"] == 12.31 and vu["points"][0].get("hors_connexion") is True
    # Seul le membre suivi peut envoyer ses positions
    assert client.post(f"/api/tracking/sessions/{s['id']}/points/lot", json={"points": points}, headers=guardian).status_code == 404


def test_je_suis_arrive_previent_gardien_et_administrateurs(client, make_user, envois_simules):
    s, (_, owner), (guardian_id, guardian) = _suivi(client, make_user)
    assert client.post(f"/api/tracking/sessions/{s['id']}/arrive", headers=owner).status_code == 200
    _attendre(client)
    vu = client.get(f"/api/tracking/sessions/{s['id']}", headers=guardian).json()
    assert vu["status"] == "stopped" and vu["motif_fin"] == "arrive" and vu["arrive_le"]
    assert envois_simules["membres"][-1][0] == guardian_id and "bien arrivé" in envois_simules["membres"][-1][1]
    assert any("bien arrivé" in t for t in envois_simules["admins"])
    alerte = client.portal.call(lambda: db.tracking_alertes.find_one({"session_id": s["id"]}))
    assert alerte["type"] == "arrivee"
    # Une seule fois
    assert client.post(f"/api/tracking/sessions/{s['id']}/arrive", headers=owner).status_code == 404


def test_alerte_signal_perdu_puis_retabli(client, make_user, envois_simules):
    staff_id, staff, _ = make_user()
    client.portal.call(lambda: db.users.update_one({"id": staff_id}, {"$set": {"role": "admin"}}))
    s, (_, owner), (guardian_id, _) = _suivi(client, make_user)
    # Dernière position il y a 12 minutes
    ancien = (datetime.now(timezone.utc) - timedelta(minutes=12)).isoformat()
    client.portal.call(lambda: db.tracking_sessions.update_one(
        {"id": s["id"]}, {"$set": {"started_at": ancien, "last_point": {"lat": 12.3, "lng": -1.5, "accuracy": 10, "at": ancien}}}))
    assert client.portal.call(tracking.verifier_signaux) == 1
    assert client.portal.call(tracking.verifier_signaux) == 0  # une seule alerte tant que le signal n'est pas revenu
    texte = envois_simules["membres"][-1][1]
    assert envois_simules["membres"][-1][0] == guardian_id and "signal perdu" in texte and "google.com/maps" in texte
    assert any("signal perdu" in t for t in envois_simules["admins"])
    suivis = client.get("/api/admin/tracking", headers=staff).json()
    assert next(x for x in suivis if x["id"] == s["id"])["alerte_signal"]["depuis"] == ancien
    # Une position revient : « signal rétabli » et l'alerte est levée
    assert client.post(f"/api/tracking/sessions/{s['id']}/points", json={"lat": 12.31, "lng": -1.51}, headers=owner).json()["ok"]
    _attendre(client)
    assert "signal rétabli" in envois_simules["membres"][-1][1]
    assert client.portal.call(lambda: db.tracking_sessions.find_one({"id": s["id"]}))["alerte_signal"] is None
    types = [a["type"] for a in client.get("/api/admin/tracking/alertes", headers=staff).json() if a["session_id"] == s["id"]]
    assert types == ["signal_retabli", "signal_perdu"]
    # Historique réservé à l'équipe
    assert client.get("/api/admin/tracking/alertes", headers=owner).status_code == 403


def test_pas_de_deconnexion_pour_inactivite_pendant_un_suivi(client, make_user, monkeypatch):
    staff_id, staff, _ = make_user()
    client.portal.call(lambda: db.users.update_one({"id": staff_id}, {"$set": {"role": "admin"}}))
    client.put("/api/plateforme/parametres/abonnements-sessions", json={"inactivite_secondes": 60}, headers=staff)
    sessions_comptes.vider_cache()
    s, (_, owner), (_, guardian) = _suivi(client, make_user)
    _, sans_suivi, _ = make_user()
    base = inactivite._maintenant()
    decalage = {"s": 0}
    monkeypatch.setattr(inactivite, "_maintenant", lambda: base + decalage["s"])
    for h in (owner, guardian, sans_suivi):
        assert client.get("/api/auth/me", headers=h).status_code == 200
    # 10 minutes sans activité : le membre suivi et la personne de confiance restent connectés
    decalage["s"] = 600
    assert client.get("/api/auth/me", headers=owner).status_code == 200
    assert client.get("/api/auth/me", headers=guardian).status_code == 200
    assert client.get("/api/auth/me", headers=sans_suivi).status_code == 401
    # Suivi arrêté : la règle normale reprend (après la durée réglée)
    client.post(f"/api/tracking/sessions/{s['id']}/stop", headers=owner)
    decalage["s"] = 800
    assert client.get("/api/auth/me", headers=guardian).status_code == 401
    client.portal.call(lambda: parametres_plateforme.modifier({"inactivite_secondes": 0}, "test"))
    sessions_comptes.vider_cache()


def test_liste_complete_des_comptes_de_test(client, make_user):
    staff_id, staff, _ = make_user()
    client.portal.call(lambda: db.users.update_one({"id": staff_id}, {"$set": {"role": "admin"}}))
    ids = [make_user()[0] for _ in range(9)]
    client.portal.call(lambda: db.users.update_many({"id": {"$in": ids}}, {"$set": {"is_test_data": True}}))
    comptes = client.get("/api/admin/test-data", headers=staff).json()["credentials"]["sample_accounts"]
    assert len(comptes) >= 9 and all("email" in c and "full_name" in c for c in comptes)
    client.portal.call(lambda: db.users.update_many({"id": {"$in": ids}}, {"$unset": {"is_test_data": ""}}))
