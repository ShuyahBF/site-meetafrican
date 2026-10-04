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


def libelle(version: int | None, lot: int | None, date: datetime,
            commit: str | None = None, detaille: bool = False) -> str:
    """Libellé de version (règle commune à toutes les plateformes, lot 54).

    - court (par défaut)  : « Version 14 · déployée le 04/10/2026 21:10 »
      → ni lot ni commit (connexion, portail) ;
    - détaillé (detaille) : « Version 14 · Lot 54 · 1a2b3c4 · déployée le 04/10/2026 21:10 »
      → réservé aux pages d'administration / paramétrage.
    Date au format JJ/MM/AAAA HH:MM, heure UTC (= heure de Ouagadougou)."""
    if version is None:
        return "Version inconnue"
    morceaux = [f"Version {version}"]
    if detaille:
        # Lot et commit uniquement dans le libellé détaillé
        if lot is not None:
            morceaux.append(f"Lot {lot}")
        if commit:
            morceaux.append(commit)
    morceaux.append(f"déployée le {date.astimezone(timezone.utc).strftime('%d/%m/%Y %H:%M')}")
    return " · ".join(morceaux)


def infos_version() -> dict:
    """Contenu de la réponse GET /api/version : `libelle` = libellé court (sans
    lot ni commit), `libelle_detaille` = libellé complet pour l'administration."""
    return {
        "version": VERSION,
        "lot": LOT,
        "commit": COMMIT,
        "demarrage": DEMARRAGE.isoformat(),
        "libelle": libelle(VERSION, LOT, DEMARRAGE),
        "libelle_detaille": libelle(VERSION, LOT, DEMARRAGE, COMMIT, detaille=True),
    }
