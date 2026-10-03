"""Sessions simultanées limitées (B) et déconnexion après inactivité : limite
d'appareils, message de l'appareil fermé, liste et fermeture par le membre et
par l'administrateur, anciens jetons, réglages et contrôle serveur de l'inactivité."""
import jwt
import pytest

import inactivite
import parametres_plateforme
import sessions_comptes
from config import get_settings
from db import db

MDP = "motdepasse123"


def _reinitialiser(client):
    client.portal.call(lambda: db.parametres_plateforme.delete_many({}))
    parametres_plateforme.vider_cache()
    sessions_comptes.vider_cache()


@pytest.fixture(autouse=True)
def reglages_propres(client):
    _reinitialiser(client)
    yield
    _reinitialiser(client)


def _email(client, uid):
    return client.portal.call(lambda: db.users.find_one({"id": uid}))["email"]


def _connexion(client, email, ua="Mozilla/5.0 (Linux; Android 14) Chrome/120"):
    r = client.post("/api/auth/login", json={"identifier": email, "password": MDP}, headers={"User-Agent": ua})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _admin(client, make_user):
    uid, headers, _ = make_user()
    client.portal.call(lambda: db.users.update_one({"id": uid}, {"$set": {"role": "admin"}}))
    return uid, headers


def test_jeton_porte_un_identifiant_de_session(client, make_user):
    _, _, token = make_user()
    contenu = jwt.decode(token, get_settings().jwt_secret, algorithms=["HS256"])
    assert contenu.get("sid")
    assert client.portal.call(lambda: db.sessions.find_one({"_id": contenu["sid"]}))


def test_sixieme_connexion_ferme_la_plus_ancienne(client, make_user):
    uid, inscription, _ = make_user()
    email = _email(client, uid)
    # L'inscription a ouvert une session ; 5 connexions de plus = 6 sessions -> la plus ancienne est fermée
    appareils = [_connexion(client, email) for _ in range(5)]
    r = client.get("/api/auth/me", headers=inscription)
    assert r.status_code == 401
    assert r.json()["detail"] == "Session fermée : nombre maximal d'appareils atteint pour ce compte."
    for h in appareils:
        assert client.get("/api/auth/me", headers=h).status_code == 200
    liste = client.get("/api/auth/sessions", headers=appareils[-1]).json()
    assert liste["max"] == 5 and len(liste["sessions"]) == 5
    assert sum(1 for s in liste["sessions"] if s["courante"]) == 1
    assert liste["sessions"][0]["appareil"] == "Chrome sur Android"


def test_limite_reglable_et_bornes(client, make_user):
    _, admin = _admin(client, make_user)
    url = "/api/plateforme/parametres/abonnements-sessions"
    assert client.put(url, json={"sessions_max": 0}, headers=admin).status_code == 400
    assert client.put(url, json={"sessions_max": 21}, headers=admin).status_code == 400
    r = client.put(url, json={"sessions_max": 2}, headers=admin)
    assert r.status_code == 200 and r.json()["sessions_max"] == 2
    uid, premier, _ = make_user()
    email = _email(client, uid)
    deuxieme = _connexion(client, email)
    troisieme = _connexion(client, email)
    assert client.get("/api/auth/me", headers=premier).status_code == 401
    assert client.get("/api/auth/me", headers=deuxieme).status_code == 200
    assert client.get("/api/auth/me", headers=troisieme).status_code == 200
    # Un membre ne peut pas modifier les paramètres
    assert client.put(url, json={"sessions_max": 3}, headers=troisieme).status_code == 403


def test_membre_ferme_une_session_et_deconnexion(client, make_user):
    uid, telephone, _ = make_user()
    ordinateur = _connexion(client, _email(client, uid), ua="Mozilla/5.0 (Windows NT 10.0) Firefox/120")
    sessions = client.get("/api/auth/sessions", headers=ordinateur).json()["sessions"]
    autre = next(s for s in sessions if not s["courante"])
    assert client.delete(f"/api/auth/sessions/{autre['id']}", headers=ordinateur).status_code == 200
    r = client.get("/api/auth/me", headers=telephone)
    assert r.status_code == 401 and "autre appareil" in r.json()["detail"]
    # Session d'un autre compte : introuvable
    _, etranger, _ = make_user()
    courante = next(s for s in sessions if s["courante"])
    assert client.delete(f"/api/auth/sessions/{courante['id']}", headers=etranger).status_code == 404
    # Déconnexion : la session courante est fermée côté serveur
    assert client.post("/api/auth/deconnexion", headers=ordinateur).status_code == 200
    assert client.get("/api/auth/me", headers=ordinateur).status_code == 401


def test_fermer_les_autres_sessions(client, make_user):
    uid, a, _ = make_user()
    email = _email(client, uid)
    b, c = _connexion(client, email), _connexion(client, email)
    assert client.post("/api/auth/sessions/fermer-autres", headers=c).json()["fermees"] == 2
    assert client.get("/api/auth/me", headers=a).status_code == 401
    assert client.get("/api/auth/me", headers=b).status_code == 401
    assert client.get("/api/auth/me", headers=c).status_code == 200


def test_administrateur_voit_et_ferme_les_sessions(client, make_user):
    _, admin = _admin(client, make_user)
    uid, membre, _ = make_user()
    _connexion(client, _email(client, uid))
    comptes = client.get("/api/admin/sessions/comptes", headers=admin).json()["comptes"]
    assert next(c for c in comptes if c["user_id"] == uid)["sessions"] == 2
    sessions = client.get(f"/api/admin/membres/{uid}/sessions", headers=admin).json()["sessions"]
    assert len(sessions) == 2
    r = client.post(f"/api/admin/membres/{uid}/sessions/{sessions[0]['id']}/fermer", headers=admin)
    assert r.status_code == 200
    assert client.post(f"/api/admin/membres/{uid}/sessions/fermer-toutes", headers=admin).json()["fermees"] == 1
    r = client.get("/api/auth/me", headers=membre)
    assert r.status_code == 401 and r.json()["detail"] == "Session fermée par l'administrateur."
    # Réservé à l'administrateur principal (modérateur refusé)
    mid, moderateur, _ = make_user()
    client.portal.call(lambda: db.users.update_one({"id": mid}, {"$set": {"role": "moderator"}}))
    assert client.get("/api/admin/sessions/comptes", headers=moderateur).status_code == 403
    # Journalisé
    assert client.portal.call(lambda: db.activity_log.find_one(
        {"action": "Toutes les sessions d'un membre fermées par l'administrateur"}))


def test_ancien_jeton_sans_sid_reste_valable_et_apparait(client, make_user):
    from auth import create_access_token
    uid, _, _ = make_user()
    ancien = {"Authorization": f"Bearer {create_access_token(uid)}"}
    assert client.get("/api/auth/me", headers=ancien).status_code == 200
    sessions = client.get("/api/auth/sessions", headers=ancien).json()["sessions"]
    assert any(s["id"].startswith("ancien-") and s["courante"] for s in sessions)


def test_reglages_inactivite_bornes(client, make_user):
    _, admin = _admin(client, make_user)
    url = "/api/plateforme/parametres/abonnements-sessions"
    assert client.put(url, json={"inactivite_secondes": 30}, headers=admin).status_code == 400
    assert client.put(url, json={"inactivite_secondes": 86_401}, headers=admin).status_code == 400
    assert client.put(url, json={"inactivite_secondes": 600}, headers=admin).json()["inactivite_secondes"] == 600
    uid, membre, _ = make_user()
    r = client.get("/api/auth/inactivite", headers=membre).json()
    assert r == {"secondes": 600, "avertissement_secondes": 60}
    # Réglage personnel réservé au super-administrateur (lot 45) : 403 pour le membre
    assert client.get("/api/auth/inactivite/reglage", headers=membre).status_code == 403
    assert client.put("/api/auth/inactivite/reglage", json={"secondes": 300}, headers=membre).status_code == 403
    # Le super-administrateur peut seulement réduire sa propre durée
    assert client.put("/api/auth/inactivite/reglage", json={"secondes": 900}, headers=admin).status_code == 400
    assert client.put("/api/auth/inactivite/reglage", json={"secondes": 0}, headers=admin).status_code == 400
    assert client.put("/api/auth/inactivite/reglage", json={"secondes": 300}, headers=admin).json()["effective"] == 300
    assert client.get("/api/auth/inactivite", headers=admin).json()["secondes"] == 300
    # Surcharge de l'administrateur pour ce membre (0 = désactivée pour lui)
    r = client.put(f"/api/admin/membres/{uid}/inactivite", json={"secondes": 0}, headers=admin)
    assert r.status_code == 200 and r.json()["plafond"] == 0 and r.json()["effective"] == 0


def test_inactivite_controle_serveur(client, make_user, monkeypatch):
    _, admin = _admin(client, make_user)
    client.put("/api/plateforme/parametres/abonnements-sessions", json={"inactivite_secondes": 60}, headers=admin)
    _, actif, _ = make_user()
    _, fond, _ = make_user()
    base = inactivite._maintenant()
    decalage = {"s": 0}
    monkeypatch.setattr(inactivite, "_maintenant", lambda: base + decalage["s"])
    for h in (actif, fond):
        assert client.get("/api/auth/me", headers=h).status_code == 200
    # +100 s : vraie activité pour l'un, requête de fond pour l'autre (non comptée)
    decalage["s"] = 100
    assert client.get("/api/auth/me", headers=actif).status_code == 200
    assert client.get("/api/auth/me", headers={**fond, "X-BA-Fond": "1"}).status_code == 200
    # +150 s : 50 s depuis la dernière activité du premier ; 150 s pour le second (> 60 + 60 de marge)
    decalage["s"] = 150
    assert client.get("/api/auth/me", headers=actif).status_code == 200
    r = client.get("/api/auth/me", headers=fond)
    assert r.status_code == 401 and r.json()["detail"] == inactivite.MESSAGE_INACTIVITE
    # La session reste fermée même si l'activité reprend
    assert client.get("/api/auth/me", headers=fond).status_code == 401
    # La session de l'administrateur, inactive depuis 150 s, est elle aussi fermée
    assert client.get("/api/auth/me", headers=admin).status_code == 401
    # Désactivée (0) : plus de contrôle
    client.portal.call(lambda: parametres_plateforme.modifier({"inactivite_secondes": 0}, "test"))
    decalage["s"] = 5000
    assert client.get("/api/auth/me", headers=actif).status_code == 200


def test_chat_temps_reel_refuse_une_session_fermee(client, make_user):
    from starlette.websockets import WebSocketDisconnect
    uid, _, token = make_user()
    autre = _connexion(client, _email(client, uid))
    client.post("/api/auth/sessions/fermer-autres", headers=autre)
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect(f"/api/ws/conversations/inconnue?token={token}") as ws:
            ws.receive_json()
    assert exc.value.code == 4401
