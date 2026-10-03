"""GET /api/version : version et lot relus dans frontend/src/version.js
(source unique), hash du commit et heure de démarrage."""
import version_plateforme


def test_api_version_reprend_le_fichier_source_unique(client):
    attendu_version, attendu_lot = version_plateforme.lire_version_lot()
    # Le fichier existe dans le dépôt : les deux nombres doivent être lus
    assert isinstance(attendu_version, int) and attendu_version >= 1
    assert isinstance(attendu_lot, int) and attendu_lot >= 1

    res = client.get("/api/version")
    assert res.status_code == 200, res.text
    corps = res.json()
    assert corps["version"] == attendu_version
    assert corps["lot"] == attendu_lot
    assert corps["commit"]
    assert corps["demarrage"]
    # Libellé « Version 5.45 du JJ/MM/AAAA » : sans hash de commit
    jour = version_plateforme.DEMARRAGE.strftime("%d/%m/%Y")
    assert corps["libelle"] == f"Version {attendu_version}.{attendu_lot} du {jour}"
    assert corps["commit"] not in corps["libelle"]


def test_format_du_libelle():
    from datetime import datetime, timezone
    date = datetime(2026, 10, 3, 23, 30, tzinfo=timezone.utc)
    assert version_plateforme.libelle(5, 45, date) == "Version 5.45 du 03/10/2026"


def test_lecture_robuste_si_fichier_absent_ou_invalide(tmp_path):
    # Fichier absent : pas d'erreur, valeurs inconnues
    assert version_plateforme.lire_version_lot(tmp_path / "absent.js") == (None, None)
    # Fichier au bon format
    f = tmp_path / "version.js"
    f.write_text("export const VERSION = 12;\nexport const LOT = 57;\n", encoding="utf-8")
    assert version_plateforme.lire_version_lot(f) == (12, 57)


def test_hash_commit_prend_render_git_commit(monkeypatch):
    monkeypatch.setenv("RENDER_GIT_COMMIT", "0123456789abcdef0123456789abcdef01234567")
    assert version_plateforme.hash_commit_court() == "0123456"
