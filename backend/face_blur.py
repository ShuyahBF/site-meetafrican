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
# Photos : BANDEAU NOIR ou MASQUE SANITAIRE avec le logo beAuthentik
# ---------------------------------------------------------------------------
# Demandes du propriétaire (09/10/2026) :
#   « bande des yeux au nez afin qu'on ne soit pas reconnaissable », puis « Mettons le bandeau noir un peu
#   au-dessus du menton ou un masque sanitaire (au choix dans les paramètres) avec le logo de beAuthentik ».
# YuNet renvoie, pour chaque visage, 5 repères : œil droit, œil gauche, bout du nez, coins de la bouche.
# Toutes les formes sont calculées dans le REPÈRE DU VISAGE pour suivre l'inclinaison de la tête :
#   u = position le long de la ligne des yeux, v = position vers le bas du visage,
#   l'unité est l'écart entre les deux yeux (le visage garde ainsi les mêmes proportions quelle que soit sa taille).
# Le masquage est OPAQUE : rien n'est récupérable dessous.
STYLE_BANDEAU = "bandeau"
STYLE_MASQUE_SANITAIRE = "masque_sanitaire"
STYLES_MASQUE = (STYLE_BANDEAU, STYLE_MASQUE_SANITAIRE)

BANDE_COULEUR_BGR = (14, 12, 12)          # noir (très légèrement adouci), opaque
BANDE_MARGE_COTES = 0.75                  # débord de chaque côté des yeux (en écarts entre les yeux)
BANDE_MARGE_HAUT = 0.55                   # au-dessus des yeux : sourcils
BANDE_MARGE_SOUS_BOUCHE = 0.30            # sous la bouche : s'arrête un peu au-dessus du menton

# 09/10/2026 — « Un fond blanc pour le masque. Le logo ressortira mieux »
MASQUE_COULEUR_BGR = (250, 250, 250)      # blanc
MASQUE_PLIS_BGR = (200, 200, 200)         # plis et contour gris clair (le masque reste visible sur peau claire)
MASQUE_ELASTIQUE_BGR = (228, 228, 228)    # élastiques gris très clair

LOGO_PATH = Path(__file__).parent / "assets" / "images" / "logo-beauthentik.png"


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


class _RepereVisage:
    """Repère du visage : centre entre les yeux, axe des yeux (u), normale vers le menton (v), écart des yeux."""

    def __init__(self, reperes: np.ndarray):
        oeil_d, oeil_g = reperes[0], reperes[1]
        vecteur = oeil_g - oeil_d
        self.ecart = float(np.hypot(*vecteur))
        self.axe = vecteur / self.ecart
        self.normale = np.array([-self.axe[1], self.axe[0]])
        self.centre = (oeil_d + oeil_g) / 2
        self.angle_deg = float(np.degrees(np.arctan2(self.axe[1], self.axe[0])))   # inclinaison de la tête
        # Profondeurs (en écarts) du nez et de la bouche sous la ligne des yeux, avec des minimums réalistes
        bouche = (reperes[3] + reperes[4]) / 2
        self.v_nez = max(self._v(reperes[2]), 0.35)
        self.v_bouche = max(self._v(bouche), self.v_nez + 0.25)

    def _v(self, point: np.ndarray) -> float:
        return float(np.dot(point - self.centre, self.normale)) / self.ecart

    def point(self, u: float, v: float) -> np.ndarray:
        """Coordonnées (u, v) du visage → pixel de l'image."""
        return self.centre + (self.axe * u + self.normale * v) * self.ecart

    def poly(self, points_uv) -> np.ndarray:
        return np.array([[round(p[0]), round(p[1])] for p in (self.point(u, v) for u, v in points_uv)], dtype=np.int32)


def _cadre_vers_repere(cadre: Box) -> Optional[np.ndarray]:
    """Repères approximatifs déduits du cadre du visage quand ceux de YuNet sont inutilisables."""
    x0, y0, x1, y1 = cadre
    w, h = x1 - x0, y1 - y0
    if w < 4 or h < 4:
        return None
    return np.array([[x0 + 0.32 * w, y0 + 0.40 * h], [x0 + 0.68 * w, y0 + 0.40 * h], [x0 + 0.5 * w, y0 + 0.58 * h],
                     [x0 + 0.37 * w, y0 + 0.75 * h], [x0 + 0.63 * w, y0 + 0.75 * h]], dtype=np.float64)


def _repere(cadre: Box, reperes: np.ndarray) -> Optional[_RepereVisage]:
    if float(np.hypot(*(reperes[1] - reperes[0]))) < 2:
        reperes = _cadre_vers_repere(cadre)
        if reperes is None:
            return None
    return _RepereVisage(reperes)


def polygone_bande(cadre: Box, reperes: np.ndarray) -> np.ndarray:
    """Les 4 coins du bandeau noir : des sourcils jusqu'un peu au-dessus du menton, incliné comme les yeux."""
    r = _repere(cadre, reperes)
    if r is None:
        x0, y0, x1, y1 = cadre
        return np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1]], dtype=np.int32)
    cote = 0.5 + BANDE_MARGE_COTES
    bas = r.v_bouche + BANDE_MARGE_SOUS_BOUCHE
    return r.poly([(-cote, -BANDE_MARGE_HAUT), (cote, -BANDE_MARGE_HAUT), (cote, bas), (-cote, bas)])


def _formes_masque(r: _RepereVisage):
    """Masque sanitaire : contour (arête du nez → menton), 3 plis horizontaux et 4 élastiques vers les oreilles."""
    haut = r.v_nez * 0.55                     # sur l'arête du nez, juste sous les yeux
    vb = r.v_bouche
    bas = vb + 0.62                           # jusque sous le menton
    contour = r.poly([(-0.95, haut), (-0.35, haut - 0.10), (0.35, haut - 0.10), (0.95, haut),
                      (1.08, (haut + vb) / 2), (1.02, vb), (0.78, vb + 0.42), (0.35, bas), (-0.35, bas),
                      (-0.78, vb + 0.42), (-1.02, vb), (-1.08, (haut + vb) / 2)])
    plis = [r.poly([(-0.98, haut + (bas - haut) * k), (0.98, haut + (bas - haut) * k)]) for k in (0.30, 0.48, 0.66)]
    elastiques = [r.poly([(s * 0.95, haut + 0.04), (s * 1.42, -0.05)]) for s in (-1, 1)] + \
                 [r.poly([(s * 1.0, vb + 0.05), (s * 1.42, 0.35)]) for s in (-1, 1)]
    return contour, plis, elastiques, (haut + bas) / 2, bas - haut


def _coller_logo(image_pil, centre_xy, taille_px: int, angle_deg: float) -> None:
    """Logo beAuthentik collé au centre du masquage, tourné comme la tête (silencieux si le logo manque)."""
    from PIL import Image

    if taille_px < 8 or not LOGO_PATH.exists():
        return
    logo = Image.open(LOGO_PATH).convert("RGBA").resize((taille_px, taille_px), Image.LANCZOS)
    logo = logo.rotate(-angle_deg, resample=Image.BICUBIC, expand=True)
    x, y = int(centre_xy[0] - logo.width / 2), int(centre_xy[1] - logo.height / 2)
    image_pil.alpha_composite(logo, (x, y))


def masquer_visages(rgb: np.ndarray, style: str = STYLE_BANDEAU) -> Optional[np.ndarray]:
    """Photo (tableau RGB) dont chaque visage est caché par le BANDEAU NOIR ou le MASQUE SANITAIRE, logo au centre.
    None si aucun visage n'est détecté (l'appelant floute alors toute la photo : en cas de doute, tout est masqué)."""
    from PIL import Image

    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    visages = detect_faces_landmarks(bgr)
    if not visages:
        return None
    out = bgr.copy()
    logos = []                                  # (centre, taille, angle) : collés après le dessin des formes
    for cadre, reperes in visages:
        r = _repere(cadre, reperes)
        if style == STYLE_MASQUE_SANITAIRE and r is not None:
            contour, plis, elastiques, v_centre, hauteur = _formes_masque(r)
            epaisseur = max(1, round(r.ecart * 0.035))
            for e in elastiques:
                cv2.polylines(out, [e], False, MASQUE_ELASTIQUE_BGR, epaisseur, lineType=cv2.LINE_AA)
            cv2.fillPoly(out, [contour], MASQUE_COULEUR_BGR, lineType=cv2.LINE_AA)
            for p in plis:
                cv2.polylines(out, [p], False, MASQUE_PLIS_BGR, max(1, epaisseur // 2 + 1), lineType=cv2.LINE_AA)
            cv2.polylines(out, [contour], True, MASQUE_PLIS_BGR, epaisseur, lineType=cv2.LINE_AA)
            logos.append((r.point(0, v_centre), int(min(hauteur * 0.55, 0.85) * r.ecart), r.angle_deg))
        else:
            poly = polygone_bande(cadre, reperes)
            cv2.fillConvexPoly(out, poly, BANDE_COULEUR_BGR, lineType=cv2.LINE_AA)
            if r is not None:
                v_centre = (-BANDE_MARGE_HAUT + r.v_bouche + BANDE_MARGE_SOUS_BOUCHE) / 2
                logos.append((r.point(0, v_centre), int(0.75 * r.ecart), r.angle_deg))
    image = Image.fromarray(cv2.cvtColor(out, cv2.COLOR_BGR2RGB)).convert("RGBA")
    for centre, taille, angle in logos:
        _coller_logo(image, centre, taille, angle)
    return np.asarray(image.convert("RGB"))


def band_faces_in_photo(rgb: np.ndarray) -> Optional[np.ndarray]:
    """Compatibilité : bandeau noir (style par défaut)."""
    return masquer_visages(rgb, STYLE_BANDEAU)


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
