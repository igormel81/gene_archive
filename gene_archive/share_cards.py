"""Link previews for messengers: 1200×630 covers for the s/… pages (needs Pillow).

No text except the site's address in a corner: one picture fits every language; the
messenger prints the title and the description itself from og:title / og:description.
Cached in <site>/.cache/cards by the content of the photos: only new covers are drawn.
"""
import hashlib
import importlib.util
import json
from pathlib import Path

W, H = 1200, 630
BG, PAPER, MUTED, ACCENT = (245, 239, 228), (255, 253, 248), (122, 111, 99), (138, 75, 42)
FONTS = ("DejaVuSerif.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf", "Georgia.ttf",
         "/System/Library/Fonts/Supplemental/Georgia.ttf", "C:/Windows/Fonts/georgia.ttf")


def available():
    return importlib.util.find_spec("PIL") is not None


def _font(size):
    from PIL import ImageFont
    for name in FONTS:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _open(path):
    from PIL import Image, ImageOps
    im = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    im.thumbnail((1600, 1600))
    return im


def _framed(im, max_w, max_h, border=10):
    """A photo in a light frame with a soft shadow — like a print on a table."""
    from PIL import Image, ImageDraw, ImageFilter
    im = im.copy()
    im.thumbnail((max_w - 2 * border, max_h - 2 * border), Image.LANCZOS)
    card = Image.new("RGB", (im.width + 2 * border, im.height + 2 * border), PAPER)
    card.paste(im, (border, border))
    shadow = Image.new("RGBA", (card.width + 40, card.height + 40), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rectangle((20, 26, 20 + card.width, 26 + card.height), fill=(40, 25, 10, 90))
    return card, shadow.filter(ImageFilter.GaussianBlur(12))


def _mark(canvas, label):
    from PIL import ImageDraw
    d = ImageDraw.Draw(canvas)
    f = _font(22)
    w = d.textlength(label, font=f)
    d.text((W - w - 34, H - 46), label, font=f, fill=MUTED)
    d.rectangle((34, H - 34, 34 + 56, H - 31), fill=ACCENT)


def single(photo, label):
    """One photo: blurred and faded behind, the print in a frame in the middle."""
    from PIL import Image, ImageFilter, ImageOps
    im = _open(photo)
    bg = ImageOps.fit(im, (W, H), Image.LANCZOS).filter(ImageFilter.GaussianBlur(28))
    bg = Image.blend(bg, Image.new("RGB", (W, H), BG), 0.62)
    card, shadow = _framed(im, W - 160, H - 90)
    x, y = (W - card.width) // 2, (H - card.height) // 2 - 10
    bg.paste(shadow, (x - 20, y - 20), shadow)
    bg.paste(card, (x, y))
    _mark(bg, label)
    return bg


def collage(photos, label):
    """Several photos in a row, overlapping and slightly tilted — like prints spread on a table."""
    from PIL import Image
    photos = photos[:6]
    canvas = Image.new("RGB", (W, H), BG)
    if not photos:
        _mark(canvas, label)
        return canvas
    slot = (W - 120) / len(photos)
    tilt = [-4, 3, -2, 4, -3, 2]
    for i, p in enumerate(photos):
        card, shadow = _framed(_open(p), int(slot * 1.25), H - 150, border=8)
        layer = Image.new("RGBA", (card.width + 40, card.height + 40), (0, 0, 0, 0))
        layer.paste(shadow, (0, 0), shadow)
        layer.paste(card, (20, 20))
        layer = layer.rotate(tilt[i % len(tilt)], resample=Image.BICUBIC, expand=True)
        cx = 60 + slot * (i + 0.5)
        canvas.paste(layer, (int(cx - layer.width / 2), int((H - 40 - layer.height) / 2)), layer)
    _mark(canvas, label)
    return canvas


def make(out_dir, cache_dir, key, photos, label):
    """Draws s/img/<key>.jpg from one photo or several. Returns its path from the site root, or None."""
    photos = [Path(p) for p in photos if p and Path(p).is_file()]
    if not photos or not available():
        return None
    digest = hashlib.sha1(json.dumps([key, label, "v1"] + [hashlib.sha1(p.read_bytes()).hexdigest() for p in photos]).encode()).hexdigest()[:16]
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cached = cache_dir / f"{digest}.jpg"
    if not cached.exists():
        try:
            img = single(photos[0], label) if len(photos) == 1 else collage(photos, label)
        except OSError:   # an unreadable image: no cover rather than a failed build
            return None
        img.save(cached, quality=86, optimize=True, progressive=True)
    dest = Path(out_dir) / "s" / "img" / f"{key}.jpg"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(cached.read_bytes())
    return f"s/img/{key}.jpg"
