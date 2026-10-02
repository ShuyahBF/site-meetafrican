"""Envoi des e-mails de la plateforme (envoi_email.py) : forme exacte des appels aux
4 fournisseurs (httpx simulé, aucun appel réseau), remontée des erreurs, clé jamais
renvoyée ni stockée en clair, repli sur les variables d'environnement, compatibilité
des anciens réglages SMTP, écran réservé à l'administrateur principal, essai,
journal, et e-mails EN PLUS de WhatsApp / SMS (alertes, avertissements du cycle de vie)."""
import json
import uuid
from datetime import datetime, timedelta, timezone

import httpx
import pytest

import abonnement_grace
import cycle_vie
import envoi_email
import envoi_messages
import parametres_plateforme
from config import get_settings
from db import db

CLE = "cle_test"
VARIABLES_REPLI = ("resend_api_key", "resend_expediteur", "plateforme_smtp_hote", "smtp_host", "brevo_api_key",
                   "zeptomail_api_key", "zeptomail_hote", "email_expediteur")


@pytest.fixture
def requetes(client, monkeypatch):
    """Transport httpx simulé : note chaque requête et répond selon `reponse`."""
    notees: list[httpx.Request] = []
    etat = {"reponse": lambda req: httpx.Response(200 if "resend" in str(req.url) else 201, json={"id": "x"})}

    def gerer(req: httpx.Request) -> httpx.Response:
        notees.append(req)
        return etat["reponse"](req)

    monkeypatch.setattr(envoi_email, "_transport", httpx.MockTransport(gerer))
    for nom in VARIABLES_REPLI:  # aucune variable d'environnement de repli, sauf test dédié
        monkeypatch.setattr(get_settings(), nom, None)

    def nettoyer():
        async def _n():
            await db.parametres_plateforme.delete_many({"_id": envoi_email.ID_DOC})
            await db.emails_journal.delete_many({})
            await db.email_reglages_journal.delete_many({})
        client.portal.call(_n)

    nettoyer()
    yield {"notees": notees, "etat": etat}
    nettoyer()


def _admin(client, make_user):
    uid, headers, _ = make_user()
    client.portal.call(lambda: db.users.update_one({"id": uid}, {"$set": {"role": "admin"}}))
    return headers


def _regler(client, **reglages):
    return client.portal.call(lambda: envoi_email.modifier(reglages, "admin@example.com"))


def _envoyer(client, dest="dest@example.com"):
    return client.portal.call(lambda: envoi_email.envoyer(dest, "Objet", "Corps du message",
                                                          reponse_a="reponse@example.com"))


# ---------------------------------------------------------------------------
# Forme exacte des appels
# ---------------------------------------------------------------------------
def test_resend_url_entetes_et_json(client, requetes):
    _regler(client, fournisseur="resend", expediteur="envoi@beauthentik.net", nom_expediteur="beAuth<en>tik\nX",
            cle_api=CLE, actif=True)
    assert _envoyer(client) == "resend"
    req = requetes["notees"][-1]
    assert str(req.url) == "https://api.resend.com/emails"
    assert req.headers["authorization"] == f"Bearer {CLE}"
    assert json.loads(req.content) == {"from": "beAuthentik X <envoi@beauthentik.net>", "to": ["dest@example.com"],
                                       "subject": "Objet", "text": "Corps du message",
                                       "reply_to": "reponse@example.com"}


def test_brevo_url_entetes_et_json(client, requetes):
    _regler(client, fournisseur="brevo", expediteur="envoi@beauthentik.net", nom_expediteur="beAuthentik",
            cle_api=CLE, actif=True)
    _envoyer(client)
    req = requetes["notees"][-1]
    assert str(req.url) == "https://api.brevo.com/v3/smtp/email"
    assert req.headers["api-key"] == CLE and req.headers["accept"] == "application/json"
    assert json.loads(req.content) == {"sender": {"name": "beAuthentik", "email": "envoi@beauthentik.net"},
                                       "to": [{"email": "dest@example.com"}], "subject": "Objet",
                                       "textContent": "Corps du message", "replyTo": {"email": "reponse@example.com"}}


@pytest.mark.parametrize("cle_collee", [CLE, f"Zoho-enczapikey {CLE}"])
def test_zeptomail_prefixe_jamais_double(client, requetes, cle_collee):
    _regler(client, fournisseur="zeptomail", expediteur="envoi@beauthentik.net", nom_expediteur="beAuthentik",
            cle_api=cle_collee, zeptomail_hote="api.zeptomail.eu", actif=True)
    _envoyer(client)
    req = requetes["notees"][-1]
    assert str(req.url) == "https://api.zeptomail.eu/v1.1/email"
    assert req.headers["authorization"] == f"Zoho-enczapikey {CLE}"
    assert json.loads(req.content) == {"from": {"address": "envoi@beauthentik.net", "name": "beAuthentik"},
                                       "to": [{"email_address": {"address": "dest@example.com"}}],
                                       "subject": "Objet", "textbody": "Corps du message",
                                       "reply_to": [{"address": "reponse@example.com"}]}


def test_smtp_reglages_et_mot_de_passe(client, requetes, monkeypatch):
    envois = []

    def smtp(c, dest, sujet, corps, reponse_a):
        envois.append((c["smtp_hote"], c["smtp_port"], c["smtp_securite"], c["smtp_utilisateur"],
                       c["smtp_mot_de_passe"], dest))

    monkeypatch.setattr(envoi_email, "_smtp_synchrone", smtp)
    _regler(client, fournisseur="smtp", expediteur="envoi@beauthentik.net", smtp_hote="smtp.exemple.net",
            smtp_port=465, smtp_securite="ssl", smtp_utilisateur="u", smtp_mot_de_passe="mdp_test", actif=True)
    _envoyer(client)
    assert envois == [("smtp.exemple.net", 465, "ssl", "u", "mdp_test", "dest@example.com")]
    assert not requetes["notees"]


# ---------------------------------------------------------------------------
# Erreurs des fournisseurs
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("fournisseur,reponse,attendu", [
    ("resend", httpx.Response(422, json={"message": "domain is not verified"}), "Resend 422 : domain is not verified"),
    ("brevo", httpx.Response(401, json={"code": "unauthorized", "message": "Key not found"}), "Brevo 401 : Key not found"),
    ("zeptomail", httpx.Response(400, json={"error": {"message": "Invalid", "details": [{"message": "bad from"}]}}),
     "ZeptoMail 400 : Invalid ; bad from"),
])
def test_erreur_du_fournisseur_remontee(client, requetes, fournisseur, reponse, attendu):
    requetes["etat"]["reponse"] = lambda req: reponse
    _regler(client, fournisseur=fournisseur, expediteur="envoi@beauthentik.net", cle_api=CLE, actif=True)
    with pytest.raises(envoi_email.ErreurEnvoi) as exc:
        _envoyer(client)
    assert str(exc.value) == attendu and CLE not in str(exc.value)
    # Envoi journalisé : ne lève jamais, statut ECHEC avec le message du fournisseur
    res = client.portal.call(lambda: envoi_email.envoyer_journalise("dest@example.com", "s", "c", "test"))
    assert res["statut"] == "ECHEC" and res["erreur"] == attendu


def test_non_configure_par_defaut(client, requetes):
    res = client.portal.call(lambda: envoi_email.envoyer_journalise("dest@example.com", "s", "c", "test"))
    assert res["statut"] == "NON_CONFIGURE" and not requetes["notees"]
    assert client.portal.call(lambda: db.emails_journal.find_one({"contexte": "test"}))["statut"] == "NON_CONFIGURE"


# ---------------------------------------------------------------------------
# Secrets jamais renvoyés ni stockés en clair ; écran réservé ; journal ; essai
# ---------------------------------------------------------------------------
def test_ecran_reserve_cle_jamais_renvoyee_ni_en_clair(client, make_user, requetes):
    _, membre, _ = make_user()
    assert client.get("/api/plateforme/parametres/email", headers=membre).status_code == 403
    adm = _admin(client, make_user)
    r = client.put("/api/plateforme/parametres/email", headers=adm, json={
        "fournisseur": "resend", "expediteur": "envoi@beauthentik.net", "nom_expediteur": "beAuthentik",
        "cle_api": CLE, "actif": True})
    assert r.status_code == 200, r.text
    assert CLE not in r.text and r.json()["a_cle"]["resend"] is True
    lu = client.get("/api/plateforme/parametres/email", headers=adm)
    assert CLE not in lu.text and lu.json()["en_vigueur"]["pret"] is True
    doc = client.portal.call(lambda: db.parametres_plateforme.find_one({"_id": "email"}))
    assert CLE not in json.dumps(doc, default=str)
    # Champ secret vide : clé conservée
    client.put("/api/plateforme/parametres/email", headers=adm, json={"cle_api": "", "nom_expediteur": "BA"})
    assert envoi_email.dechiffrer(client.portal.call(
        lambda: db.parametres_plateforme.find_one({"_id": "email"}))["cles_chiffrees"]["resend"]) == CLE
    # Journal : qui, quand, quel fournisseur — jamais la clé
    journal = client.get("/api/plateforme/parametres/email/journal", headers=adm)
    assert CLE not in journal.text
    modifs = journal.json()["modifications"]
    assert len(modifs) == 2 and modifs[-1]["fournisseur"] == "resend" and modifs[-1]["secret_modifie"] is True
    assert modifs[-1]["par"] and modifs[-1]["date"]


def test_essai_avec_reglages_enregistres_et_erreur_affichee(client, make_user, requetes):
    adm = _admin(client, make_user)
    client.put("/api/plateforme/parametres/email", headers=adm, json={
        "fournisseur": "brevo", "expediteur": "envoi@beauthentik.net", "cle_api": CLE, "actif": True})
    r = client.post("/api/plateforme/parametres/email/essai", headers=adm, json={"destinataire": "moi@example.com"})
    assert r.json()["statut"] == "ENVOYE"
    assert json.loads(requetes["notees"][-1].content)["to"] == [{"email": "moi@example.com"}]
    requetes["etat"]["reponse"] = lambda req: httpx.Response(400, json={"message": "sender not valid"})
    r = client.post("/api/plateforme/parametres/email/essai", headers=adm, json={})
    assert r.json()["statut"] == "ECHEC" and r.json()["erreur"] == "Brevo 400 : sender not valid"


def test_port_25_refuse_et_desactive(client, make_user, requetes):
    adm = _admin(client, make_user)
    r = client.put("/api/plateforme/parametres/email", headers=adm, json={"fournisseur": "smtp", "smtp_port": 25})
    assert r.status_code == 400 and "25" in r.json()["detail"]
    r = client.put("/api/plateforme/parametres/email", headers=adm, json={"fournisseur": "desactive"})
    assert r.json()["en_vigueur"]["fournisseur"] == "desactive" and r.json()["en_vigueur"]["pret"] is False


# ---------------------------------------------------------------------------
# Repli sur les variables d'environnement et compatibilité
# ---------------------------------------------------------------------------
def test_repli_variables_environnement(client, requetes, monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "brevo_api_key", CLE)
    monkeypatch.setattr(s, "email_expediteur", "envoi@beauthentik.net")
    assert client.portal.call(envoi_email.config_effective)["fournisseur"] == "brevo"
    monkeypatch.setattr(s, "plateforme_smtp_hote", "smtp.exemple.net")
    assert client.portal.call(envoi_email.config_effective)["fournisseur"] == "smtp"
    monkeypatch.setattr(s, "resend_api_key", CLE)
    monkeypatch.setattr(s, "resend_expediteur", "resend@beauthentik.net")
    c = client.portal.call(envoi_email.config_effective)
    assert c["fournisseur"] == "resend" and c["source"] == "variables d'environnement"
    _envoyer(client)
    assert str(requetes["notees"][-1].url) == envoi_email.RESEND_URL
    # Un réglage fait dans l'écran passe avant les variables d'environnement
    _regler(client, fournisseur="desactive")
    assert client.portal.call(envoi_email.config_effective)["fournisseur"] == "desactive"


def test_repli_zeptomail_hote(client, requetes, monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "zeptomail_api_key", CLE)
    monkeypatch.setattr(s, "zeptomail_hote", "api.zeptomail.in")
    monkeypatch.setattr(s, "email_expediteur", "envoi@beauthentik.net")
    _envoyer(client)
    assert str(requetes["notees"][-1].url) == "https://api.zeptomail.in/v1.1/email"


def test_ancien_document_smtp_sans_fournisseur(client, requetes, monkeypatch):
    envois = []
    monkeypatch.setattr(envoi_email, "_smtp_synchrone", lambda c, *a: envois.append((c["smtp_hote"], c["smtp_mot_de_passe"])))
    client.portal.call(lambda: db.parametres_plateforme.insert_one({
        "_id": "email", "hote": "smtp.ancien.net", "port": 587, "utilisateur": "u", "expediteur": "envoi@beauthentik.net",
        "mot_de_passe_chiffre": envoi_email.chiffrer("mdp_test")}))
    assert client.portal.call(envoi_email.lire_public)["fournisseur"] == "smtp"
    _envoyer(client)
    assert envois == [("smtp.ancien.net", "mdp_test")]


# ---------------------------------------------------------------------------
# E-mails EN PLUS de WhatsApp / SMS
# ---------------------------------------------------------------------------
def test_alerte_administrateurs_whatsapp_et_email(client, make_user, requetes, monkeypatch):
    _admin(client, make_user)
    messages = []

    async def envoyer(user, texte):
        messages.append(texte)
        return {"ok": True, "canal": "whatsapp", "erreur": None}

    monkeypatch.setattr(envoi_messages, "envoyer", envoyer)
    _regler(client, fournisseur="resend", expediteur="envoi@beauthentik.net", cle_api=CLE, actif=True)
    client.portal.call(lambda: envoi_messages.alerter_administrateurs("beAuthentik : ÉCHEC de la sauvegarde (x)."))
    adresses = client.portal.call(envoi_email.emails_administrateurs)
    assert messages and len(requetes["notees"]) == len(adresses) >= 1
    corps = json.loads(requetes["notees"][-1].content)
    assert corps["subject"] == "beAuthentik : ÉCHEC de la sauvegarde" and "ÉCHEC" in corps["text"]


def test_avertissement_cycle_vie_par_email_une_seule_fois(client, make_user, requetes, monkeypatch, tmp_path):
    s = get_settings()
    monkeypatch.setattr(s, "beauthentik_sauvegardes_dossier_local", str(tmp_path / "r2"))
    monkeypatch.setattr(s, "sauvegarde_auto_phrase", "phrase de sauvegarde automatique 2026")

    async def envoyer(user, texte):
        return {"ok": False, "canal": None, "erreur": "WhatsApp et SMS indisponibles ou non configurés"}

    async def alerter(texte, **_):
        return 0

    monkeypatch.setattr(cycle_vie.envoi_messages, "envoyer", envoyer)
    monkeypatch.setattr(cycle_vie.envoi_messages, "alerter_administrateurs", alerter)
    reel = datetime.now(timezone.utc)
    monkeypatch.setattr(abonnement_grace, "maintenant", lambda: reel)
    client.portal.call(lambda: parametres_plateforme.marquer({"cycle_debut_le": (reel - timedelta(days=400)).isoformat()}))
    _regler(client, fournisseur="brevo", expediteur="envoi@beauthentik.net", cle_api=CLE, actif=True)
    uid, _, _ = make_user()
    email = client.portal.call(lambda: db.users.find_one({"id": uid}))["email"]
    echeance = reel - timedelta(days=103)
    client.portal.call(lambda: db.subscriptions.insert_one({
        "id": str(uuid.uuid4()), "user_id": uid, "plan_id": "p", "status": "active",
        "expires_at": echeance.isoformat(), "created_at": (echeance - timedelta(days=30)).isoformat()}))
    try:
        for _ in range(2):  # deux passages le même jour : un seul e-mail
            client.portal.call(lambda: cycle_vie.executer_quotidien("test"))
        vers_membre = [r for r in requetes["notees"] if json.loads(r.content)["to"] == [{"email": email}]]
        assert len(vers_membre) == 1
        assert "suspendu dans 7 jours" in json.loads(vers_membre[0].content)["subject"]
        suivi = client.portal.call(lambda: db.users.find_one({"id": uid}))["cycle_vie"]["avertissement_103"]
        assert suivi["email"] == "ENVOYE" and suivi["ok"] is True and suivi["canal"] is None
        journal = client.portal.call(lambda: db.cycle_vie_journal.find_one({"user_id": uid, "action": "avertissement_103"}))
        assert journal["details"]["email"] == "ENVOYE"
    finally:
        async def _n():
            await db.subscriptions.delete_many({"user_id": uid})
            await db.parametres_plateforme.delete_many({})
        client.portal.call(_n)
        parametres_plateforme.vider_cache()
