"""Traitement des vidéos du fil "Moments" avec ffmpeg.

Pour chaque vidéo publiée, on produit TROIS fichiers à partir de l'original :
  - la version CLAIRE, compressée (H.264 720p max, son AAC) -> stockage
    PRIVÉ : seuls les membres autorisés par l'auteur la reçoivent, via une
    URL temporaire (cf. routes/videos.py) ;
  - la version FLOUTÉE, entièrement floutée, basse résolution et SANS SON
    (la voix permet aussi d'identifier quelqu'un) -> stockage PUBLIC,
    c'est celle que tout le monde voit dans le fil ;
  - une VIGNETTE (image JPEG floutée) -> stockage PUBLIC, pour les grilles
    de vidéos des profils.

Le flou est appliqué côté serveur, dans les pixels : impossible de le
retirer depuis le navigateur (contrairement à un simple flou CSS).

ffmpeg est fourni par le paquet pip `imageio-ffmpeg` (binaire statique
embarqué) : aucune installation système n'est nécessaire, ni en local ni
sur Render.
"""
from __future__ import annotations

import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

# Durée maximale d'un traitement ffmpeg (sécurité contre un fichier piégé
# qui bloquerait le serveur indéfiniment).
FFMPEG_TIMEOUT_SECONDS = 240

DURATION_RE = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")


class VideoProcessingError(Exception):
    """Erreur lisible par l'utilisateur (message en français)."""


@dataclass
class ProcessedVideo:
    duration_seconds: float
    clear_mp4: bytes      # version claire compressée (privée)
    blurred_mp4: bytes    # version entièrement floutée (publique)
    poster_jpg: bytes     # vignette floutée (publique)


def ffmpeg_exe() -> str:
    """Chemin du binaire ffmpeg fourni par imageio-ffmpeg."""
    import imageio_ffmpeg

    return imageio_ffmpeg.get_ffmpeg_exe()


def _run(args: List[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [ffmpeg_exe(), "-hide_banner", "-nostdin", *args],
        capture_output=True,
        timeout=FFMPEG_TIMEOUT_SECONDS,
        check=False,
    )


def probe_duration(path: Path) -> Optional[float]:
    """Durée réelle de la vidéo, lue dans la sortie de `ffmpeg -i` (ffprobe
    n'est pas fourni par imageio-ffmpeg). None si illisible."""
    result = _run(["-i", str(path)])
    match = DURATION_RE.search(result.stderr.decode("utf-8", "ignore"))
    if not match:
        return None
    hours, minutes, seconds = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def process_video(source: Path, max_duration_seconds: int) -> ProcessedVideo:
    """Vérifie la durée puis produit les trois fichiers. Fonction BLOQUANTE
    (plusieurs secondes) : à appeler via asyncio.to_thread."""
    duration = probe_duration(source)
    if duration is None:
        raise VideoProcessingError("Fichier vidéo illisible ou corrompu")
    if duration > max_duration_seconds + 1:
        raise VideoProcessingError(f"Vidéo trop longue ({max_duration_seconds} secondes maximum)")

    with tempfile.TemporaryDirectory(prefix="maf-video-") as tmp:
        tmp_dir = Path(tmp)
        clear = tmp_dir / "clear.mp4"
        blurred = tmp_dir / "blurred.mp4"
        poster = tmp_dir / "poster.jpg"

        # 1) Version claire compressée : 720 px de large max, H.264 CRF 28,
        #    son AAC 96 kb/s, "faststart" pour démarrer la lecture avant la
        #    fin du téléchargement (indispensable pour un fil fluide).
        _check(_run([
            "-y", "-i", str(source),
            "-vf", "scale='min(720,iw)':-2",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "28", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "96k",
            "-movflags", "+faststart",
            str(clear),
        ]), "compression")

        # 2) Version entièrement floutée : on réduit fortement la définition
        #    PUIS on floute (flou "boîte" répété) — aucun détail du visage
        #    ne subsiste, même en agrandissant. Sans piste audio.
        _check(_run([
            "-y", "-i", str(clear),
            "-vf", "scale=180:-2,boxblur=luma_radius=12:luma_power=4,scale=360:-2",
            "-an",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "33", "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            str(blurred),
        ]), "floutage")

        # 3) Vignette : une image de la version floutée (à 0,5 s, ou la
        #    toute première si la vidéo est plus courte).
        seek = "0.5" if duration > 1 else "0"
        _check(_run(["-y", "-ss", seek, "-i", str(blurred), "-frames:v", "1", "-q:v", "4", str(poster)]), "vignette")

        return ProcessedVideo(
            duration_seconds=round(duration, 2),
            clear_mp4=clear.read_bytes(),
            blurred_mp4=blurred.read_bytes(),
            poster_jpg=poster.read_bytes(),
        )


def _check(result: subprocess.CompletedProcess, step: str) -> None:
    if result.returncode != 0:
        # Le détail technique reste dans les logs serveur, l'utilisateur
        # reçoit un message simple.
        tail = result.stderr.decode("utf-8", "ignore")[-500:]
        print(f"[video_processing] échec de l'étape {step} : {tail}")
        raise VideoProcessingError("Impossible de traiter cette vidéo, essayez un autre fichier")
