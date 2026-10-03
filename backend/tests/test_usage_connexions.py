"""Lot 47 — onglet « Usage » : journal des connexions (IP réelle), accès réservé au
super-administrateur, pastilles de présence, blocages d'IP (ce compte / tous) et de
comptes, levée des blocages, auto-blocage interdit, journal des actions."""
import time

import pytest

import blocages_acces
import sessions_comptes
from db import db

MDP = "motdepasse123"


def _nettoyer(client):
    """Aucun blocage ne doit survivre à un test (il bloquerait les suivants)."""
    client.portal.call(lambda: db.blocages.delete_many({}))
    blocages_acces.vider_cache()
    sessions_comptes.vider_cache()


@pytest.fixture(autouse=True)
def propre(client):
    _nettoyer(client)
    yield
    _nettoyer(client)


def _email(client, uid):
    return client.portal.call(lambda: db.users.find_one({"id": uid}))["email"]


def _ip(ip):
    """En-têtes d'une requête passée par le proxy de Render (vraie IP en 1re position)."""
    return {"X-Forwarded-For": f"{ip}, 10.0.0.1", "User-Agent": "Mozilla/5.0 (Windows NT 10.0) Chrome/120"}


def _connexion(client, email, ip):
    return client.post("/api/auth/login", json={"identifier": email, "password": MDP}, headers=_ip(ip))


def _jeton(client, email, ip):
    r = _connexion(client, email, ip)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}", **_ip(ip)}


def _admin(client, make_user):
    uid, headers, _ = make_user()
    client.portal.call(lambda: db.users.update_one({"id": uid}, {"$set": {"role": "admin"}}))
    return uid, headers


def _est_suspendu(r):
    return r.status_code == 403 and r.json()["detail"]["code"] == "acces_suspendu"


def test_journal_enregistre_ip_reelle_et_methode(client, make_user):
    uid, _, _ = make_user()
    _jeton(client, _email(client, uid), "198.51.100.7")
    ligne = client.portal.call(lambda: db.connexions_journal.find_one(
        {"user_id": uid, "ip": "198.51.100.7"}, sort=[("date", -1)]))
    assert ligne and ligne["etat"] == "reussie" and ligne["methode"] == "mot_de_passe"
    assert ligne["sid"] and ligne["appareil"] == "Chrome sur Windows"
    # L'inscription (fixture make_user) est aussi au journal
    assert client.portal.call(lambda: db.connexions_journal.find_one({"user_id": uid, "methode": "inscription"}))


def test_liste_reservee_au_super_admin(client, make_user):
    _, membre, _ = make_user()
    assert client.get("/api/admin/usage/connexions", headers=membre).status_code == 403
    mod_id, moderateur, _ = make_user()
    client.portal.call(lambda: db.users.update_one({"id": mod_id}, {"$set": {"role": "moderator"}}))
    assert client.get("/api/admin/usage/connexions", headers=moderateur).status_code == 403
    assert client.get("/api/admin/usage/blocages", headers=moderateur).status_code == 403
    uid, _ = make_user()[:2]
    _jeton(client, _email(client, uid), "198.51.100.8")
    _, admin = _admin(client, make_user)
    r = client.get("/api/admin/usage/connexions", params={"q": "198.51.100.8"}, headers=admin)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["par_page"] == 50 and data["total"] >= 1
    ligne = data["items"][0]
    assert ligne["ip"] == "198.51.100.8" and ligne["compte"]["id"] == uid
    assert ligne["abonnement"]["statut"] == "aucun" and ligne["ip_etat"] == "autorisee"
    assert ligne["presence"]["couleur"] == "vert"
    # Filtre sur l'état de l'abonnement : ce membre n'a pas d'abonnement actif
    r = client.get("/api/admin/usage/connexions", params={"q": "198.51.100.8", "abonnement": "actif"}, headers=admin)
    assert r.json()["total"] == 0


def test_presence_vert_orange_rouge(client, make_user):
    uid, _ = make_user()[:2]
    _jeton(client, _email(client, uid), "198.51.100.9")
    sid = client.portal.call(lambda: db.connexions_journal.find_one(
        {"user_id": uid, "ip": "198.51.100.9"}))["sid"]
    _, admin = _admin(client, make_user)
    fond = {**admin, "X-BA-Fond": "1"}

    def couleur(il_y_a):
        client.portal.call(lambda: db.sessions.update_one(
            {"_id": sid}, {"$set": {"derniere_activite": time.time() - il_y_a}}))
        r = client.get("/api/admin/usage/presence", params={"sids": sid}, headers=fond)
        assert r.status_code == 200
        return r.json()["presence"][sid]["couleur"]

    assert couleur(60) == "vert"
    assert couleur(7 * 60) == "orange"
    assert couleur(11 * 60) == "rouge"
    client.portal.call(lambda: db.sessions.update_one({"_id": sid}, {"$set": {"fermee": True}}))
    assert couleur(10) == "rouge"  # déconnecté


def test_blocage_ip_tous_les_comptes(client, make_user):
    ip = "203.0.113.10"
    a, _ = make_user()[:2]
    b, _ = make_user()[:2]
    session_a = _jeton(client, _email(client, a), ip)
    assert client.get("/api/auth/me", headers=session_a).status_code == 200
    _, admin = _admin(client, make_user)
    r = client.post("/api/admin/usage/blocages", json={"type": "ip", "ip": ip, "tous_comptes": True,
                                                      "libelle": "Cybercafé test"}, headers=admin)
    assert r.status_code == 200, r.text
    assert r.json()["portee"] == "tous" and r.json()["sessions_fermees"] >= 1
    # Session en cours fermée : la requête suivante reçoit la page « accès suspendu »
    r = client.get("/api/auth/me", headers=session_a)
    assert _est_suspendu(r)
    assert "contacter" in r.json()["detail"]["message"].lower() or "Contactez" in r.json()["detail"]["message"]
    # Nouvelle connexion refusée, pour les DEUX comptes, et tentative journalisée « refusée »
    assert _est_suspendu(_connexion(client, _email(client, a), ip))
    assert _est_suspendu(_connexion(client, _email(client, b), ip))
    assert client.portal.call(lambda: db.connexions_journal.find_one({"user_id": b, "etat": "refusee", "motif": "ip"}))
    # Inscription depuis cette IP refusée aussi
    r = client.post("/api/auth/register", headers=_ip(ip), json={
        "full_name": "Nouveau", "email": "bloque-inscription@example.com", "password": MDP,
        "gender": "femme", "birthdate": "1990-01-01"})
    assert _est_suspendu(r)
    # Depuis une autre IP : connexion normale
    assert _connexion(client, _email(client, a), "203.0.113.11").status_code == 200
    # Le tableau affiche l'IP comme bloquée pour tous
    lignes = client.get("/api/admin/usage/connexions", params={"q": ip}, headers=admin).json()["items"]
    assert lignes and all(l["ip_etat"] == "bloquee_tous" for l in lignes)
    assert any(l["etat"] == "refusee" for l in lignes)
    # Autoriser : le blocage est levé, la connexion redevient possible
    r = client.post("/api/admin/usage/autoriser", json={"type": "ip", "ip": ip}, headers=admin)
    assert r.status_code == 200 and r.json()["leves"] == 1
    assert _connexion(client, _email(client, a), ip).status_code == 200
    # L'ancienne session (fermée) demande simplement de se reconnecter
    r = client.get("/api/auth/me", headers=session_a)
    assert r.status_code == 401 and r.json()["detail"] == "Session fermée. Reconnectez-vous."


def test_blocage_ip_pour_ce_compte_seulement(client, make_user):
    ip = "203.0.113.20"
    a, _ = make_user()[:2]
    b, _ = make_user()[:2]
    _, admin = _admin(client, make_user)
    r = client.post("/api/admin/usage/blocages", json={"type": "ip", "ip": ip, "user_id": a,
                                                      "tous_comptes": False}, headers=admin)
    assert r.status_code == 200 and r.json()["portee"] == "compte"
    assert _est_suspendu(_connexion(client, _email(client, a), ip))
    assert _connexion(client, _email(client, b), ip).status_code == 200
    assert _connexion(client, _email(client, a), "203.0.113.21").status_code == 200
    # Liste « Blocages en cours » puis levée
    liste = client.get("/api/admin/usage/blocages", headers=admin).json()["blocages"]
    assert len(liste) == 1
    assert client.post(f"/api/admin/usage/blocages/{liste[0]['id']}/lever", headers=admin).status_code == 200
    assert _connexion(client, _email(client, a), ip).status_code == 200
    assert client.get("/api/admin/usage/blocages", headers=admin).json()["blocages"] == []


def test_blocage_du_compte(client, make_user):
    a, _ = make_user()[:2]
    session = _jeton(client, _email(client, a), "203.0.113.30")
    _, admin = _admin(client, make_user)
    r = client.post("/api/admin/usage/blocages", json={"type": "compte", "user_id": a}, headers=admin)
    assert r.status_code == 200, r.text
    assert _est_suspendu(client.get("/api/auth/me", headers=session))
    assert _est_suspendu(_connexion(client, _email(client, a), "203.0.113.31"))
    assert client.portal.call(lambda: db.connexions_journal.find_one({"user_id": a, "etat": "refusee",
                                                                      "motif": "compte"}))
    assert client.post("/api/admin/usage/blocages", json={"type": "compte", "user_id": a},
                       headers=admin).status_code == 409
    r = client.post("/api/admin/usage/autoriser", json={"type": "compte", "user_id": a}, headers=admin)
    assert r.json()["leves"] == 1
    assert _connexion(client, _email(client, a), "203.0.113.31").status_code == 200


def test_super_admin_ne_peut_pas_se_bloquer(client, make_user):
    admin_id, admin = _admin(client, make_user)
    r = client.post("/api/admin/usage/blocages", json={"type": "compte", "user_id": admin_id}, headers=admin)
    assert r.status_code == 400 and "super-administrateur" in r.json()["detail"]
    r = client.post("/api/admin/usage/blocages", json={"type": "ip", "ip": "203.0.113.40", "user_id": admin_id,
                                                      "tous_comptes": False}, headers=admin)
    assert r.status_code == 400
    # Son IP actuelle (vue derrière le proxy) ne peut pas être bloquée
    r = client.post("/api/admin/usage/blocages", json={"type": "ip", "ip": "203.0.113.41", "tous_comptes": True},
                    headers={**admin, **_ip("203.0.113.41")})
    assert r.status_code == 400 and "vous-même" in r.json()["detail"]
    # Une IP bloquée pour tous ne bloque jamais le super-administrateur
    assert client.post("/api/admin/usage/blocages", json={"type": "ip", "ip": "203.0.113.42"},
                       headers=admin).status_code == 200
    assert _connexion(client, _email(client, admin_id), "203.0.113.42").status_code == 200
    assert client.portal.call(lambda: db.blocages.count_documents({"type": "compte"})) == 0


def test_journal_des_actions_et_contact(client, make_user):
    a, _ = make_user()[:2]
    _, admin = _admin(client, make_user)
    client.post("/api/admin/usage/blocages", json={"type": "compte", "user_id": a, "motif": "Essai"}, headers=admin)
    client.post("/api/admin/usage/autoriser", json={"type": "compte", "user_id": a}, headers=admin)
    actions = client.get("/api/admin/usage/journal", headers=admin).json()["actions"]
    noms = [x["action"] for x in actions]
    assert "Compte bloqué" in noms and "Blocage levé (accès autorisé)" in noms
    assert all(x["par"] and x["date"] for x in actions)
    # Contact de la page de blocage : réglé par le super-admin, lisible sans connexion
    assert client.put("/api/admin/usage/contact", json={"email": "pas-un-email"}, headers=admin).status_code == 400
    r = client.put("/api/admin/usage/contact", json={"email": "contact@example.com", "whatsapp": "+226 70 00 00 00"},
                   headers=admin)
    assert r.status_code == 200
    assert client.get("/api/acces-suspendu/contact").json() == {"email": "contact@example.com",
                                                                "whatsapp": "+226 70 00 00 00"}
    client.portal.call(lambda: db.settings.delete_many({"id": blocages_acces.ID_CONTACT}))
