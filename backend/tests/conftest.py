"""Configuration commune des tests : base MongoDB EN MÉMOIRE (mongomock) et
stockage local dans un dossier temporaire — aucun accès réseau, aucune
donnée réelle touchée. Les variables d'environnement doivent être posées
AVANT l'import de l'application (config.py les lit au premier import)."""
import os
import sys
import tempfile
from pathlib import Path

_tmp = tempfile.mkdtemp(prefix="maf-tests-")
os.environ.update({
    "MONGO_URL": "mongomock://",
    "STORAGE_BACKEND": "local",
    "UPLOADS_DIR": str(Path(_tmp) / "uploads"),
    "JWT_SECRET": "test-secret",
    "ADMIN_BOOTSTRAP_EMAIL": "",
    "ADMIN_BOOTSTRAP_PASSWORD": "",
    # Pas de signal de présence SAWALI pendant les tests (aucun réseau)
    "PRESENCE_SAWALI": "0",
    # Lot 71 : pas de signal de connexion / visite vers SAWALI (réactivé dans test_signal_connexions_sawali.py)
    "SIGNAL_CONNEXIONS_SAWALI": "0",
})
# Permet "import server" depuis backend/tests/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture(scope="session")
def client():
    import server

    # "with" déclenche l'événement startup (index, données de départ).
    with TestClient(server.app) as c:
        yield c


_counter = {"n": 0}


@pytest.fixture
def make_user(client):
    """Crée un membre et renvoie (id, en-têtes d'authentification)."""
    def _make(gender="femme", birthdate="1995-05-05", verified=False, **profile):
        _counter["n"] += 1
        res = client.post("/api/auth/register", json={
            "full_name": f"Membre {_counter['n']}",
            "email": f"membre{_counter['n']}@example.com",
            "password": "motdepasse123",
            "gender": gender,
            "birthdate": birthdate,
        })
        assert res.status_code == 201, res.text
        token = res.json()["access_token"]
        user_id = res.json()["user"]["id"]
        headers = {"Authorization": f"Bearer {token}"}
        if profile:
            r = client.put("/api/me/profile", json=profile, headers=headers)
            assert r.status_code == 200, r.text
        if verified:
            from db import db
            # Raccourci de test : on force le statut "vérifié" directement en
            # base (le vrai parcours passe par l'analyse IA de la pièce d'identité).
            client.portal.call(lambda: db.users.update_one(
                {"id": user_id}, {"$set": {"verification_status": "verified"}}
            ))
        return user_id, headers, token
    return _make
