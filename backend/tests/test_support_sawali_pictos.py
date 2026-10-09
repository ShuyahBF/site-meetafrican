"""SAWALI lot 93 — pictogrammes de la fenêtre d'assistance : la plateforme relaie photo / document / vidéo, note
vocale et lecture d'un média vers SAWALI (requêtes signées) ; les refus de SAWALI (type, taille) restent lisibles.
Aucun appel réseau réel (transport simulé)."""
import base64
import json

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

import support_sawali as ss

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 32 + b"\xff\xd9"


def application(monkeypatch, repondre):
    """Petite application avec le routeur du support et un utilisateur connecté simulé."""
    monkeypatch.setenv("LILUVINE_WA_HMAC", "cle-test")
    monkeypatch.setenv("SAWALI_API_URL", "https://sawali.test")
    monkeypatch.setattr(ss, "_transport", httpx.MockTransport(repondre))
    app = FastAPI()
    app.include_router(ss.creer_router(lambda: {"id": "u1", "nom": "Awa"}, lambda u: {"id": u["id"], "nom": u["nom"]}), prefix="/api")
    return TestClient(app)


def test_fichier_transcription_media(monkeypatch):
    vus = []

    def repondre(r: httpx.Request):
        corps = json.loads(r.content.decode())
        vus.append((r.url.path, corps))
        if r.url.path.endswith("/fichier"):
            return httpx.Response(200, json={"ok": True, "message": {"id": "m1", "media": {"genre": "image"}}})
        if r.url.path.endswith("/transcrire"):
            return httpx.Response(200, json={"ok": True, "texte": "Bonjour"})
        return httpx.Response(200, json={"type": "image/jpeg", "nom": "a.jpg", "contenu": base64.b64encode(JPEG).decode()})

    c = application(monkeypatch, repondre)
    data = "data:image/jpeg;base64," + base64.b64encode(JPEG).decode()
    r = c.post("/api/support-sawali/fichier", json={"fichier": data, "nom": "a.jpg", "legende": " Voici "})
    assert r.status_code == 200 and r.json()["message"]["media"]["genre"] == "image"
    assert vus[-1][0] == "/api/support-plateforme/fichier" and vus[-1][1]["utilisateur"]["id"] == "u1" and vus[-1][1]["legende"] == "Voici"
    assert c.post("/api/support-sawali/transcrire", json={"audio": "data:audio/webm;base64,QUJDREVGR0g="}).json()["texte"] == "Bonjour"
    m = c.get("/api/support-sawali/media/m1")
    assert m.status_code == 200 and m.content == JPEG and m.headers["content-type"] == "image/jpeg"
    assert vus[-1] == ("/api/support-plateforme/media", {"utilisateur": {"id": "u1", "nom": "Awa"}, "message_id": "m1"})


def test_refus_lisible(monkeypatch):
    c = application(monkeypatch, lambda r: httpx.Response(415, json={"detail": "Type de fichier non accepté"}))
    r = c.post("/api/support-sawali/fichier", json={"fichier": "data:application/x-msdownload;base64,TVo=AAAA", "nom": "x.exe"})
    assert r.status_code == 415 and r.json()["detail"] == "Type de fichier non accepté"
