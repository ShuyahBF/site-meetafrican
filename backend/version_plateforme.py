"""Version et lot de la plateforme, exposés par GET /api/version.

SOURCE UNIQUE : le fichier frontend/src/version.js (constantes VERSION et LOT).
Ce module ne fait que le RELIRE au démarrage du serveur : il n'y a donc
qu'un seul endroit à modifier à chaque déploiement.

Attention (Render) : le service backend a `rootDir: backend` et ne se
redéploie QUE si un fichier de backend/ change. Lors d'un déploiement qui ne
touche que le site (frontend), le backend garde donc la version/le lot de SON
dernier démarrage. C'est voulu : /api/version dit quelle version du code
tourne côté API (avec son propre hash de commit), tandis que la mention
affichée sur le site vient du frontend (toujours reconstruit, puisque
version.js change à chaque déploiement).
"""
from __future__ import annotations

import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

# Emplacement du fichier source unique (dépôt complet : backend/ et frontend/
# sont voisins ; Render clone tout le dépôt même avec rootDir).
FICHIER_VERSION = Path(__file__).resolve().parent.parent / "frontend" / "src" / "version.js"

# Heure de démarrage de CE processus (= date du déploiement du backend)
DEMARRAGE = datetime.now(timezone.utc)


def lire_version_lot(fichier: Path = FICHIER_VERSION) -> tuple[int | None, int | None]:
    """Lit `export const VERSION = N;` et `export const LOT = N;` dans version.js.
    Renvoie (None, None) si le fichier est absent ou illisible (jamais d'erreur :
    l'API doit démarrer même sans le dossier frontend)."""
    try:
        texte = fichier.read_text(encoding="utf-8")
    except OSError:
        return None, None

    def _nombre(nom: str) -> int | None:
        m = re.search(rf"export\s+const\s+{nom}\s*=\s*(\d+)\s*;", texte)
        return int(m.group(1)) if m else None

    return _nombre("VERSION"), _nombre("LOT")


def hash_commit_court() -> str:
    """Hash court (7 caractères) du commit déployé : RENDER_GIT_COMMIT sur
    Render, sinon `git rev-parse`, sinon "dev"."""
    complet = os.environ.get("RENDER_GIT_COMMIT", "").strip()
    if complet:
        return complet[:7]
    try:
        sortie = subprocess.run(
            ["git", "rev-parse", "--short=7", "HEAD"],
            cwd=Path(__file__).resolve().parent,
            capture_output=True, text=True, timeout=3, check=True,
        )
        return sortie.stdout.strip() or "dev"
    except (OSError, subprocess.SubprocessError):
        return "dev"


# Valeurs figées au démarrage (lecture disque / git une seule fois)
VERSION, LOT = lire_version_lot()
COMMIT = hash_commit_court()


def infos_version() -> dict:
    """Contenu de la réponse GET /api/version."""
    morceaux = []
    if VERSION is not None:
        morceaux.append(f"Version {VERSION}")
    if LOT is not None:
        morceaux.append(f"Lot {LOT}")
    morceaux.append(COMMIT)
    return {
        "version": VERSION,
        "lot": LOT,
        "commit": COMMIT,
        "demarrage": DEMARRAGE.isoformat(),
        "libelle": " · ".join(morceaux),
    }
