"""Tests du signal de présence SAWALI (règle 4) — sans aucun accès réseau."""
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import presence_sawali  # noqa: E402


def test_corps_signal_complet():
    # Corps attendu : champs obligatoires et dates en ISO UTC
    d = datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc)
    corps = presence_sawali.corps_signal("18", "beauthentik-api", d, d)
    assert corps["application"] == "beAuthentik"
    assert corps["version"] == "18"
    assert corps["machine"] == "beauthentik-api"
    assert corps["utilisateur"] == "serveur"
    assert corps["site"] == "beauthentik.net"
    assert corps["systeme"].startswith("Render · Python ")
    assert corps["deploye_le"] == "2026-10-06T12:00:00+00:00"
    assert corps["demarre_le"] == "2026-10-06T12:00:00+00:00"


def test_corps_signal_sans_date_deploiement():
    # Date de déploiement inconnue → null
    d = datetime(2026, 10, 6, tzinfo=timezone.utc)
    assert presence_sawali.corps_signal("x", "m", None, d)["deploye_le"] is None


def test_entete_et_desactivation(monkeypatch):
    # En-tête X-Cle-Loois uniquement si la variable existe
    monkeypatch.delenv("LOOIS_SUPPORT_CLE", raising=False)
    assert presence_sawali.entetes() == {}
    monkeypatch.setenv("LOOIS_SUPPORT_CLE", "cle-factice")
    assert presence_sawali.entetes() == {"X-Cle-Loois": "cle-factice"}
    # PRESENCE_SAWALI=0 désactive le signal
    monkeypatch.setenv("PRESENCE_SAWALI", "0")
    assert presence_sawali.presence_active() is False


def test_version_identique_au_site():
    # Même version que frontend/src/version.js
    assert presence_sawali.version_deployee() == str(presence_sawali.version_plateforme.VERSION)
