"""Floutage du VISAGE uniquement (photos masquées et vidéos publiques).

Objectif : pour matcher, on doit pouvoir voir la silhouette, le style, le
cadre… mais pas reconnaître la personne. On détecte donc les visages et on
ne floute QUE ces zones ; le reste de l'image reste net.

Détecteur : YuNet (OpenCV, modèle ONNX de 230 Ko embarqué dans
assets/models/, licence MIT). Choisi plutôt que les anciens détecteurs
"Haar" d'OpenCV, nettement moins fiables sur les peaux foncées et en
faible lumière — essentiel pour notre public.

Principe de sécurité : EN CAS DE DOUTE, TOUT RESTE FLOUTÉ.
  - photo sans visage détecté      -> photo entièrement floutée (ancien mode) ;
  - image de vidéo sans visage détecté à proximité (ni sur l'échantillon
    précédent, ni sur le suivant) -> image entièrement floutée ;
  - chaque zone de visage est agrandie (cheveux, oreilles, menton) et
    pixelisée PUIS floutée : impossible à "défloutter".
Limite assumée : un visage que le détecteur ne voit pas du tout (très de
profil, très petit, masqué) sur une image où un AUTRE visage est détecté
reste visible. Le signalement et la modération restent le filet de sécurité.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import List, Optional, Tuple

import cv2
import numpy as np

MODEL_PATH = Path(__file__).parent / "assets" / "models" / "face_detection_yunet_2023mar.onnx"

# Seuil de confiance volontairement BAS : on préfère flouter une zone en
# trop (fausse alerte) que rater un visage.
SCORE_THRESHOLD = 0.5
# Largeur maximale de l'image envoyée au détecteur (au-delà : plus lent,
# sans gain utile pour des visages de taille normale).
DETECT_MAX_WIDTH = 640
# Agrandissement de la zone détectée (fraction de la largeur / hauteur du
# visage) : le haut est plus agrandi pour couvrir front et cheveux.
MARGIN_SIDES, MARGIN_TOP, MARGIN_BOTTOM = 0.35, 0.55, 0.30
# Vidéos : nombre d'images analysées par seconde (les images intermédiaires
# utilisent les zones de l'échantillon précédent ET du suivant).
VIDEO_DETECTIONS_PER_SECOND = 6
# Vidéos publiques : largeur de sortie et images/seconde maximales.
VIDEO_OUTPUT_MAX_WIDTH = 480
VIDEO_MAX_FPS = 30

Box = Tuple[int, int, int, int]  # (x0, y0, x1, y1) en pixels


def detect_faces(bgr: np.ndarray) -> List[Box]:
    """Zones de visage (déjà agrandies) sur une image BGR (format OpenCV)."""
    h, w = bgr.shape[:2]
    scale = min(1.0, DETECT_MAX_WIDTH / w)
    small = cv2.resize(bgr, (max(1, int(w * scale)), max(1, int(h * scale)))) if scale < 1 else bgr
    sh, sw = small.shape[:2]
    # Un détecteur par appel : l'objet OpenCV n'est pas partageable entre threads.
    detector = cv2.FaceDetectorYN.create(str(MODEL_PATH), "", (sw, sh), SCORE_THRESHOLD, 0.3, 50)
    _, faces = detector.detect(small)
    boxes: List[Box] = []
    for face in faces if faces is not None else []:
        x, y, fw, fh = (float(v) / scale for v in face[:4])
        x0 = int(max(0, x - fw * MARGIN_SIDES))
        y0 = int(max(0, y - fh * MARGIN_TOP))
        x1 = int(min(w, x + fw * (1 + MARGIN_SIDES)))
        y1 = int(min(h, y + fh * (1 + MARGIN_BOTTOM)))
        if x1 > x0 and y1 > y0:
            boxes.append((x0, y0, x1, y1))
    return boxes


def _obliterate(region: np.ndarray) -> np.ndarray:
    """Pixelisation (8 blocs de large) puis flou gaussien : aucun détail
    récupérable, même en agrandissant."""
    h, w = region.shape[:2]
    tiny = cv2.resize(region, (8, max(1, round(8 * h / w))), interpolation=cv2.INTER_AREA)
    big = cv2.resize(tiny, (w, h), interpolation=cv2.INTER_LINEAR)
    k = max(3, (min(w, h) // 4) | 1)  # taille de noyau impaire
    return cv2.GaussianBlur(big, (k, k), 0)


def blur_boxes(bgr: np.ndarray, boxes: List[Box]) -> np.ndarray:
    out = bgr.copy()
    for x0, y0, x1, y1 in boxes:
        out[y0:y1, x0:x1] = _obliterate(out[y0:y1, x0:x1])
    return out


def blur_everything(bgr: np.ndarray) -> np.ndarray:
    """Image entièrement floutée (repli quand aucun visage n'est trouvé)."""
    h, w = bgr.shape[:2]
    tiny = cv2.resize(bgr, (max(1, w // 16), max(1, h // 16)), interpolation=cv2.INTER_AREA)
    big = cv2.resize(tiny, (w, h), interpolation=cv2.INTER_LINEAR)
    return cv2.GaussianBlur(big, (0, 0), max(4, w / 60))


# ---------------------------------------------------------------------------
# Photos
# ---------------------------------------------------------------------------

def blur_faces_in_photo(rgb: np.ndarray) -> Optional[np.ndarray]:
    """Photo (tableau RGB) avec visages floutés, ou None si aucun visage
    n'est détecté (l'appelant applique alors le floutage complet)."""
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    boxes = detect_faces(bgr)
    if not boxes:
        return None
    return cv2.cvtColor(blur_boxes(bgr, boxes), cv2.COLOR_BGR2RGB)


# ---------------------------------------------------------------------------
# Photos : BANDE opaque des yeux au nez (demande du propriétaire, 09/10/2026)
# ---------------------------------------------------------------------------
# « L'IA devait afficher ma photo avec une bande des yeux au nez afin qu'on ne soit pas reconnaissable. »
# YuNet renvoie, pour chaque visage, 5 repères : œil droit, œil gauche, bout du nez, coins de la bouche.
# La bande couvre des sourcils jusqu'au bout du nez, un peu plus large que les deux yeux, et suit
# l'inclinaison de la tête (angle de la ligne des yeux). Elle est OPAQUE : rien n'est récupérable dessous.
BANDE_COULEUR_BGR = (12, 4, 20)    # aubergine très foncé (couleur de la marque), opaque
BANDE_MARGE_COTES = 0.75           # débord de chaque côté des yeux (fraction de l'écart entre les yeux)
BANDE_MARGE_HAUT = 0.55            # au-dessus des yeux : sourcils (fraction de l'écart entre les yeux)
BANDE_MARGE_BAS = 0.30             # sous le bout du nez (fraction de l'écart entre les yeux)


def detect_faces_landmarks(bgr: np.ndarray) -> List[Tuple[Box, np.ndarray]]:
    """Visages détectés avec leurs 5 repères (en pixels de l'image d'origine) : [(cadre brut, repères 5x2)]."""
    h, w = bgr.shape[:2]
    scale = min(1.0, DETECT_MAX_WIDTH / w)
    small = cv2.resize(bgr, (max(1, int(w * scale)), max(1, int(h * scale)))) if scale < 1 else bgr
    sh, sw = small.shape[:2]
    detector = cv2.FaceDetectorYN.create(str(MODEL_PATH), "", (sw, sh), SCORE_THRESHOLD, 0.3, 50)
    _, faces = detector.detect(small)
    out: List[Tuple[Box, np.ndarray]] = []
    for face in faces if faces is not None else []:
        x, y, fw, fh = (float(v) / scale for v in face[:4])
        reperes = np.array(face[4:14], dtype=np.float64).reshape(5, 2) / scale
        out.append(((int(x), int(y), int(x + fw), int(y + fh)), reperes))
    return out


def polygone_bande(cadre: Box, reperes: np.ndarray) -> np.ndarray:
    """Les 4 coins de la bande (yeux → nez) d'un visage, inclinée comme la ligne des yeux."""
    oeil_d, oeil_g, nez = reperes[0], reperes[1], reperes[2]
    vecteur = oeil_g - oeil_d
    ecart = float(np.hypot(*vecteur))
    x0, y0, x1, y1 = cadre
    if ecart < 2:   # repères inutilisables : bande horizontale déduite du cadre du visage
        hauteur = y1 - y0
        return np.array([[x0, y0 + 0.18 * hauteur], [x1, y0 + 0.18 * hauteur],
                         [x1, y0 + 0.68 * hauteur], [x0, y0 + 0.68 * hauteur]], dtype=np.int32)
    axe = vecteur / ecart                       # direction de la ligne des yeux
    normale = np.array([-axe[1], axe[0]])       # vers le bas du visage
    centre_yeux = (oeil_d + oeil_g) / 2
    descente_nez = max(float(np.dot(nez - centre_yeux, normale)), 0.35 * ecart)
    gauche = oeil_d - axe * ecart * BANDE_MARGE_COTES
    droite = oeil_g + axe * ecart * BANDE_MARGE_COTES
    haut = -normale * ecart * BANDE_MARGE_HAUT
    bas = normale * (descente_nez + ecart * BANDE_MARGE_BAS)
    coins = [gauche + haut, droite + haut, droite + bas, gauche + bas]
    return np.array([[round(c[0]), round(c[1])] for c in coins], dtype=np.int32)


def band_faces_in_photo(rgb: np.ndarray) -> Optional[np.ndarray]:
    """Photo (tableau RGB) avec une bande opaque des yeux au nez sur chaque visage, ou None si aucun
    visage n'est détecté (l'appelant applique alors le floutage complet : en cas de doute, tout est masqué)."""
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    visages = detect_faces_landmarks(bgr)
    if not visages:
        return None
    out = bgr.copy()
    for cadre, reperes in visages:
        cv2.fillConvexPoly(out, polygone_bande(cadre, reperes), BANDE_COULEUR_BGR, lineType=cv2.LINE_AA)
    return cv2.cvtColor(out, cv2.COLOR_BGR2RGB)


# ---------------------------------------------------------------------------
# Vidéos
# ---------------------------------------------------------------------------

_DIMS_RE = re.compile(r"Video:.*?(\d{2,5})x(\d{2,5})")
_FPS_RE = re.compile(r"(\d+(?:\.\d+)?) fps")


def _probe(ffmpeg: str, src: Path) -> Tuple[int, int, float]:
    err = subprocess.run([ffmpeg, "-hide_banner", "-i", str(src)], capture_output=True).stderr.decode("utf-8", "ignore")
    dims = _DIMS_RE.search(err)
    if not dims:
        raise RuntimeError("dimensions vidéo introuvables")
    fps_match = _FPS_RE.search(err)
    fps = float(fps_match.group(1)) if fps_match else 30.0
    return int(dims.group(1)), int(dims.group(2)), min(max(fps, 1.0), VIDEO_MAX_FPS)


def _decode(ffmpeg: str, src: Path, w: int, h: int, fps: float, timeout: int):
    """Générateur d'images BGR décodées par ffmpeg (taille w x h, fps constant)."""
    proc = subprocess.Popen(
        [ffmpeg, "-hide_banner", "-nostdin", "-i", str(src),
         "-vf", f"fps={fps},scale={w}:{h}", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    )
    frame_size = w * h * 3
    try:
        while True:
            buf = proc.stdout.read(frame_size)
            if len(buf) < frame_size:
                break
            yield np.frombuffer(buf, np.uint8).reshape(h, w, 3)
    finally:
        proc.stdout.close()
        proc.wait(timeout=timeout)


def render_face_blurred_video(ffmpeg: str, src: Path, dst: Path, timeout: int = 240) -> dict:
    """Produit la version PUBLIQUE d'une vidéo : visages floutés, reste net,
    sans son. Deux passes : 1) détection sur ~6 images/s ; 2) rendu image
    par image. Renvoie des statistiques (images, images entièrement
    floutées, visages détectés)."""
    iw, ih, fps = _probe(ffmpeg, src)
    w = min(VIDEO_OUTPUT_MAX_WIDTH, iw) // 2 * 2
    h = max(2, round(ih * w / iw / 2) * 2)
    step = max(1, round(fps / VIDEO_DETECTIONS_PER_SECOND))

    # Passe 1 : détection sur les images échantillons (0, step, 2*step…)
    detections: dict[int, List[Box]] = {}
    for i, frame in enumerate(_decode(ffmpeg, src, w, h, fps, timeout)):
        if i % step == 0:
            detections[i] = detect_faces(frame)

    # Passe 2 : rendu. Image i -> zones de l'échantillon précédent + suivant ;
    # aucune zone des deux côtés -> image entièrement floutée.
    encoder = subprocess.Popen(
        [ffmpeg, "-hide_banner", "-nostdin", "-y",
         "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{w}x{h}", "-r", f"{fps}", "-i", "-",
         "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "30", "-pix_fmt", "yuv420p",
         "-movflags", "+faststart", str(dst)],
        stdin=subprocess.PIPE, stderr=subprocess.DEVNULL,
    )
    stats = {"frames": 0, "fully_blurred_frames": 0, "frames_with_faces": 0}
    try:
        for i, frame in enumerate(_decode(ffmpeg, src, w, h, fps, timeout)):
            prev_sample = (i // step) * step
            boxes = detections.get(prev_sample, []) + detections.get(prev_sample + step, [])
            if boxes:
                out = blur_boxes(frame, boxes)
                stats["frames_with_faces"] += 1
            else:
                out = blur_everything(frame)
                stats["fully_blurred_frames"] += 1
            encoder.stdin.write(np.ascontiguousarray(out).tobytes())
            stats["frames"] += 1
    finally:
        encoder.stdin.close()
        encoder.wait(timeout=timeout)
    if encoder.returncode != 0 or stats["frames"] == 0:
        raise RuntimeError("encodage de la vidéo floutée impossible")
    return stats
