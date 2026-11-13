"""Photo processing: phone photo in → display JPEG + thumbnail JPEG out.

Builds on meal-planner's Recipe._process_image (exif_transpose → RGB →
resize → JPEG q85), with three additions for studio photos:

* two sizes (display + thumbnail),
* random UUID filenames, so photo URLs can't be guessed — this matters once
  a public gallery exists and private projects' photos must stay private,
* the shoot time is read from EXIF *before* re-encoding. Re-encoding without
  passing exif= drops all EXIF, including GPS location, which is intended.

HEIC: if the optional `pillow-heif` package is installed, HEIC files decode
too. iOS Safari normally converts HEIC to JPEG on upload, so it's a fallback.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO

from django.conf import settings
from django.core.files.base import ContentFile
from django.utils import timezone
from PIL import Image, ImageOps, UnidentifiedImageError

try:  # optional HEIC support
    from pillow_heif import register_heif_opener

    register_heif_opener()
    HEIC_SUPPORTED = True
except ImportError:  # pragma: no cover - depends on environment
    HEIC_SUPPORTED = False

# EXIF tags
_EXIF_IFD = 0x8769
_DATETIME_ORIGINAL = 36867
_DATETIME = 306


class PhotoError(ValueError):
    """The upload isn't an image we can read."""


@dataclass
class ProcessedPhoto:
    display: ContentFile
    thumbnail: ContentFile
    taken_at: datetime | None
    width: int
    height: int


def _taken_at(image):
    """Shoot time from EXIF, as an aware datetime in the site's time zone."""
    try:
        exif = image.getexif()
    except Exception:  # corrupt EXIF shouldn't block an upload
        return None
    raw = exif.get_ifd(_EXIF_IFD).get(_DATETIME_ORIGINAL) or exif.get(_DATETIME)
    if not raw:
        return None
    try:
        naive = datetime.strptime(str(raw).strip("\x00 "), "%Y:%m:%d %H:%M:%S")
    except ValueError:
        return None
    # Phones write local wall-clock time without a zone; treat it as ours.
    return timezone.make_aware(naive, timezone.get_default_timezone())


def _jpeg(image, max_size):
    copy = image.copy()
    copy.thumbnail((max_size, max_size))  # never enlarges
    buffer = BytesIO()
    copy.save(buffer, format="JPEG", quality=85, optimize=True)
    return buffer.getvalue()


def process_photo(upload):
    """Turn an uploaded file into display + thumbnail JPEGs with UUID names."""
    try:
        image = Image.open(upload)
        image.load()
    except (UnidentifiedImageError, OSError) as exc:
        hint = "" if HEIC_SUPPORTED else " (HEIC photos: set iPhone Camera → Formats → Most Compatible)"
        raise PhotoError(f"Couldn't read {getattr(upload, 'name', 'that file')} as an image{hint}.") from exc

    taken_at = _taken_at(image)
    image = ImageOps.exif_transpose(image)  # bake rotation into pixels
    image = image.convert("RGB")

    name = uuid.uuid4().hex
    display = ContentFile(_jpeg(image, settings.PHOTO_DISPLAY_SIZE), name=f"{name}.jpg")
    thumbnail = ContentFile(_jpeg(image, settings.PHOTO_THUMB_SIZE), name=f"{name}.jpg")
    width, height = image.size
    return ProcessedPhoto(display, thumbnail, taken_at, width, height)
