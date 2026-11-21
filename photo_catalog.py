"""Download only licensed photographs from the curated PDF audit catalog."""
import io
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from pathlib import Path
from zipfile import ZIP_STORED, ZipFile

import fitz
import requests

CATALOG_PATH = Path(__file__).with_name("static") / "audit-photo-catalog.json"
CATALOG = {item["id"]: item for item in json.loads(CATALOG_PATH.read_text(encoding="utf-8"))}
LOGGER = logging.getLogger(__name__)
ASSET_LIMIT = 20 * 1024 * 1024
PACK_PHOTO_LIMIT = 300_000


@lru_cache(maxsize=32)
def get_photo(photo_id):
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
            pixels = fitz.Pixmap(bytes(data))
            if pixels.alpha:
                pixels = fitz.Pixmap(pixels, 0)
            if pixels.colorspace and pixels.colorspace.n != 3:
                pixels = fitz.Pixmap(fitz.csRGB, pixels)
            while max(pixels.width, pixels.height) > 1920:
                pixels.shrink(1)
            for quality in (88, 76, 64):
                jpg = pixels.tobytes("jpeg", jpg_quality=quality)
                if len(jpg) <= PACK_PHOTO_LIMIT:
                    return jpg
            pixels.shrink(1)
            jpg = pixels.tobytes("jpeg", jpg_quality=76)
            if len(jpg) <= PACK_PHOTO_LIMIT:
                return jpg
        except (requests.RequestException, RuntimeError, ValueError) as exc:
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
    with ThreadPoolExecutor(max_workers=min(5, len(ids))) as pool:
        assets = list(pool.map(available_photo, ids))
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
