"""09/10/2026 — Photos : bande opaque des yeux au nez + validation obligatoire par un administrateur.

Demande du propriétaire : « L'IA devait afficher ma photo avec une bande des yeux au nez afin que je ne sois pas
reconnaissable. Et étant Administrateur je devais valider mon inscription et voir ma photo masquée. »
"""
import numpy as np

from ai_moderation import ModerationResult
from face_blur import band_faces_in_photo, polygone_bande


def test_polygone_bande_couvre_des_yeux_au_nez():
    """Visage de face (repères YuNet) : la bande déborde des yeux sur les côtés et descend jusqu'au nez."""
    # Repères : œil droit, œil gauche, nez, coin droit de la bouche, coin gauche de la bouche
    reperes = np.array([[100, 100], [160, 100], [130, 140], [110, 170], [150, 170]], dtype=np.float32)
    poly = polygone_bande((0, 0, 200, 200), reperes)
    xs, ys = poly[:, 0], poly[:, 1]
    assert xs.min() < 100 - 30 and xs.max() > 160 + 30      # déborde largement des deux yeux
    assert ys.min() < 100 - 20                               # couvre les sourcils
    assert 140 <= ys.max() < 170                             # descend jusqu'au nez, sans couvrir la bouche


def test_bande_aucun_visage():
    """Image sans visage : pas de bande (l'appelant floute alors toute la photo)."""
    vide = np.full((200, 200, 3), 255, dtype=np.uint8)
    assert band_faces_in_photo(vide) is None


def _admin(client, make_user, role="admin"):
    """Membre promu administrateur (ou modérateur) directement en base."""
    from db import db
    uid, headers, _ = make_user()
    client.portal.call(lambda: db.users.update_one({"id": uid}, {"$set": {"role": role}}))
    return headers


def test_photo_conforme_attend_la_validation_admin(client, make_user, monkeypatch):
    """L'IA approuve, mais la photo attend l'administrateur ; l'aperçu masqué est prêt dès l'envoi."""
    import routes.photos as ph

    # Analyse simulée : 1 visage, avis IA « conforme », génération des images sans réseau
    async def un_visage(url):
        return 1

    async def ia_conforme(url, prompt):
        return ModerationResult(decision="approved", reason="Photo nette, un seul visage")

    async def masque(url):
        return "https://x/masque.jpg"

    async def variantes(url):
        return "https://x/filigrane.jpg", "https://x/masque-final.jpg"

    monkeypatch.setattr(ph, "_count_faces", un_visage)
    monkeypatch.setattr(ph, "analyze_image", ia_conforme)
    monkeypatch.setattr(ph, "_generate_masked", masque)
    monkeypatch.setattr(ph, "_generate_approved_variants", variantes)

    admin = _admin(client, make_user)
    reglages = client.get("/api/admin/settings/moderation", headers=admin).json()
    assert reglages["validation_admin_obligatoire"] is True          # valeur par défaut

    # 1) Réglage par défaut : la photo attend l'administrateur, avec son aperçu masqué
    _, membre, _ = make_user()
    r = client.post("/api/me/photos", json={"url": "https://x/moi.jpg", "is_primary": True}, headers=membre)
    assert r.status_code == 201, r.text
    photo = r.json()
    assert photo["status"] == "needs_review"
    assert photo["masked_url"] == "https://x/masque.jpg"
    assert "administrateur" in photo["moderation_notes"]

    # 2) Elle apparaît dans la file d'attente (un modérateur la voit aussi)
    moderateur = _admin(client, make_user, role="moderator")
    file_attente = client.get("/api/admin/photos/pending", headers=moderateur).json()
    item = next(p for p in file_attente if p["id"] == photo["id"])
    assert item["masked_url"] == "https://x/masque.jpg"

    # 3) Validation par l'administrateur : photo approuvée, version masquée définitive
    v = client.post(f"/api/admin/photos/{item['user_id']}/{photo['id']}/review", params={"approve": True}, headers=admin)
    assert v.status_code == 200 and v.json()["status"] == "approved"

    # 4) Interrupteur désactivé : une photo jugée conforme par l'IA est approuvée directement
    reglages["validation_admin_obligatoire"] = False
    assert client.put("/api/admin/settings/moderation", json=reglages, headers=admin).status_code == 200
    try:
        r2 = client.post("/api/me/photos", json={"url": "https://x/moi2.jpg"}, headers=membre).json()
        assert r2["status"] == "approved"
        assert r2["masked_url"] == "https://x/masque-final.jpg"
    finally:
        # Remise du réglage par défaut pour les autres tests
        reglages["validation_admin_obligatoire"] = True
        client.put("/api/admin/settings/moderation", json=reglages, headers=admin)
