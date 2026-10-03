"""Sauvegarde générale automatique (E) et date de la dernière sauvegarde (D) :
route protégée par jeton, désactivation avec alerte, idempotence sur la journée,
fichier .baexport chiffré lisible, rétention 7/4/12, restauration (Remplacer).
R2 est remplacé par un dossier local (BEAUTHENTIK_SAUVEGARDES_DOSSIER_LOCAL)."""
import time
from datetime import datetime, timedelta, timezone

import pytest

import chiffrement_flux
import sauvegarde_auto
import transfert_donnees
from config import get_settings
from db import db

PHRASE = "phrase de sauvegarde automatique 2026"
JETON = "jeton-cron-de-test-0123456789"
MDP = "motdepasse123"


@pytest.fixture
def configuree(client, tmp_path, monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "beauthentik_sauvegardes_dossier_local", str(tmp_path / "r2"))
    monkeypatch.setattr(s, "sauvegarde_auto_phrase", PHRASE)
    monkeypatch.setattr(s, "sauvegarde_auto_jeton", JETON)
    client.portal.call(lambda: db.sauvegardes_auto.delete_many({}))
    yield tmp_path / "r2"
    client.portal.call(lambda: db.sauvegardes_auto.delete_many({}))


def _admin(client, make_user):
    uid, headers, _ = make_user()
    client.portal.call(lambda: db.users.update_one({"id": uid}, {"$set": {"role": "admin"}}))
    return headers


def _attendre(client, condition, secondes=30):
    fin = time.time() + secondes
    while time.time() < fin:
        valeur = client.portal.call(condition)
        if valeur:
            return valeur
        time.sleep(0.2)
    raise AssertionError("délai dépassé")


def test_route_protegee_par_jeton(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "sauvegarde_auto_jeton", None)
    assert client.post("/api/sauvegarde-auto/declencher").status_code == 503
    monkeypatch.setattr(get_settings(), "sauvegarde_auto_jeton", JETON)
    assert client.post("/api/sauvegarde-auto/declencher").status_code == 403
    assert client.post("/api/sauvegarde-auto/declencher", headers={"X-Sauvegarde-Jeton": "faux"}).status_code == 403


def test_desactivee_sans_phrase_avec_alerte(client, make_user, monkeypatch, tmp_path):
    monkeypatch.setattr(get_settings(), "sauvegarde_auto_phrase", None)
    monkeypatch.setattr(get_settings(), "beauthentik_sauvegardes_dossier_local", str(tmp_path))
    rapport = client.portal.call(sauvegarde_auto.executer)
    assert rapport["statut"] == "DESACTIVEE"
    etat = client.get("/api/plateforme/sauvegardes-auto", headers=_admin(client, make_user)).json()
    assert etat["active"] is False and "SAUVEGARDE_AUTO_PHRASE" in etat["alerte"]
    monkeypatch.setattr(get_settings(), "sauvegarde_auto_phrase", "trop courte")
    assert "trop courte" in sauvegarde_auto.motif_desactivation()


def test_sauvegarde_par_le_cron_puis_idempotence(client, make_user, configuree):
    _, membre, _ = make_user()
    admin = _admin(client, make_user)
    assert client.get("/api/sauvegarde-auto/derniere", headers=admin).json() == {"date": None}
    # Lot 45 : la date de sauvegarde n'est plus visible des membres
    assert client.get("/api/sauvegarde-auto/derniere", headers=membre).status_code == 403
    r = client.post("/api/sauvegarde-auto/declencher", headers={"X-Sauvegarde-Jeton": JETON})
    assert r.status_code == 202
    ligne = _attendre(client, lambda: db.sauvegardes_auto.find_one({"statut": {"$in": ["REUSSIE", "ECHEC"]}}))
    assert ligne["statut"] == "REUSSIE", ligne
    fichiers = list((configuree / "sauvegardes-beauthentik" / "generales").glob("*.baexport"))
    assert len(fichiers) == 1
    # Fichier chiffré au format de l'export manuel, lisible avec la phrase
    lecteur = chiffrement_flux.LecteurChiffre(str(fichiers[0]), PHRASE, transfert_donnees._cle_signature())
    assert lecteur.signature_valide
    lecteur.close()
    # Même journée : pas de seconde sauvegarde
    assert client.portal.call(sauvegarde_auto.executer)["statut"] == "DEJA_FAITE_OU_EN_COURS"
    assert len(list((configuree / "sauvegardes-beauthentik" / "generales").glob("*.baexport"))) == 1
    # D : date visible par le super-administrateur seulement
    assert client.get("/api/sauvegarde-auto/derniere", headers=admin).json()["date"] == ligne["fin"]
    # Administration : pas d'alerte, liste des sauvegardes R2
    etat = client.get("/api/plateforme/sauvegardes-auto", headers=_admin(client, make_user)).json()
    assert etat["active"] and etat["alerte"] is None and len(etat["sauvegardes"]) == 1
    assert client.get("/api/plateforme/sauvegardes-auto", headers=membre).status_code == 403


def test_alerte_si_plus_de_26_heures(client, make_user, configuree):
    vieille = (datetime.now(timezone.utc) - timedelta(hours=27)).isoformat()
    client.portal.call(lambda: db.sauvegardes_auto.insert_one(
        {"_id": "jour:2000-01-01", "jour": "2000-01-01", "statut": "REUSSIE", "fin": vieille}))
    etat = client.get("/api/plateforme/sauvegardes-auto", headers=_admin(client, make_user)).json()
    assert "26 h" in etat["alerte"]


def test_echec_alerte_les_administrateurs(client, configuree, monkeypatch):
    alertes = []

    async def alerter(texte):
        alertes.append(texte)
        return 1

    async def panne(*a, **k):
        raise RuntimeError("disque plein")

    monkeypatch.setattr(sauvegarde_auto.envoi_messages, "alerter_administrateurs", alerter)
    monkeypatch.setattr(transfert_donnees, "ecrire_export", panne)
    rapport = client.portal.call(sauvegarde_auto.executer)
    assert rapport["statut"] == "ECHEC" and alertes and "ÉCHEC" in alertes[0]
    # Nouvel essai possible le même jour après un échec
    monkeypatch.undo()


def test_retention_7_4_12():
    debut = datetime(2026, 10, 2, 2, 0, tzinfo=timezone.utc)
    objets = [{"cle": f"p/generales/beauthentik_{(debut - timedelta(days=i)).strftime('%Y%m%d-%H%M%S')}.baexport",
               "date": (debut - timedelta(days=i)).isoformat()} for i in range(400)]
    garder = sauvegarde_auto.a_conserver(objets)
    jours = sorted((sauvegarde_auto._date_objet({"cle": c, "date": ""}) for c in garder), reverse=True)
    # 7 derniers jours conservés
    assert jours[:7] == [debut - timedelta(days=i) for i in range(7)]
    # Au plus 7 + 4 + 12 sauvegardes, et une par mois sur les 12 derniers mois
    assert len(garder) <= 23
    assert len({(d.year, d.month) for d in jours}) == 12
    assert min(jours) > debut - timedelta(days=366)


def test_restauration_depuis_r2(client, make_user, configuree):
    admin = _admin(client, make_user)
    rapport = client.portal.call(sauvegarde_auto.executer)
    assert rapport["statut"] == "REUSSIE", rapport
    cle = rapport["cle"]
    url = "/api/plateforme/sauvegardes-auto/restaurer"
    assert client.post(url, json={"cle": cle, "mot_de_passe": MDP, "confirmation": "non"}, headers=admin).status_code == 400
    assert client.post(url, json={"cle": cle, "mot_de_passe": "faux", "confirmation": "REMPLACER"},
                       headers=admin).status_code == 403
    assert client.post(url, json={"cle": "../autre", "mot_de_passe": MDP, "confirmation": "REMPLACER"},
                       headers=admin).status_code == 400
    r = client.post(url, json={"cle": cle, "mot_de_passe": MDP, "confirmation": "REMPLACER"}, headers=admin)
    assert r.status_code == 202, r.text
    tache = r.json()
    for _ in range(150):
        etat = client.get(f"/api/plateforme/transfert/taches/{tache['id']}").json()
        if etat["statut"] != "EN_COURS":
            break
        time.sleep(0.2)
    assert etat["statut"] == "TERMINE", etat
    assert etat["rapport"]["conforme"], etat["rapport"]
