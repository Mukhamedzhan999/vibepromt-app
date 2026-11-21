"""Render an AI-authored photo plan using public images fetched by VibePrompt."""

import hashlib
import html
import io
import re
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlsplit

import fitz
import requests
from PIL import Image, ImageOps

import photo_catalog

MAX_PAGES = 12
IMAGE_HOST = "upload.wikimedia.org"


class PlanError(ValueError):
    pass


def direct_image_url(value):
    if not isinstance(value, str) or len(value) > 1500:
        return False
    try:
        parts = urlsplit(value)
        return (parts.scheme == "https" and parts.netloc == IMAGE_HOST
                and parts.path.startswith("/wikipedia/commons/")
                and parts.path.lower().endswith((".jpg", ".jpeg", ".png", ".webp"))
                and not parts.query and not parts.fragment)
    except ValueError:
        return False


def _text(record, key, limit):
    value = record.get(key)
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise PlanError(f'«{key}» өрісін тексеріңіз. Шегі — {limit} таңба.')
    return " ".join(value.split())


def validate_plan(plan):
    if not isinstance(plan, dict):
        raise PlanError("AI жауабындағы JSON нысанын көшіріңіз.")
    title = _text(plan, "title", 140)
    pages = plan.get("pages")
    expected = plan.get("page_count", len(pages) if isinstance(pages, list) else None)
    if (not isinstance(pages, list) or not 1 <= len(pages) <= MAX_PAGES
            or type(expected) is not int or expected != len(pages)):
        raise PlanError(f"Жоспарда 1–{MAX_PAGES} бет және әр беттің дерегі болуы керек.")
    normalized = []
    for number, page in enumerate(pages, 1):
        if not isinstance(page, dict) or type(page.get("page")) is not int or page["page"] != number:
            raise PlanError("Беттерді 1-ден бастап, ретімен нөмірлеңіз.")
        asset, url = page.get("photo_id") or "", page.get("image_url") or ""
        if not isinstance(asset, str) or (asset and asset not in photo_catalog.CATALOG):
            raise PlanError(f"{number}-беттегі фото идентификаторы жарамсыз.")
        if url and not direct_image_url(url):
            raise PlanError(f"{number}-бетке Wikimedia Commons-тың тікелей JPEG, PNG не WebP сілтемесін беріңіз.")
        if not asset and not url:
            raise PlanError(f"{number}-бетке фото таңдалмаған.")
        normalized.append({
            "title": _text(page, "title", 140),
            "body": _text(page, "body", 960),
            "caption": _text(page, "caption", 400),
            "photo_id": asset,
            "image_url": url,
            "image_credit": _text(page, "image_credit", 160) if url else "",
        })
    return title, normalized


def download_web_photo(url):
    """Fetch only direct Commons images, without following redirects."""
    if not direct_image_url(url):
        return None
    try:
        deadline = time.monotonic() + 9
        with requests.get(url, stream=True, allow_redirects=False, timeout=(3, 5),
                          headers={"User-Agent": "VibePromptAI/1.0 (public Wikimedia photo export)"}) as response:
            if response.status_code != 200 or not response.headers.get("Content-Type", "").startswith("image/"):
                return None
            data = bytearray()
            for chunk in response.iter_content(65536):
                data.extend(chunk)
                if len(data) > photo_catalog.ASSET_LIMIT or time.monotonic() > deadline:
                    return None
        with Image.open(io.BytesIO(data), formats=("JPEG", "PNG", "WEBP")) as source:
            if min(source.size) < 180 or source.width * source.height > 24_000_000:
                return None
            image = ImageOps.exif_transpose(source).convert("RGB")
            for size, quality in ((1600, 85), (1200, 76), (800, 68)):
                image.thumbnail((size, size), Image.Resampling.LANCZOS)
                buffer = io.BytesIO()
                image.save(buffer, format="JPEG", quality=quality, optimize=True)
                if buffer.tell() <= photo_catalog.PACK_PHOTO_LIMIT:
                    return buffer.getvalue()
    except (requests.RequestException, OSError, ValueError, Image.DecompressionBombError):
        return None
    return None


def _load_photo(page):
    if page["image_url"]:
        image = download_web_photo(page["image_url"])
        if image is not None:
            return image, page["image_credit"], page["image_url"]
    photo_id = page["photo_id"]
    if photo_id:
        asset = photo_catalog.CATALOG[photo_id]
        credit = f'{asset["credit"]} · {asset["license"]} · Wikimedia Commons'
        return photo_catalog.available_photo(photo_id), credit, asset["sourceUrl"]
    return None, "", ""


def _write(page, rect, text, size, color, *, bold=False, serif=False):
    family = "serif" if serif else "sans-serif"
    css = (f"body {{margin:0;font-family:{family};font-size:{size}pt;"
           f"line-height:1.28;color:{color};font-weight:{700 if bold else 400};}}")
    result, _ = page.insert_htmlbox(rect, html.escape(text), css=css, scale_low=0.70)
    if result < 0:
        raise PlanError("Мәтін бетке сыймады. AI жоспарындағы мәтінді ықшамдаңыз.")


def render_plan(plan):
    title, rows = validate_plan(plan)
    with ThreadPoolExecutor(max_workers=min(6, len(rows))) as pool:
        assets = list(pool.map(_load_photo, rows))
    missing = [str(i) for i, (data, _, _) in enumerate(assets, 1) if data is None]
    if missing:
        raise PlanError("Фото жүктелмеген беттер — " + ", ".join(missing) + ". Осы беттерге басқа дереккөз таңдаңыз.")
    if len({hashlib.sha256(data).digest() for data, _, _ in assets}) != len(rows):
        raise PlanError("Бір фото бірнеше рет таңдалған. Әр бетке бөлек фото таңдаңыз.")

    with fitz.open() as document:
        document.set_metadata({"title": title, "creator": "VibePrompt AI"})
        for number, (row, (data, credit, source)) in enumerate(zip(rows, assets), 1):
            page = document.new_page(width=960, height=540)
            page.draw_rect(page.rect, color=None, fill=(0.96, 0.93, 0.88))
            page.draw_rect(fitz.Rect(0, 0, 960, 8), color=None, fill=(0.46, 0.29, 0.21))
            _write(page, fitz.Rect(52, 27, 908, 49), title, 12, "#79513A", bold=True)
            _write(page, fitz.Rect(52, 57, 908, 146), row["title"], 36, "#16263D", bold=True, serif=True)
            photo_x, text_x = (52, 490) if number % 2 else (510, 52)
            photo_rect = fitz.Rect(photo_x, 151, photo_x + 398, 441)
            page.insert_image(photo_rect, stream=data, keep_proportion=True)
            credit_rect = fitz.Rect(photo_x, 448, photo_x + 398, 479)
            _write(page, credit_rect, credit, 9, "#594537")
            page.insert_link({"kind": fitz.LINK_URI, "from": credit_rect, "uri": source})
            _write(page, fitz.Rect(text_x, 151, text_x + 418, 328), row["body"], 18, "#201817")
            page.draw_rect(fitz.Rect(text_x, 334, text_x + 418, 481), color=None, fill=(0.91, 0.85, 0.78))
            _write(page, fitz.Rect(text_x + 14, 348, text_x + 404, 370), "Фото туралы", 11, "#79513A", bold=True)
            _write(page, fitz.Rect(text_x + 14, 374, text_x + 404, 472), row["caption"], 15, "#16263D")
            page.draw_line((52, 497), (908, 497), color=(0.65, 0.54, 0.46), width=0.75)
            _write(page, fitz.Rect(52, 501, 280, 525), "VibePrompt AI", 10, "#79513A", bold=True)
            _write(page, fitz.Rect(853, 501, 908, 525), f"{number} / {len(rows)}", 10, "#79513A")
        pdf = document.tobytes(garbage=4, deflate=True)
    with fitz.open(stream=pdf, filetype="pdf") as exported:
        if len(exported) != len(rows) or any(not page.get_image_info() for page in exported):
            raise PlanError("Дайын PDF-тегі фотоларды растау мүмкін болмады.")
    return pdf, len(rows)
