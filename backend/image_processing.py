"""Traitement des photos de profil approuvées :

  - `apply_watermark` : filigrane discret "beAuthentik" en bas de l'image,
    appliqué à toute photo dès son approbation (IA ou admin) — dissuade la
    réutilisation des photos hors du site.
  - `apply_face_mask` : version masquée servie aux membres qui n'ont PAS
    matché avec le propriétaire de la photo (voir routes/matching.py:
    _mask_photos_for_viewer). Le VISAGE est détecté (face_blur.py) puis caché
    par un bandeau noir ou un masque sanitaire avec le logo beAuthentik (au
    choix dans Admin > Paramètres) : silhouette et style restent visibles.
    Si aucun visage n'est détecté, par sécurité, toute l'image est floutée
    avec un bandeau de marque.

Police utilisée : Plus Jakarta Sans (police de marque du site), embarquée
dans assets/fonts/ pour ne pas dépendre des polices système — absentes par
défaut sur l'environnement de build Render.
"""
from __future__ import annotations

import io
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

FONT_PATH = Path(__file__).parent / "assets" / "fonts" / "PlusJakartaSans-Bold.ttf"
BRAND_TEXT = "beAuthentik"


def _font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_PATH), size)


def _load_rgb(image_bytes: bytes) -> Image.Image:
    img = Image.open(io.BytesIO(image_bytes))
    # Photos de téléphone : on applique l'orientation EXIF (sinon l'image
    # peut être couchée et le visage non détecté).
    return ImageOps.exif_transpose(img).convert("RGB")


def _to_jpeg_bytes(img: Image.Image, quality: int = 85) -> bytes:
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=quality, optimize=True)
    return buf.getvalue()


def apply_watermark(image_bytes: bytes) -> bytes:
    """Filigrane semi-transparent en bas de l'image, taille proportionnelle
    à la largeur pour rester lisible aussi bien sur une vignette que sur un
    affichage plein écran."""
    img = _load_rgb(image_bytes)
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    font_size = max(14, img.width // 22)
    font = _font(font_size)
    margin = font_size // 2
    text_w = draw.textlength(BRAND_TEXT, font=font)
    x = img.width - text_w - margin
    y = img.height - font_size - margin

    # Léger contour sombre pour rester lisible sur fond clair ET foncé.
    for dx, dy in ((-1, -1), (-1, 1), (1, -1), (1, 1)):
        draw.text((x + dx, y + dy), BRAND_TEXT, font=font, fill=(0, 0, 0, 110))
    draw.text((x, y), BRAND_TEXT, font=font, fill=(255, 255, 255, 200))

    watermarked = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    return _to_jpeg_bytes(watermarked)


# Version du masquage : les photos masquées plus anciennes (ou d'une autre
# version) sont régénérées automatiquement (voir media_migration.py).
# La version dépend du STYLE choisi dans les paramètres : changer de style fait régénérer toutes les photos.
STYLE_PAR_DEFAUT = "bandeau"
STYLES_MASQUE = ("bandeau", "masque_sanitaire")


def mask_version(style: str = STYLE_PAR_DEFAUT) -> str:
    """Identifiant de version du masquage pour un style (ex. « bandeau-v2 », « masque_sanitaire-v2 »)."""
    return f"{style if style in STYLES_MASQUE else STYLE_PAR_DEFAUT}-v3"   # v3 : masque sanitaire blanc


MASK_VERSION = mask_version()   # 09/10/2026 : bandeau noir jusqu'au-dessus du menton, avec le logo


def apply_face_mask(image_bytes: bytes, style: str = STYLE_PAR_DEFAUT) -> bytes:
    """Version servie aux membres sans match : BANDEAU NOIR (sourcils → un peu au-dessus du menton) ou MASQUE
    SANITAIRE, logo beAuthentik au centre ; image entièrement floutée si aucun visage n'est détecté."""
    img = _load_rgb(image_bytes)
    try:
        import numpy as np

        from face_blur import masquer_visages

        faces_blurred = masquer_visages(np.asarray(img), style)
    except Exception as exc:  # détecteur indisponible -> repli sûr
        print(f"[image_processing] détection de visage impossible : {exc}")
        faces_blurred = None
    if faces_blurred is not None:
        return _face_only_mask(Image.fromarray(faces_blurred))
    return _full_mask(img)


def _face_only_mask(img: Image.Image) -> bytes:
    """Visage déjà masqué (bandeau ou masque sanitaire) : on ajoute une petite étiquette en bas."""
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    font = _font(max(12, img.width // 28))
    text = "Visage masqué · visible après un match"
    text_w = draw.textlength(text, font=font)
    pad = max(6, img.width // 60)
    x0 = (img.width - text_w) / 2 - pad
    y0 = img.height - font.size - 3 * pad
    draw.rounded_rectangle(
        [(x0, y0), (x0 + text_w + 2 * pad, y0 + font.size + 2 * pad)],
        radius=font.size, fill=(20, 4, 12, 170),
    )
    draw.text((x0 + pad, y0 + pad * 0.8), text, font=font, fill=(255, 255, 255, 235))
    return _to_jpeg_bytes(Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB"))


def _full_mask(img: Image.Image) -> bytes:
    """Repli : image entièrement floutée + bandeau de marque centré."""
    blurred = img.filter(ImageFilter.GaussianBlur(radius=max(12, img.width // 25)))

    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    band_h = int(img.height * 0.22)
    band_y = (img.height - band_h) // 2
    draw.rectangle([(0, band_y), (img.width, band_y + band_h)], fill=(20, 4, 12, 190))

    font = _font(max(16, img.width // 12))
    text_w = draw.textlength(BRAND_TEXT, font=font)
    draw.text(
        ((img.width - text_w) / 2, band_y + band_h / 2 - font.size / 2),
        BRAND_TEXT, font=font, fill=(255, 255, 255, 235),
    )

    sub_font = _font(max(11, img.width // 26))
    sub_text = "Abonnez-vous pour voir le profil"
    sub_w = draw.textlength(sub_text, font=sub_font)
    draw.text(
        ((img.width - sub_w) / 2, band_y + band_h / 2 + font.size / 2 + 4),
        sub_text, font=sub_font, fill=(255, 255, 255, 210),
    )

    masked = Image.alpha_composite(blurred.convert("RGBA"), overlay).convert("RGB")
    return _to_jpeg_bytes(masked)
