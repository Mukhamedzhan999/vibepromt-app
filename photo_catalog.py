"""Download only licensed photographs from the curated PDF audit catalog."""
import io
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from pathlib import Path
from threading import Lock
from zipfile import ZIP_STORED, ZipFile

import requests
from PIL import Image, ImageOps

CATALOG_PATH = Path(__file__).with_name("static") / "audit-photo-catalog.json"
CATALOG = {item["id"]: item for item in json.loads(CATALOG_PATH.read_text(encoding="utf-8"))}
LOGGER = logging.getLogger(__name__)
ASSET_LIMIT = 20 * 1024 * 1024
PACK_PHOTO_LIMIT = 300_000
_PHOTO_LOCKS = {photo_id: Lock() for photo_id in CATALOG}
_PHOTO_WORKERS = ThreadPoolExecutor(max_workers=6, thread_name_prefix="web-photo")


def get_photo(photo_id):
    with _PHOTO_LOCKS[photo_id]:
        return _get_photo(photo_id)


def collect_assets(loader, items):
    return list(_PHOTO_WORKERS.map(loader, items))


@lru_cache(maxsize=32)
def _get_photo(photo_id):
    entry = CATALOG[photo_id]
    urls = (entry["previewUrl"], entry["imageUrl"])
    for url in urls:
        if not url.startswith("https://upload.wikimedia.org/wikipedia/commons/"):
            continue
        try:
            with requests.get(
                url,
                timeout=(3, 6),
                allow_redirects=False,
                stream=True,
                headers={"User-Agent": "VibePromptAI/1.0 (https://vibeprompt-ai-eta.vercel.app/)"},
            ) as response:
                if response.status_code != 200 or not response.headers.get("Content-Type", "").startswith("image/"):
                    continue
                data = bytearray()
                for chunk in response.iter_content(65536):
                    data.extend(chunk)
                    if len(data) > ASSET_LIMIT:
                        break
                if not data or len(data) > ASSET_LIMIT:
                    continue
            with Image.open(io.BytesIO(data), formats=("JPEG", "PNG", "WEBP")) as original:
                if original.width * original.height > 24_000_000:
                    continue
                image = ImageOps.exif_transpose(original).convert("RGB")
                for size, quality in ((1920, 88), (1500, 78), (1200, 72), (800, 68)):
                    image.thumbnail((size, size), Image.Resampling.LANCZOS)
                    jpeg = io.BytesIO()
                    image.save(jpeg, format="JPEG", quality=quality, optimize=True)
                    if jpeg.tell() <= PACK_PHOTO_LIMIT:
                        return jpeg.getvalue()
        except (requests.RequestException, OSError, ValueError, Image.DecompressionBombError) as exc:
            LOGGER.info("Catalog photo %s unavailable: %s", photo_id, type(exc).__name__)
    raise LookupError(photo_id)


def available_photo(photo_id):
    try:
        return get_photo(photo_id)
    except LookupError:
        return None


def build_photo_pack(ids):
    """Return a ZIP and counts. If no assets could be retrieved, return no archive."""
    ids = list(dict.fromkeys(photo_id for photo_id in ids if photo_id in CATALOG))
    if not ids:
        return None, 0, 0
    assets = collect_assets(available_photo, ids)
    count = sum(asset is not None for asset in assets)
    if not count:
        return None, 0, len(ids)
    archive = io.BytesIO()
    credits = []
    with ZipFile(archive, "w", ZIP_STORED) as zip_file:
        for photo_id, image in zip(ids, assets):
            entry = CATALOG[photo_id]
            filename = photo_id + ".jpg"
            if image:
                zip_file.writestr(filename, image)
            credits.append(
                f'{filename} — {"included, resized and re-encoded" if image else "unavailable in this ZIP"}\n'
                f'{entry["subject"]}\n{entry["credit"]} · {entry["license"]} · {entry["licenseUrl"]}\n'
                f'Source: {entry["sourceUrl"]}\nOriginal: {entry["imageUrl"]}\n'
            )
        zip_file.writestr("CREDITS.txt", "\n".join(credits))
    return archive.getvalue(), count, len(ids)
