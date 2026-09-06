"""Traitement des photos de profil approuvées :

  - `apply_watermark` : filigrane discret "bAuthentik" en bas de l'image,
    appliqué à toute photo dès son approbation (IA ou admin) — dissuade la
    réutilisation des photos hors du site.
  - `apply_face_mask` : version masquée servie aux profils SANS abonnement
    actif (voir routes/matching.py:_mask_photos_for_viewer). Limite réelle
    assumée : sans détection de visage (aucune dépendance de ce type dans le
    projet), on ne trace pas précisément yeux/nez/bouche — on applique un
    flou fort sur toute l'image plus un bandeau de marque centré, ce qui
    atteint le même objectif pratique (impossible de reconnaître la
    personne) sans ajouter de dépendance de vision par ordinateur.

Police utilisée : Plus Jakarta Sans (police de marque du site), embarquée
dans assets/fonts/ pour ne pas dépendre des polices système — absentes par
défaut sur l'environnement de build Render.
"""
from __future__ import annotations

import io
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

FONT_PATH = Path(__file__).parent / "assets" / "fonts" / "PlusJakartaSans-Bold.ttf"
BRAND_TEXT = "bAuthentik"


def _font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_PATH), size)


def _load_rgb(image_bytes: bytes) -> Image.Image:
    img = Image.open(io.BytesIO(image_bytes))
    return img.convert("RGB")


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


def apply_face_mask(image_bytes: bytes) -> bytes:
    """Version floutée + bandeau de marque, servie aux profils visiteurs
    sans abonnement actif (voir limite documentée en tête de fichier)."""
    img = _load_rgb(image_bytes)
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
