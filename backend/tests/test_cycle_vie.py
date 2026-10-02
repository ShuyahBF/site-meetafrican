"""Cycle de vie du non-renouvellement (C) : avertissements J+103 / J+110 / J+112
envoyés une seule fois, suspension J+110 (accès limité au renouvellement, levée
au paiement), archive chiffrée vérifiée puis suppression du compte à J+113,
échec de vérification sans suppression, exclusions, rattrapage à la mise en
service, simulation, interrupteur, effacement des archives, réouverture."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

import abonnement_grace
import cycle_vie
import parametres_plateforme
from config import get_settings
from db import db

PHRASE = "phrase de sauvegarde automatique 2026"
MDP = "motdepasse123"
REEL = datetime.now(timezone.utc)


@pytest.fixture
def cycle(client, tmp_path, monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "beauthentik_sauvegardes_dossier_local", str(tmp_path / "r2"))
    monkeypatch.setattr(s, "sauvegarde_auto_phrase", PHRASE)
    envois = []

    async def envoyer(user, texte):
        envois.append({"phone": user.get("phone"), "texte": texte})
        return {"ok": True, "canal": "whatsapp", "erreur": None}

    monkeypatch.setattr(cycle_vie.envoi_messages, "envoyer", envoyer)
    decalage = {"jours": 0}
    monkeypatch.setattr(abonnement_grace, "maintenant", lambda: REEL + timedelta(days=decalage["jours"]))

    def nettoyer():
        async def _n():
            await db.parametres_plateforme.delete_many({})
            await db.cycle_vie_rapports.delete_many({})
        client.portal.call(_n)
        parametres_plateforme.vider_cache()

    nettoyer()
    # Cycle en service depuis longtemps (pas de rattrapage), sauf test dédié
    client.portal.call(lambda: parametres_plateforme.marquer({"cycle_debut_le": (REEL - timedelta(days=400)).isoformat()}))
    yield {"envois": envois, "decalage": decalage, "r2": tmp_path / "r2"}
    nettoyer()


def _membre(client, make_user, jours_depuis_echeance, **champs):
    uid, headers, _ = make_user()
    telephone = f"7{uuid.uuid4().int % 10**7:07d}"
    client.portal.call(lambda: db.users.update_one({"id": uid}, {"$set": {"phone": telephone, **champs}}))
    echeance = REEL - timedelta(days=jours_depuis_echeance)
    client.portal.call(lambda: db.subscriptions.insert_one({
        "id": str(uuid.uuid4()), "user_id": uid, "plan_id": "p", "status": "active",
        "expires_at": echeance.isoformat(), "created_at": (echeance - timedelta(days=30)).isoformat()}))
    return uid, headers, telephone


def _executer(client, simulation=None):
    return client.portal.call(lambda: cycle_vie.executer_quotidien("test", simulation=simulation))


def _actions(rapport, uid):
    return [a["action"] for a in rapport["actions"] if a["user_id"] == uid]


def _user(client, uid):
    return client.portal.call(lambda: db.users.find_one({"id": uid}, {"_id": 0}))


def test_parcours_complet_jusqu_a_la_suppression(client, make_user, cycle):
    uid, headers, tel = _membre(client, make_user, 103)
    # Quelques données du membre
    client.portal.call(lambda: db.support_tickets.insert_one({"id": "t-" + uid, "user_id": uid, "sujet": "x"}))

    # Simulation : rien n'est fait, rien n'est envoyé
    rapport = _executer(client, simulation=True)
    assert _actions(rapport, uid) == ["avertissement_103"] and rapport["simulation"]
    assert not cycle["envois"] and not _user(client, uid).get("cycle_vie")

    # J+103 : avertissement, une seule fois
    assert _actions(_executer(client), uid) == ["avertissement_103"]
    assert _actions(_executer(client), uid) == []
    # (les administrateurs reçoivent aussi le rapport : seuls les envois au membre sont comptés)
    au_membre = lambda: [e for e in cycle["envois"] if e["phone"] == tel]  # noqa: E731
    assert len(au_membre()) == 1
    assert "sera suspendu le" in au_membre()[0]["texte"]

    # J+110 : suspension + avertissement
    cycle["decalage"]["jours"] = 7
    assert _actions(_executer(client), uid) == ["suspension"]
    u = _user(client, uid)
    assert u["is_active"] is False and u["statut_cycle"] == cycle_vie.STATUT_SUSPENDU
    assert "est suspendu" in au_membre()[-1]["texte"]
    # Accès limité aux routes de renouvellement
    r = client.get("/api/me/settings", headers=headers)
    assert r.status_code == 403 and r.json()["detail"].startswith("Compte suspendu")
    etat = client.get("/api/abonnement/etat", headers=headers).json()
    assert etat["suspendu"] is True and etat["cycle_vie"]["suppression_le"]
    assert client.get("/api/subscriptions/me", headers=headers).status_code == 200
    # Le membre suspendu peut se connecter (pour renouveler)
    email = u["email"]
    assert client.post("/api/auth/login", json={"identifier": email, "password": MDP}).status_code == 200

    # J+112 : veille de la suppression
    cycle["decalage"]["jours"] = 9
    assert _actions(_executer(client), uid) == ["avertissement_112"]
    assert "supprimé demain" in au_membre()[-1]["texte"]
    assert len(au_membre()) == 3

    # J+113 : archive vérifiée sur R2 puis suppression du compte
    cycle["decalage"]["jours"] = 10
    rapport = _executer(client)
    assert _actions(rapport, uid) == ["archive_et_suppression"], rapport
    assert _user(client, uid) is None
    assert client.portal.call(lambda: db.support_tickets.find_one({"user_id": uid})) is None
    assert client.portal.call(lambda: db.subscriptions.find_one({"user_id": uid})) is None
    fiche = client.portal.call(lambda: db.archives_membres.find_one({"user_id": uid}, {"_id": 0}))
    assert fiche["statut"] == "ARCHIVÉ" and fiche["comptes"]["users"] == 1 and fiche["comptes"]["support_tickets"] == 1
    assert "archives-locataires/" + uid in fiche["cle_r2"]
    assert (cycle["r2"] / fiche["cle_r2"]).exists()
    assert datetime.fromisoformat(fiche["expire_le"]) > REEL + timedelta(days=360)
    # L'ancien jeton ne donne plus accès ; il peut se réinscrire (repart de zéro)
    assert client.get("/api/auth/me", headers=headers).status_code == 401
    assert client.post("/api/auth/login", json={"identifier": email, "password": MDP}).status_code == 401
    # Rapport visible par l'administrateur
    aid, admin, _ = make_user()
    client.portal.call(lambda: db.users.update_one({"id": aid}, {"$set": {"role": "admin"}}))
    etat = client.get("/api/plateforme/cycle-vie", headers=admin).json()
    assert any(a["user_id"] == uid for a in etat["archives"]) and etat["rapports"]

    # Réouverture manuelle par l'administrateur (mot de passe exigé)
    url = f"/api/plateforme/cycle-vie/archives/{fiche['id']}/rouvrir"
    assert client.post(url, json={"mot_de_passe": "faux"}, headers=admin).status_code == 403
    r = client.post(url, json={"mot_de_passe": MDP, "frais_encaisses": True}, headers=admin)
    assert r.status_code == 200, r.text
    u = _user(client, uid)
    assert u["is_active"] is True and not u.get("statut_cycle") and u["cycle_repart_le"]
    assert client.post("/api/auth/login", json={"identifier": email, "password": MDP}).status_code == 200
    # Le cycle repart de la réouverture : pas de nouvelle suspension immédiate
    assert _actions(_executer(client), uid) == []
    assert client.post(url, json={"mot_de_passe": MDP}, headers=admin).status_code == 400


def test_paiement_leve_la_suspension(client, make_user, cycle):
    uid, headers, _ = _membre(client, make_user, 110)
    assert _actions(_executer(client), uid) == ["suspension"]
    assert client.get("/api/me/settings", headers=headers).status_code == 403
    # Nouveau paiement : nouvelle échéance
    client.portal.call(lambda: db.subscriptions.insert_one({
        "id": str(uuid.uuid4()), "user_id": uid, "plan_id": "p", "status": "active",
        "expires_at": (REEL + timedelta(days=60)).isoformat(), "created_at": (REEL + timedelta(days=1)).isoformat()}))
    assert client.get("/api/me/settings", headers=headers).status_code == 200
    u = _user(client, uid)
    assert u["is_active"] is True and u["statut_cycle"] is None


def test_verification_echouee_rien_n_est_supprime(client, make_user, cycle, monkeypatch):
    uid, _, _ = _membre(client, make_user, 113)
    _executer(client)  # suspension
    cycle["decalage"]["jours"] = 3
    alertes = []

    async def alerter(texte, **_):
        alertes.append(texte)
        return 0

    monkeypatch.setattr(cycle_vie.envoi_messages, "alerter_administrateurs", alerter)
    monkeypatch.setattr(cycle_vie, "_lire_archive", lambda chemin, phrase: ({"collections": []}, {}))
    rapport = _executer(client)
    assert any(e["user_id"] == uid for e in rapport["erreurs"])
    assert _user(client, uid) is not None
    assert client.portal.call(lambda: db.archives_membres.find_one({"user_id": uid})) is None
    assert any("ÉCHOUÉE" in a for a in alertes)


def test_sans_sauvegarde_configuree_rien_n_est_supprime(client, make_user, cycle, monkeypatch):
    uid, _, _ = _membre(client, make_user, 113)
    _executer(client)
    cycle["decalage"]["jours"] = 3
    monkeypatch.setattr(get_settings(), "sauvegarde_auto_phrase", None)
    rapport = _executer(client)
    assert any("SAUVEGARDE_AUTO_PHRASE" in e["erreur"] for e in rapport["erreurs"] if e["user_id"] == uid)
    assert _user(client, uid) is not None


def test_exclusions(client, make_user, cycle):
    admin_id, _, _ = _membre(client, make_user, 150, role="admin")
    mod_id, _, _ = _membre(client, make_user, 150, role="moderator")
    test_id, _, _ = _membre(client, make_user, 150, is_test_data=True)
    desactive_id, _, _ = _membre(client, make_user, 150, is_active=False)
    rapport = _executer(client)
    for uid in (admin_id, mod_id, test_id, desactive_id):
        assert _actions(rapport, uid) == []
        assert not _user(client, uid).get("cycle_vie")
    # Base partagée entre les fichiers de test : le compte « de test » est supprimé
    # (la purge des données de test de test_features.py en compte le nombre exact)
    client.portal.call(lambda: db.users.delete_one({"id": test_id}))


def test_rattrapage_a_la_mise_en_service(client, make_user, cycle):
    client.portal.call(lambda: db.parametres_plateforme.update_one(
        {"_id": parametres_plateforme.ID_DOC}, {"$unset": {"cycle_debut_le": ""}}))
    parametres_plateforme.vider_cache()
    uid, _, _ = _membre(client, make_user, 300)
    # Échéance très ancienne : d'abord l'avertissement J+103, pas de suspension ni de suppression
    assert _actions(_executer(client), uid) == ["avertissement_103"]
    assert _user(client, uid)["is_active"] is True
    cycle["decalage"]["jours"] = 6
    assert _actions(_executer(client), uid) == []
    cycle["decalage"]["jours"] = 7
    assert _actions(_executer(client), uid) == ["suspension"]


def test_interrupteur_et_droits(client, make_user, cycle):
    uid, membre, _ = _membre(client, make_user, 103)
    aid, admin, _ = make_user()
    client.portal.call(lambda: db.users.update_one({"id": aid}, {"$set": {"role": "admin"}}))
    client.put("/api/plateforme/parametres/abonnements-sessions", json={"cycle_actif": False}, headers=admin)
    assert _executer(client)["statut"] == "DESACTIVE"
    assert not cycle["envois"]
    # Simulation lancée par l'administrateur : rapport immédiat
    r = client.post("/api/plateforme/cycle-vie/executer", json={"simulation": True}, headers=admin)
    assert r.status_code == 200 and "avertissement_103" in _actions(r.json(), uid)
    assert client.post("/api/plateforme/cycle-vie/executer", json={"simulation": True}, headers=membre).status_code == 403
    assert client.get("/api/plateforme/cycle-vie", headers=membre).status_code == 403


def test_effacement_des_archives_apres_conservation(client, make_user, cycle):
    uid, _, _ = _membre(client, make_user, 113)
    _executer(client)
    cycle["decalage"]["jours"] = 3
    _executer(client)
    fiche = client.portal.call(lambda: db.archives_membres.find_one({"user_id": uid}, {"_id": 0}))
    assert fiche and (cycle["r2"] / fiche["cle_r2"]).exists()
    passe = (REEL - timedelta(days=1)).isoformat()
    client.portal.call(lambda: db.archives_membres.update_one({"id": fiche["id"]}, {"$set": {"expire_le": passe}}))
    rapport = _executer(client)
    assert any(a["id"] == fiche["id"] for a in rapport["archives_effacees"])
    assert not (cycle["r2"] / fiche["cle_r2"]).exists()
    assert client.portal.call(lambda: db.archives_membres.find_one({"id": fiche["id"]}))["statut"] == "ARCHIVE_EFFACEE"


def test_archive_de_membre_refusee_par_l_import_complet(client, make_user, cycle):
    """Une archive de membre (partielle) ne doit jamais pouvoir remplacer toute la base."""
    import transfert_donnees
    with pytest.raises(transfert_donnees.ErreurTransfert):
        transfert_donnees._valider_manifest({"application": "beauthentik", "version_format": 1, "partiel": True,
                                             "collections": []}, None)
