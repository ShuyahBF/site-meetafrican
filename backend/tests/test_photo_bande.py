"""09/10/2026 — Photos : bande opaque des yeux au nez + validation obligatoire par un administrateur.

Demande du propriétaire : « L'IA devait afficher ma photo avec une bande des yeux au nez afin que je ne sois pas
reconnaissable. Et étant Administrateur je devais valider mon inscription et voir ma photo masquée. »
"""
import numpy as np

from ai_moderation import ModerationResult
from face_blur import band_faces_in_photo, masquer_visages, polygone_bande
from image_processing import mask_version


def test_polygone_bande_des_sourcils_au_dessus_du_menton():
    """Visage de face (repères YuNet) : le bandeau déborde des yeux et descend un peu sous la bouche (pas au menton)."""
    # Repères : œil droit, œil gauche, nez, coin droit de la bouche, coin gauche de la bouche
    reperes = np.array([[100, 100], [160, 100], [130, 140], [110, 170], [150, 170]], dtype=np.float32)
    poly = polygone_bande((0, 0, 200, 200), reperes)
    xs, ys = poly[:, 0], poly[:, 1]
    assert xs.min() < 100 - 30 and xs.max() > 160 + 30      # déborde largement des deux yeux
    assert ys.min() < 100 - 20                               # couvre les sourcils
    assert 170 < ys.max() < 200                              # couvre la bouche, s'arrête au-dessus du menton


def test_bande_aucun_visage():
    """Image sans visage : pas de bande (l'appelant floute alors toute la photo)."""
    vide = np.full((200, 200, 3), 255, dtype=np.uint8)
    assert band_faces_in_photo(vide) is None
    assert masquer_visages(vide, "masque_sanitaire") is None


def test_version_du_masque_suit_le_style():
    """Changer de style dans les paramètres fait régénérer les photos (version différente)."""
    assert mask_version("bandeau") != mask_version("masque_sanitaire")
    assert mask_version("inconnu") == mask_version("bandeau")


def _admin(client, make_user, role="admin"):
    """Membre promu administrateur (ou modérateur) directement en base."""
    from db import db
    uid, headers, _ = make_user()
    client.portal.call(lambda: db.users.update_one({"id": uid}, {"$set": {"role": role}}))
    return headers


def test_l_ia_decide_l_admin_force_s_il_le_veut(client, make_user, monkeypatch):
    """Règle du 09/10/2026 : l'IA valide seule ; administrateurs ET modérateurs peuvent forcer une décision sur une photo.
    Option « validation systématique » : la photo attend alors le super-administrateur, aperçu masqué prêt."""
    import routes.photos as ph

    # Analyse simulée : 1 visage, avis IA « conforme », génération des images sans réseau
    async def un_visage(url):
        return 1

    async def ia_conforme(url, prompt):
        return ModerationResult(decision="approved", reason="Photo nette, un seul visage")

    async def masque(url, style="bandeau"):
        return "https://x/masque.jpg"

    async def variantes(url, style="bandeau"):
        return "https://x/filigrane.jpg", "https://x/masque-final.jpg"

    monkeypatch.setattr(ph, "_count_faces", un_visage)
    monkeypatch.setattr(ph, "analyze_image", ia_conforme)
    monkeypatch.setattr(ph, "_generate_masked", masque)
    monkeypatch.setattr(ph, "_generate_approved_variants", variantes)

    admin = _admin(client, make_user)
    moderateur = _admin(client, make_user, role="moderator")
    reglages = client.get("/api/admin/settings/moderation", headers=admin).json()
    assert reglages["validation_admin_systematique"] is False        # valeur par défaut : l'IA décide

    # 1) L'IA juge la photo conforme : publiée aussitôt
    _, membre, _ = make_user()
    photo = client.post("/api/me/photos", json={"url": "https://x/moi.jpg", "is_primary": True}, headers=membre).json()
    assert photo["status"] == "approved" and photo["masked_url"] == "https://x/masque-final.jpg"

    # 2) Elle figure dans « Décisions de l'IA », que le modérateur voit aussi…
    decisions = client.get("/api/admin/photos/decisions-ia", headers=moderateur).json()
    item = next(p for p in decisions if p["id"] == photo["id"])
    # … et le modérateur peut FORCER le refus, puis l'administrateur rétablir l'approbation
    url = f"/api/admin/photos/{item['user_id']}/{photo['id']}/review"
    assert client.post(url, params={"approve": False}, headers=moderateur).json()["status"] == "rejected"
    assert client.post(url, params={"approve": True}, headers=admin).json()["status"] == "approved"

    # 3) Option « validation systématique » : la photo attend le super-administrateur, avec son aperçu masqué
    reglages["validation_admin_systematique"] = True
    assert client.put("/api/admin/settings/moderation", json=reglages, headers=admin).status_code == 200
    try:
        r2 = client.post("/api/me/photos", json={"url": "https://x/moi2.jpg"}, headers=membre).json()
        assert r2["status"] == "needs_review" and r2["masked_url"] == "https://x/masque.jpg"
        assert any(p["id"] == r2["id"] for p in client.get("/api/admin/photos/pending", headers=moderateur).json())
    finally:
        reglages["validation_admin_systematique"] = False
        client.put("/api/admin/settings/moderation", json=reglages, headers=admin)

    # 4) Option désactivée : la photo retenue est libérée (comme au démarrage du serveur)
    assert client.portal.call(ph.liberer_photos_conformes) >= 1
    moi = client.get("/api/auth/me", headers=membre).json()
    libre = next(p for p in moi["photos"] if p["id"] == r2["id"])
    assert libre["status"] == "approved" and "administrateur" not in (libre["moderation_notes"] or "")


def test_visage_en_clair_seulement_apres_un_match(client, make_user):
    """Le bandeau n'est servi qu'aux membres qui n'ont PAS matché avec le propriétaire de la photo."""
    from db import db

    proprio, _, _ = make_user(gender="femme")
    visiteur, h_visiteur, _ = make_user(gender="homme")
    photo = {"id": "p-clair", "url": "https://x/clair.jpg", "masked_url": "https://x/bandeau.jpg",
             "status": "approved", "is_primary": True, "mask_version": mask_version()}
    client.portal.call(lambda: db.users.update_one({"id": proprio}, {"$set": {"photos": [photo]}}))

    # Pas de match : bandeau
    vue = client.get(f"/api/users/{proprio}", headers=h_visiteur).json()
    assert vue["profile"]["photos"][0]["url"] == "https://x/bandeau.jpg"

    # Match : photo en clair
    a, b = sorted([proprio, visiteur])
    client.portal.call(lambda: db.matches.insert_one({"id": "m-clair", "user_a": a, "user_b": b, "created_at": "2026-10-09T00:00:00+00:00"}))
    vue = client.get(f"/api/users/{proprio}", headers=h_visiteur).json()
    assert vue["profile"]["photos"][0]["url"] == "https://x/clair.jpg"


def test_piece_d_identite_super_admin_seulement(client, make_user):
    """Pièces d'identité : seul le super-administrateur tranche ou force une décision (pas un modérateur)."""
    admin = _admin(client, make_user)
    moderateur = _admin(client, make_user, role="moderator")
    for chemin in ("/api/admin/verification/pending", "/api/admin/verification/decisions-ia"):
        assert client.get(chemin, headers=moderateur).status_code == 403
        assert client.get(chemin, headers=admin).status_code == 200
    assert client.post("/api/admin/verification/inconnue/review", params={"approve": True}, headers=moderateur).status_code == 403


def test_partage_facebook_candidats_et_publication(client, make_user):
    """Lot 66 — seuls les membres consentants (photo masquée approuvée + bio) sont proposés à SAWALI,
    par le canal signé ; prénom seul, jamais le nom complet ; pas de republication avant 60 jours."""
    import json
    import time

    import transmission_wa as service
    from db import db

    os_env = __import__("os").environ
    os_env["LILUVINE_WA_HMAC"] = "cle-de-test"
    try:
        def appel(corps):
            brut = json.dumps(corps)
            ts = str(int(time.time()))
            return client.post("/api/webhooks/liluvine-retour", content=brut, headers={
                "Content-Type": "application/json", "X-Timestamp": ts,
                "X-Signature": service.signer("cle-de-test", ts, brut)})

        photo = {"id": "pf1", "url": "https://x/f.jpg", "masked_url": "https://x/fm.jpg", "status": "approved", "is_primary": True}
        oui, h_oui, _ = make_user(bio="J'aime la musique et les voyages", city="Ouagadougou")
        non, _, _ = make_user(bio="Discret")
        client.portal.call(lambda: db.users.update_many({"id": {"$in": [oui, non]}}, {"$set": {"photos": [photo]}}))
        # Le membre donne son accord depuis son profil
        assert client.put("/api/me/profile", json={"partage_facebook": True}, headers=h_oui).json()["partage_facebook"] is True

        cands = appel({"type": "facebook_candidats", "nombre": 10}).json()["candidats"]
        ids = [c["membre_id"] for c in cands]
        assert oui in ids and non not in ids
        c = next(c for c in cands if c["membre_id"] == oui)
        assert c["photo_url"] == "https://x/fm.jpg" and " " not in c["prenom"] and c["bio"].startswith("J'aime")

        # Publication notée : plus proposé ensuite (60 jours)
        assert appel({"type": "facebook_publie", "membre_id": oui, "post_id": "123_456"}).json()["ok"] is True
        assert oui not in [x["membre_id"] for x in appel({"type": "facebook_candidats"}).json()["candidats"]]
        # Sans signature : refusé
        assert client.post("/api/webhooks/liluvine-retour", json={"type": "facebook_candidats"}).status_code == 401
    finally:
        os_env.pop("LILUVINE_WA_HMAC", None)
