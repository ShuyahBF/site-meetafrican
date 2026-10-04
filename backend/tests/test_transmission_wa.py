"""Transmission WhatsApp (transmission_wa.py) : WABA propre en priorité, sinon
Transmission WA Universelle Liluvine. Les réponses HTTP sont SIMULÉES
(httpx.MockTransport) : aucun appel réseau réel."""
import asyncio
import hashlib
import hmac
import json

import httpx
import pytest

import otp_senders
import transmission_wa as twu
from config import get_settings

URL = "https://sawali.exemple/api/webhook/liluvine-send"
CLE = "cle-de-test-non-secrete"


@pytest.fixture
def simulateur(monkeypatch):
    """Installe un transport simulé ; `reponses` = liste de codes HTTP ou d'exceptions,
    consommée dans l'ordre. Renvoie la liste des requêtes reçues."""
    requetes = []

    def installer(*reponses):
        file = list(reponses)

        def traiter(requete: httpx.Request):
            requetes.append(requete)
            suivante = file.pop(0) if file else 200
            if isinstance(suivante, Exception):
                raise suivante
            # (code HTTP, corps JSON) : réponse d'erreur détaillée (ex. erreur Meta)
            if isinstance(suivante, tuple):
                return httpx.Response(suivante[0], json=suivante[1])
            if suivante == 200 and "graph.facebook.com" in str(requete.url):
                return httpx.Response(200, json={"messages": [{"id": "wamid.TEST"}]})
            if suivante == 200:
                return httpx.Response(200, json={"ok": True, "message_id": "wamid.LILU", "doublon": False})
            return httpx.Response(suivante, json={"detail": "erreur simulée"})

        monkeypatch.setattr(twu, "_transport", httpx.MockTransport(traiter))
        return requetes

    return installer


@pytest.fixture
def sans_waba(monkeypatch):
    monkeypatch.setattr(otp_senders, "whatsapp_configured", lambda: False)


@pytest.fixture
def liluvine(monkeypatch):
    monkeypatch.setenv("LILUVINE_WA_URL", URL)
    monkeypatch.setenv("LILUVINE_WA_HMAC", CLE)
    monkeypatch.setenv("LILUVINE_WA_EMETTEUR", "beauthentik")


def _envoyer(numero="+22670000000", message="Bonjour", **kw):
    return asyncio.run(twu.envoyer_whatsapp(numero, message, **kw))


def test_repli_liluvine_sans_waba_et_signature_hmac(simulateur, sans_waba, liluvine):
    requetes = simulateur(200)
    res = _envoyer(message="Alerte « Me suivre » é")
    assert res == {"ok": True, "canal": "liluvine", "message_id": "wamid.LILU", "erreur": None}
    assert len(requetes) == 1
    r = requetes[0]
    assert str(r.url) == URL
    corps_brut = r.content.decode("utf-8")
    corps = json.loads(corps_brut)
    # Corps du protocole : id uuid4, numéro international, message, source par défaut
    assert set(corps) == {"id", "to", "message", "source"}
    assert corps["to"] == "+22670000000"
    assert corps["message"] == "Alerte « Me suivre » é"
    assert corps["source"] == "beAuthentik"
    assert len(corps["id"]) == 36
    # Signature calculée sur le corps EXACT envoyé
    attendu = hmac.new(CLE.encode(), f"{r.headers['X-Timestamp']}.{corps_brut}".encode(), hashlib.sha256).hexdigest()
    assert r.headers["X-Signature"] == attendu
    assert r.headers["X-Emetteur"] == "beauthentik"
    assert r.headers["Content-Type"] == "application/json"
    # La clé n'apparaît jamais dans la requête
    assert CLE not in corps_brut and CLE not in str(dict(r.headers))


def test_source_personnalisee(simulateur, sans_waba, liluvine):
    requetes = simulateur(200)
    _envoyer(source="beAuthentik — Me suivre")
    assert json.loads(requetes[0].content)["source"] == "beAuthentik — Me suivre"


def test_priorite_waba_si_configure(simulateur, liluvine, monkeypatch):
    monkeypatch.setattr(otp_senders, "whatsapp_configured", lambda: True)
    s = get_settings()
    monkeypatch.setattr(s, "whatsapp_access_token", "jeton-test")
    monkeypatch.setattr(s, "whatsapp_phone_number_id", "12345")
    requetes = simulateur(200)
    res = _envoyer()
    assert res == {"ok": True, "canal": "waba", "message_id": "wamid.TEST", "erreur": None}
    assert len(requetes) == 1 and "graph.facebook.com/v21.0/12345/messages" in str(requetes[0].url)
    assert json.loads(requetes[0].content)["to"] == "22670000000"


def test_nouvel_essai_meme_id_sur_5xx(simulateur, sans_waba, liluvine):
    requetes = simulateur(500, 200)
    res = _envoyer()
    assert res["ok"] is True and res["canal"] == "liluvine"
    assert len(requetes) == 2
    ids = [json.loads(r.content)["id"] for r in requetes]
    assert ids[0] == ids[1]
    # Corps identique, signature recalculée pour chaque essai
    assert requetes[0].content == requetes[1].content
    for r in requetes:
        attendu = hmac.new(CLE.encode(), r.headers["X-Timestamp"].encode() + b"." + r.content, hashlib.sha256).hexdigest()
        assert r.headers["X-Signature"] == attendu


def test_nouvel_essai_meme_id_sur_erreur_reseau(simulateur, sans_waba, liluvine):
    requetes = simulateur(httpx.ConnectError("coupure"), 200)
    res = _envoyer()
    assert res["ok"] is True
    assert len(requetes) == 2
    assert json.loads(requetes[0].content)["id"] == json.loads(requetes[1].content)["id"]


def test_un_seul_nouvel_essai(simulateur, sans_waba, liluvine):
    requetes = simulateur(503, 503, 200)
    res = _envoyer()
    assert res["ok"] is False and res["canal"] == "liluvine" and res["erreur"]
    assert len(requetes) == 2


@pytest.mark.parametrize("code", [401, 422, 429])
def test_pas_de_nouvel_essai_sur_4xx(simulateur, sans_waba, liluvine, code):
    requetes = simulateur(code, 200)
    res = _envoyer()
    assert res["ok"] is False and res["canal"] == "liluvine"
    assert len(requetes) == 1


def test_desactivation_propre_si_variables_absentes(simulateur, sans_waba, monkeypatch):
    monkeypatch.delenv("LILUVINE_WA_URL", raising=False)
    monkeypatch.setenv("LILUVINE_WA_HMAC", CLE)
    requetes = simulateur(200)
    res = _envoyer()
    assert res["ok"] is False and res["canal"] is None and "non configuré" in res["erreur"]
    assert requetes == []
    assert twu.etat() == {"waba_configure": False, "liluvine_configure": False, "emetteur": "beauthentik"}


def test_jamais_d_exception(sans_waba, liluvine, monkeypatch):
    def panne(*a, **k):
        raise RuntimeError("panne inattendue")
    monkeypatch.setattr(twu, "_envoyer_liluvine", panne)
    res = _envoyer()
    assert res["ok"] is False and res["erreur"]


def test_envoi_messages_passe_par_la_transmission(simulateur, sans_waba, liluvine, monkeypatch):
    """Les alertes (« Me suivre », cycle de vie, sauvegardes) partent par la Transmission
    universelle quand WABA n'est pas configuré, sans passer au SMS."""
    import envoi_messages
    requetes = simulateur(200)
    res = asyncio.run(envoi_messages.envoyer({"whatsapp": "70000000"}, "Signal perdu"))
    assert res == {"ok": True, "canal": "whatsapp", "erreur": None}
    assert json.loads(requetes[0].content)["to"] == "+22670000000"


def test_routes_administrateur(client, make_user, simulateur, sans_waba, liluvine):
    from db import db
    _, membre = make_user()[:2]
    # Membre ordinaire : refusé
    assert client.get("/api/admin/transmission-wa/etat", headers=membre).status_code == 403
    assert client.post("/api/admin/transmission-wa/test", json={"numero": "+22670000000"},
                       headers=membre).status_code == 403
    # Administrateur : état (sans aucun secret) et essai
    uid, admin = make_user()[:2]
    client.portal.call(lambda: db.users.update_one({"id": uid}, {"$set": {"role": "admin"}}))
    r = client.get("/api/admin/transmission-wa/etat", headers=admin)
    assert r.status_code == 200
    assert r.json() == {"waba_configure": False, "liluvine_configure": True, "emetteur": "beauthentik"}
    assert CLE not in r.text
    requetes = simulateur(200)
    r = client.post("/api/admin/transmission-wa/test", json={"numero": "+22670000000"}, headers=admin)
    assert r.status_code == 200 and r.json()["ok"] is True and r.json()["canal"] == "liluvine"
    assert json.loads(requetes[0].content)["message"] == "Test de transmission WhatsApp depuis beAuthentik"



# ---------------------------------------------------------------------------
# Protocole v3 — médias, désinscription, repli WABA → Liluvine, retours
# ---------------------------------------------------------------------------

@pytest.fixture
def avec_waba(monkeypatch):
    """WABA propre configuré (valeurs factices)."""
    monkeypatch.setattr(otp_senders, "whatsapp_configured", lambda: True)
    s = get_settings()
    monkeypatch.setattr(s, "whatsapp_access_token", "jeton-test")
    monkeypatch.setattr(s, "whatsapp_phone_number_id", "12345")


def _erreur_meta(code, message, details=""):
    """Réponse d'erreur du WABA telle que Meta la renvoie."""
    return (400, {"error": {"code": code, "message": message, "error_data": {"details": details}}})


def test_media_par_lien(simulateur, sans_waba, liluvine):
    requetes = simulateur(200)
    res = _envoyer(message="Votre facture", media={"type": "document", "url": "https://r2.exemple/f.pdf",
                                                   "nom_fichier": "facture.pdf", "mime": "application/pdf"})
    assert res["ok"] is True and res["canal"] == "liluvine"
    corps = json.loads(requetes[0].content)
    assert corps["message"] == "Votre facture"
    assert corps["media"] == {"type": "document", "url": "https://r2.exemple/f.pdf",
                              "nom_fichier": "facture.pdf", "mime": "application/pdf"}


def test_media_par_octets_encodes_en_base64(simulateur, sans_waba, liluvine):
    import base64
    requetes = simulateur(200)
    octets = b"%PDF-1.4 contenu de test \x00\xff"
    res = _envoyer(media={"type": "image", "contenu": octets, "mime": "image/png", "legende": "Photo"})
    assert res["ok"] is True
    media = json.loads(requetes[0].content)["media"]
    assert "url" not in media and base64.b64decode(media["contenu_base64"]) == octets
    assert media["legende"] == "Photo"


@pytest.mark.parametrize("media", [
    {"type": "document", "contenu": b"x" * (10 * 1024 * 1024 + 1)},       # plus de 10 Mo
    {"type": "document", "url": "https://a/b.pdf", "contenu": b"x"},       # les deux à la fois
    {"type": "document"},                                                 # ni l'un ni l'autre
    {"type": "sticker", "url": "https://a/b.webp"},                        # type inconnu
    {"type": "image", "url": "http://a/b.png"},                            # lien non HTTPS
])
def test_media_refuse_localement_sans_appel(simulateur, sans_waba, liluvine, media):
    requetes = simulateur(200)
    res = _envoyer(media=media)
    assert res["ok"] is False and res["canal"] is None and res["erreur"]
    assert requetes == []


def test_media_10_mo_exactement_accepte(simulateur, sans_waba, liluvine):
    requetes = simulateur(200)
    assert _envoyer(media={"type": "document", "contenu": b"x" * (10 * 1024 * 1024)})["ok"] is True
    assert len(requetes) == 1


def test_media_par_le_waba(simulateur, avec_waba):
    requetes = simulateur(200)
    res = _envoyer(message="Votre reçu", media={"type": "document", "url": "https://r2.exemple/r.pdf",
                                                "nom_fichier": "recu.pdf"})
    assert res["ok"] is True and res["canal"] == "waba"
    corps = json.loads(requetes[0].content)
    assert corps["type"] == "document"
    assert corps["document"] == {"link": "https://r2.exemple/r.pdf", "caption": "Votre reçu", "filename": "recu.pdf"}


def test_desinscrit_409_echec_definitif_sans_nouvel_essai(client, simulateur, sans_waba, liluvine):
    from db import db
    requetes = simulateur(409, 200)
    res = asyncio.run(twu.envoyer_whatsapp("+22670009409", "Bonjour"))
    assert res["ok"] is False and res["desinscrit"] is True and "désinscrit" in res["erreur"]
    assert len(requetes) == 1
    # Trace du refus dans liluvine_retours
    id_envoi = json.loads(requetes[0].content)["id"]
    trace = client.portal.call(lambda: db.liluvine_retours.find_one({"id_origine": id_envoi}, {"_id": 0}))
    assert trace["type"] == "refus_desinscrit" and trace["numero"] == "+22670009409"


def test_repli_waba_vers_liluvine_sur_fenetre_24h(simulateur, avec_waba, liluvine):
    requetes = simulateur(_erreur_meta(131047, "Re-engagement message",
                                       "More than 24 hours have passed"), 200)
    res = _envoyer(message="Signal perdu", media={"type": "image", "url": "https://r2.exemple/carte.png"})
    assert res["ok"] is True and res["canal"] == "liluvine_repli" and res["message_id"] == "wamid.LILU"
    assert len(requetes) == 2
    assert "graph.facebook.com" in str(requetes[0].url) and str(requetes[1].url) == URL
    # Même texte ET même média
    corps = json.loads(requetes[1].content)
    assert corps["message"] == "Signal perdu" and corps["media"]["url"] == "https://r2.exemple/carte.png"


def test_repli_waba_vers_liluvine_sur_panne_reseau(simulateur, avec_waba, liluvine):
    requetes = simulateur(httpx.ConnectError("coupure"), 200)
    res = _envoyer()
    assert res["ok"] is True and res["canal"] == "liluvine_repli" and len(requetes) == 2


def test_pas_de_repli_sur_numero_invalide(simulateur, avec_waba, liluvine):
    requetes = simulateur(_erreur_meta(100, "(#100) Invalid parameter", "Invalid phone number"), 200)
    res = _envoyer()
    assert res["ok"] is False and res["canal"] == "waba" and res["numero_invalide"] is True
    assert len(requetes) == 1


def test_pas_de_repli_si_liluvine_non_configuree(simulateur, avec_waba, monkeypatch):
    monkeypatch.delenv("LILUVINE_WA_URL", raising=False)
    requetes = simulateur(_erreur_meta(131047, "Re-engagement message"))
    res = _envoyer()
    assert res["ok"] is False and res["canal"] == "waba" and len(requetes) == 1


def test_echec_du_repli_rend_les_deux_erreurs(simulateur, avec_waba, liluvine):
    simulateur(_erreur_meta(131047, "Re-engagement message"), 422)
    res = _envoyer()
    assert res["ok"] is False and res["canal"] == "liluvine_repli"
    assert "WABA" in res["erreur"] and "repli" in res["erreur"]


def test_code_otp_par_liluvine_sans_waba(simulateur, sans_waba, liluvine):
    requetes = simulateur(200)
    ok, erreur = asyncio.run(otp_senders.send_whatsapp_code("22670000000", "123456"))
    assert ok is True and erreur is None
    corps = json.loads(requetes[0].content)
    assert str(requetes[0].url) == URL and "123456" in corps["message"] and "media" not in corps


def test_code_otp_sans_aucun_canal(simulateur, sans_waba, monkeypatch):
    monkeypatch.delenv("LILUVINE_WA_URL", raising=False)
    requetes = simulateur(200)
    ok, erreur = asyncio.run(otp_senders.send_whatsapp_code("22670000000", "123456"))
    assert ok is False and "pas encore configuré" in erreur and requetes == []


# --- Retours de SAWALI : POST /api/webhooks/liluvine-retour ---------------------

RETOUR = "/api/webhooks/liluvine-retour"


def _poster_retour(client, donnees, cle=CLE, decalage=0, signature=None):
    """Envoie un retour signé comme le fait SAWALI (corps brut signé)."""
    import time
    corps_brut = json.dumps(donnees, ensure_ascii=False).encode("utf-8")
    ts = str(int(time.time()) + decalage)
    sig = signature or hmac.new(cle.encode(), ts.encode() + b"." + corps_brut, hashlib.sha256).hexdigest()
    return client.post(RETOUR, content=corps_brut, headers={
        "Content-Type": "application/json", "X-Emetteur": "sawali", "X-Timestamp": ts, "X-Signature": sig})


def test_retour_signature_invalide_401(client, liluvine):
    donnees = {"type": "desinscription", "de": "+22670000001", "date": "2026-10-04T10:00:00Z"}
    assert _poster_retour(client, donnees, signature="0" * 64).status_code == 401
    assert _poster_retour(client, donnees, cle="mauvaise-cle").status_code == 401
    # Horodatage hors de la fenêtre de ±5 minutes
    assert _poster_retour(client, donnees, decalage=-400).status_code == 401
    assert _poster_retour(client, donnees, decalage=400).status_code == 401


def test_retour_sans_cle_configuree_503(client, monkeypatch):
    monkeypatch.delenv("LILUVINE_WA_HMAC", raising=False)
    assert _poster_retour(client, {"type": "statut", "id": "x", "statut": "sent"}).status_code == 503


def test_retour_type_inconnu_422(client, liluvine):
    assert _poster_retour(client, {"type": "autre"}).status_code == 422


def test_retour_statut_idempotent_et_journal_mis_a_jour(client, liluvine, simulateur, sans_waba):
    from db import db
    # Un envoi par Liluvine, noté dans le journal des envois
    requetes = simulateur(200)
    assert asyncio.run(twu.envoyer_whatsapp("+22670000777", "Bonjour"))["ok"] is True
    id_envoi = json.loads(requetes[0].content)["id"]
    donnees = {"type": "statut", "id": id_envoi, "message_id": "wamid.S1", "statut": "delivered",
               "erreur": None, "date": "2026-10-04T10:00:00Z"}
    r1 = _poster_retour(client, donnees)
    assert r1.status_code == 200 and r1.json() == {"ok": True, "doublon": False}
    # Même statut reçu une 2e fois : pas de doublon
    r2 = _poster_retour(client, donnees)
    assert r2.status_code == 200 and r2.json() == {"ok": True, "doublon": True}
    nb = client.portal.call(lambda: db.liluvine_retours.count_documents({"id_origine": id_envoi, "type": "statut"}))
    assert nb == 1
    envoi = client.portal.call(lambda: db.liluvine_envois.find_one({"id": id_envoi}, {"_id": 0}))
    assert envoi["statut"] == "delivered" and envoi["numero"] == "+22670000777"
    # Un statut DIFFÉRENT pour le même envoi est bien enregistré
    assert _poster_retour(client, {**donnees, "statut": "read"}).json()["doublon"] is False


def test_retour_reponse_signalee_aux_administrateurs_par_email(client, liluvine, monkeypatch):
    import envoi_email
    import envoi_messages
    signalements = []

    async def faux_email(sujet, corps, contexte):
        signalements.append((sujet, corps, contexte))
        return 1

    async def interdit(*a, **k):  # aucun WhatsApp / SMS ne doit partir (pas de boucle)
        raise AssertionError("aucun WhatsApp ne doit être envoyé")

    monkeypatch.setattr(envoi_email, "envoyer_aux_administrateurs", faux_email)
    monkeypatch.setattr(envoi_messages, "envoyer", interdit)
    monkeypatch.setattr(twu, "envoyer_whatsapp", interdit)
    donnees = {"type": "reponse", "id_origine": "id-1", "de": "+22670000002", "texte": "Merci, bien reçu",
               "media": None, "date": "2026-10-04T10:05:00Z"}
    assert _poster_retour(client, donnees).json() == {"ok": True, "doublon": False}
    assert _poster_retour(client, donnees).json() == {"ok": True, "doublon": True}
    # Un seul signalement, par e-mail, avec le texte de la réponse
    assert len(signalements) == 1
    assert "Merci, bien reçu" in signalements[0][1] and signalements[0][2] == "liluvine_reponse"


def test_route_admin_des_retours(client, make_user, liluvine):
    from db import db
    donnees = {"type": "desinscription", "de": "+22670000003", "date": "2026-10-04T11:00:00Z"}
    assert _poster_retour(client, donnees).status_code == 200
    _, membre = make_user()[:2]
    assert client.get("/api/admin/transmission-wa/retours", headers=membre).status_code == 403
    uid, admin = make_user()[:2]
    client.portal.call(lambda: db.users.update_one({"id": uid}, {"$set": {"role": "admin"}}))
    r = client.get("/api/admin/transmission-wa/retours", headers=admin)
    assert r.status_code == 200
    retours = r.json()["retours"]
    assert 1 <= len(retours) <= 100
    assert any(x["type"] == "desinscription" and x["numero"] == "+22670000003" for x in retours)
    assert CLE not in r.text
