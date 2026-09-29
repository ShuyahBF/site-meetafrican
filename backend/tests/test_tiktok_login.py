"""« Continuer avec TikTok » : connexion, inscription avec liaison, liaison à un
compte existant. Les appels à TikTok sont simulés (aucun accès réseau)."""
from urllib.parse import parse_qs, urlparse

import pytest

from config import get_settings
from routes import auth_tiktok


@pytest.fixture
def tiktok_simule(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "tiktok_client_key", "cle-test")
    monkeypatch.setattr(s, "tiktok_client_secret", "secret-test")
    compte = {"open_id": "oid-1"}

    async def echanger_code(code):
        return {"access_token": "at", "open_id": compte["open_id"]}

    async def lire_profil(jeton):
        return {"open_id": compte["open_id"], "display_name": "Awa TikTok", "avatar_url": "https://p16.tiktokcdn.com/a.jpg"}

    monkeypatch.setattr(auth_tiktok, "echanger_code", echanger_code)
    monkeypatch.setattr(auth_tiktok, "lire_profil", lire_profil)
    return compte


def _code_tiktok(client):
    """Parcours TikTok jusqu'au code à usage unique renvoyé au site."""
    url = urlparse(client.get("/api/auth/tiktok/start").json()["url"])
    params = parse_qs(url.query)
    assert url.netloc == "www.tiktok.com" and params["scope"] == ["user.info.basic"]
    r = client.get("/api/auth/tiktok/callback", params={"code": "c", "state": params["state"][0]}, follow_redirects=False)
    cible = urlparse(r.headers["location"])
    assert cible.path == "/connexion"
    return parse_qs(cible.query)["tiktok"][0]


def test_non_configure(client):
    assert client.get("/api/auth/tiktok/config").json() == {"actif": False}
    assert client.get("/api/auth/tiktok/start").status_code == 503


def test_inscription_puis_connexion_par_tiktok(client, tiktok_simule):
    tiktok_simule["open_id"] = "oid-inscription"
    code = _code_tiktok(client)
    r = client.post("/api/auth/tiktok/finaliser", json={"code": code})
    assert r.json()["inscription"]["nom"] == "Awa TikTok"
    # Inscription complète (âge et identité restent exigés), avec le code de liaison
    r = client.post("/api/auth/register", json={"full_name": "Awa T", "email": "awa.tiktok@example.com",
                                                "password": "motdepasse123", "gender": "femme", "birthdate": "1995-05-05",
                                                "tiktok_lien": code})
    assert r.status_code == 201, r.text
    # Le code est consommé : il ne resservira pas
    assert client.post("/api/auth/tiktok/finaliser", json={"code": code}).status_code == 400
    # Connexion suivante : directement avec TikTok
    r = client.post("/api/auth/tiktok/finaliser", json={"code": _code_tiktok(client)})
    assert r.status_code == 200 and r.json()["user"]["full_name"] == "Awa T" and r.json()["access_token"]


def test_liaison_a_un_compte_existant(client, tiktok_simule):
    tiktok_simule["open_id"] = "oid-existant"
    email = "compte.existant@example.com"  # compte classique déjà existant
    assert client.post("/api/auth/register", json={"full_name": "Issa K", "email": email, "password": "motdepasse123",
                                                   "gender": "homme", "birthdate": "1990-01-01"}).status_code == 201
    code = _code_tiktok(client)
    assert "inscription" in client.post("/api/auth/tiktok/finaliser", json={"code": code}).json()
    r = client.post("/api/auth/login", json={"identifier": email, "password": "motdepasse123", "tiktok_lien": code})
    assert r.status_code == 200, r.text
    r = client.post("/api/auth/tiktok/finaliser", json={"code": _code_tiktok(client)})
    assert r.json()["user"]["full_name"] == "Issa K"


def test_etat_falsifie_et_code_inconnu(client, tiktok_simule):
    r = client.get("/api/auth/tiktok/callback", params={"code": "c", "state": "faux"}, follow_redirects=False)
    assert r.headers["location"].endswith("tiktok_erreur=invalide")
    assert client.post("/api/auth/tiktok/finaliser", json={"code": "x" * 20}).status_code == 400
    r = client.post("/api/auth/register", json={"full_name": "Zz", "email": "zz@example.com", "password": "motdepasse123",
                                                "gender": "homme", "birthdate": "1990-01-01", "tiktok_lien": "y" * 20})
    assert r.status_code == 400  # code de liaison invalide : aucun compte créé
    assert client.post("/api/auth/login", json={"identifier": "zz@example.com", "password": "motdepasse123"}).status_code == 401
