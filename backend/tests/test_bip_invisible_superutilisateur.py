"""Lot 45 : son des nouveaux messages (préférences), Mode Invisible (14 jours,
bonus payant ou formule l'autorisant, prix réglé par le super-administrateur),
sauvegardes et « Déconnexion si inactivité » réservées au super-utilisateur."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

import mode_invisible
import parametres_plateforme
from db import db


@pytest.fixture(autouse=True)
def reglages_propres(client):
    """Chaque test repart sans prix de bonus ni paramètres de plateforme. Les comptes
    et formules créés ici sont supprimés ensuite, pour ne pas fausser les autres
    tests (recherche limitée à 20 résultats, liste des formules)."""
    client.portal.call(lambda: db.settings.delete_many({"id": mode_invisible.ID_REGLAGE}))
    client.portal.call(lambda: db.parametres_plateforme.delete_many({}))
    parametres_plateforme.vider_cache()
    comptes_avant = client.portal.call(lambda: db.users.distinct("id"))
    formules_avant = client.portal.call(lambda: db.subscription_plans.distinct("id"))
    yield
    client.portal.call(lambda: db.settings.delete_many({"id": mode_invisible.ID_REGLAGE}))
    client.portal.call(lambda: db.parametres_plateforme.delete_many({}))
    parametres_plateforme.vider_cache()
    client.portal.call(lambda: db.users.delete_many({"id": {"$nin": comptes_avant}}))
    client.portal.call(lambda: db.subscription_plans.delete_many({"id": {"$nin": formules_avant}}))


def _role(client, uid, role):
    client.portal.call(lambda: db.users.update_one({"id": uid}, {"$set": {"role": role}}))


def _admin(client, make_user):
    uid, headers, _ = make_user()
    _role(client, uid, "admin")
    return headers


def _moderateur(client, make_user):
    uid, headers, _ = make_user()
    _role(client, uid, "moderator")
    return headers


def _crediter(client, uid, montant):
    client.portal.call(lambda: db.users.update_one({"id": uid}, {"$set": {"wallet_balance_xof": montant}}))


def _abonner(client, uid, plan_id):
    """Abonnement actif pour 30 jours sur la formule donnée."""
    maintenant = datetime.now(timezone.utc)
    sub = {"id": str(uuid.uuid4()), "user_id": uid, "plan_id": plan_id, "status": "active",
           "started_at": maintenant.isoformat(), "expires_at": (maintenant + timedelta(days=30)).isoformat(),
           "created_at": maintenant.isoformat()}
    client.portal.call(lambda: db.subscriptions.insert_one(dict(sub)))


def _formule(client, headers, autorise):
    plan = {"code": f"f-{uuid.uuid4().hex[:6]}", "name": "Formule test", "duration_days": 30, "price_xof": 5000,
            "autorise_mode_invisible": autorise}
    r = client.post("/api/admin/subscription-plans", json=plan, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


# ---------------------------------------------------------------------------
# 1. Son des nouveaux messages
# ---------------------------------------------------------------------------
def test_preferences_son_enregistrees_et_relues(client, make_user):
    _, membre, _ = make_user()
    defaut = client.get("/api/me/settings", headers=membre).json()
    assert defaut["son_messages"] is True and defaut["son_volume"] == 70 and defaut["son_type"] == "carillon"
    assert set(defaut["sons_disponibles"]) == {"carillon", "goutte", "bip"}
    r = client.put("/api/me/settings", json={"son_messages": False, "son_volume": 35, "son_type": "goutte"},
                   headers=membre)
    assert r.status_code == 200
    relu = client.get("/api/me/settings", headers=membre).json()
    assert relu["son_messages"] is False and relu["son_volume"] == 35 and relu["son_type"] == "goutte"
    # Valeurs hors bornes refusées
    assert client.put("/api/me/settings", json={"son_volume": 101}, headers=membre).status_code == 422
    assert client.put("/api/me/settings", json={"son_type": "sirene"}, headers=membre).status_code == 422


# ---------------------------------------------------------------------------
# 2. Mode Invisible
# ---------------------------------------------------------------------------
def test_mode_invisible_refuse_sans_droit(client, make_user):
    _, membre, _ = make_user()
    r = client.put("/api/me/settings", json={"invisible_mode": True}, headers=membre)
    assert r.status_code == 403 and "bonus" in r.json()["detail"]
    etat = client.get("/api/me/mode-invisible", headers=membre).json()
    assert etat["actif"] is False and etat["formule_autorise"] is False
    # Sans prix réglé : achat indisponible, message clair
    assert etat["achat_disponible"] is False and etat["prix_bonus_xof"] is None
    r = client.post("/api/me/mode-invisible/bonus", headers=membre)
    assert r.status_code == 400 and "prix" in r.json()["detail"]


def test_prix_du_bonus_reserve_au_super_administrateur(client, make_user):
    admin = _admin(client, make_user)
    _, membre, _ = make_user()
    moderateur = _moderateur(client, make_user)
    for h in (membre, moderateur):
        assert client.get("/api/admin/mode-invisible", headers=h).status_code == 403
        assert client.put("/api/admin/mode-invisible", json={"prix_bonus_xof": 100}, headers=h).status_code == 403
    assert client.put("/api/admin/mode-invisible", json={"prix_bonus_xof": 0}, headers=admin).status_code == 400
    r = client.put("/api/admin/mode-invisible", json={"prix_bonus_xof": 1500}, headers=admin)
    assert r.status_code == 200 and r.json()["prix_bonus_xof"] == 1500 and r.json()["duree_jours"] == 14


def test_mode_invisible_avec_bonus_paye(client, make_user):
    admin = _admin(client, make_user)
    client.put("/api/admin/mode-invisible", json={"prix_bonus_xof": 1500}, headers=admin)
    uid, membre, _ = make_user()
    # Solde insuffisant : refusé, rien n'est débité
    _crediter(client, uid, 1000)
    r = client.post("/api/me/mode-invisible/bonus", headers=membre)
    assert r.status_code == 400 and "insuffisant" in r.json()["detail"]
    # Solde suffisant : débit, mode activé pour 14 jours, ligne au relevé du portefeuille
    _crediter(client, uid, 2000)
    r = client.post("/api/me/mode-invisible/bonus", headers=membre)
    assert r.status_code == 200, r.text
    assert r.json()["invisible_mode"] is True
    fin = datetime.fromisoformat(r.json()["invisible_mode_expire_le"])
    assert timedelta(days=13, hours=23) < fin - datetime.now(timezone.utc) <= timedelta(days=14)
    portefeuille = client.get("/api/me/wallet", headers=membre).json()
    assert portefeuille["balance_xof"] == 500
    assert portefeuille["history"][0]["kind"] == "bonus_mode_invisible"
    # Second achat pendant le bonus : refusé
    assert client.post("/api/me/mode-invisible/bonus", headers=membre).status_code == 400
    # Désactiver puis réactiver pendant le bonus : la fin reste celle du bonus
    client.put("/api/me/settings", json={"invisible_mode": False}, headers=membre)
    r = client.put("/api/me/settings", json={"invisible_mode": True}, headers=membre)
    assert r.status_code == 200 and r.json()["invisible_mode_expire_le"] == fin.isoformat()


def test_mode_invisible_avec_formule_l_autorisant(client, make_user):
    admin = _admin(client, make_user)
    avec = _formule(client, admin, True)
    sans = _formule(client, admin, False)
    # Case enregistrée sur la formule
    plans = {p["id"]: p for p in client.get("/api/admin/subscription-plans", headers=admin).json()}
    assert plans[avec["id"]]["autorise_mode_invisible"] is True
    assert plans[sans["id"]]["autorise_mode_invisible"] is False

    uid_sans, membre_sans, _ = make_user()
    _abonner(client, uid_sans, sans["id"])
    assert client.put("/api/me/settings", json={"invisible_mode": True}, headers=membre_sans).status_code == 403

    uid, membre, _ = make_user()
    _abonner(client, uid, avec["id"])
    assert client.get("/api/me/mode-invisible", headers=membre).json()["formule_autorise"] is True
    r = client.put("/api/me/settings", json={"invisible_mode": True}, headers=membre)
    assert r.status_code == 200 and r.json()["invisible_mode"] is True
    assert r.json()["mode_invisible"]["expire_le"]


def test_case_de_formule_modifiable_par_le_super_administrateur_seulement(client, make_user):
    admin = _admin(client, make_user)
    moderateur = _moderateur(client, make_user)
    plan = _formule(client, admin, True)
    # Un modérateur modifie la formule : la case est conservée telle quelle
    r = client.put(f"/api/admin/subscription-plans/{plan['id']}",
                   json={**plan, "name": "Renommée", "autorise_mode_invisible": False}, headers=moderateur)
    assert r.status_code == 200 and r.json()["autorise_mode_invisible"] is True and r.json()["name"] == "Renommée"
    # Le super-administrateur peut la décocher
    r = client.put(f"/api/admin/subscription-plans/{plan['id']}", json={**plan, "autorise_mode_invisible": False},
                   headers=admin)
    assert r.json()["autorise_mode_invisible"] is False
    # Création par un modérateur : jamais cochée
    r = client.post("/api/admin/subscription-plans", json={"code": "m", "name": "M", "duration_days": 7,
                                                            "price_xof": 1, "autorise_mode_invisible": True},
                    headers=moderateur)
    assert r.json()["autorise_mode_invisible"] is False


def test_mode_invisible_expire_apres_14_jours(client, make_user, monkeypatch):
    admin = _admin(client, make_user)
    client.put("/api/admin/mode-invisible", json={"prix_bonus_xof": 100}, headers=admin)
    uid, membre, _ = make_user()
    _crediter(client, uid, 100)
    depart = datetime.now(timezone.utc)
    monkeypatch.setattr(mode_invisible, "maintenant", lambda: depart)
    assert client.post("/api/me/mode-invisible/bonus", headers=membre).status_code == 200
    # 13 jours plus tard : toujours actif
    monkeypatch.setattr(mode_invisible, "maintenant", lambda: depart + timedelta(days=13))
    assert client.get("/api/me/settings", headers=membre).json()["invisible_mode"] is True
    # 14 jours plus tard : coupé automatiquement à la lecture, et en base
    monkeypatch.setattr(mode_invisible, "maintenant", lambda: depart + timedelta(days=14, seconds=1))
    r = client.get("/api/me/settings", headers=membre).json()
    assert r["invisible_mode"] is False and r["mode_invisible"]["bonus_actif"] is False
    doc = client.portal.call(lambda: db.users.find_one({"id": uid}))
    assert doc["settings"]["invisible_mode"] is False
    # Plus de droit : réactivation refusée
    assert client.put("/api/me/settings", json={"invisible_mode": True}, headers=membre).status_code == 403


# ---------------------------------------------------------------------------
# 3. Sauvegardes et inactivité : super-utilisateur seulement
# ---------------------------------------------------------------------------
def test_sauvegardes_et_inactivite_reserves_au_super_utilisateur(client, make_user):
    admin = _admin(client, make_user)
    moderateur = _moderateur(client, make_user)
    _, membre, _ = make_user()
    urls_lecture = ["/api/sauvegarde-auto/derniere", "/api/plateforme/sauvegardes-auto",
                    "/api/plateforme/parametres/abonnements-sessions", "/api/auth/inactivite/reglage"]
    for h in (moderateur, membre):
        for url in urls_lecture:
            assert client.get(url, headers=h).status_code == 403, url
        assert client.post("/api/plateforme/sauvegardes-auto/lancer", headers=h).status_code == 403
        assert client.put("/api/plateforme/parametres/abonnements-sessions", json={"inactivite_secondes": 600},
                          headers=h).status_code == 403
        assert client.put("/api/auth/inactivite/reglage", json={"secondes": 120}, headers=h).status_code == 403
    for url in ("/api/sauvegarde-auto/derniere", "/api/plateforme/parametres/abonnements-sessions",
                "/api/auth/inactivite/reglage"):
        assert client.get(url, headers=admin).status_code == 200, url
    r = client.put("/api/plateforme/parametres/abonnements-sessions", json={"inactivite_secondes": 600}, headers=admin)
    assert r.status_code == 200 and r.json()["inactivite_secondes"] == 600
    # La déconnexion automatique continue de s'appliquer aux membres (durée lisible pour l'appliquer)
    assert client.get("/api/auth/inactivite", headers=membre).json()["secondes"] == 600
