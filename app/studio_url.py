"""Safe public-page inspection for Studio motion-video projects.

No page JavaScript is executed.  Every navigation and downloaded image is
resolved again and checked against public IP space to prevent DNS/redirect SSRF.
"""
from __future__ import annotations

import ipaddress
import json
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from PIL import Image

MAX_HTML = 3 * 1024 * 1024
MAX_IMAGE = 12 * 1024 * 1024
MAX_REDIRECTS = 5
USER_AGENT = "RafieiVideoStudio/1.0"


def _public_url(value: str) -> str:
    parsed = urllib.parse.urlsplit(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Only public HTTP/HTTPS URLs are supported")
    try:
        addresses = socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80))
    except socket.gaierror as exc:
        raise ValueError("The page hostname could not be resolved") from exc
    if not addresses:
        raise ValueError("The page hostname could not be resolved")
    for item in addresses:
        address = ipaddress.ip_address(item[4][0])
        if not address.is_global:
            raise ValueError("Private, loopback and reserved addresses are not allowed")
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path or "/", parsed.query, ""))


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


def _fetch(url: str, *, max_bytes: int, accept: str) -> tuple[bytes, str, str]:
    opener = urllib.request.build_opener(_NoRedirect)
    current = _public_url(url)
    for _ in range(MAX_REDIRECTS + 1):
        request = urllib.request.Request(current, headers={"User-Agent": USER_AGENT, "Accept": accept})
        try:
            response = opener.open(request, timeout=20)
        except urllib.error.HTTPError as exc:
            if exc.code in {301, 302, 303, 307, 308}:
                target = exc.headers.get("Location")
                if not target:
                    raise ValueError("The page returned an invalid redirect") from exc
                current = _public_url(urllib.parse.urljoin(current, target))
                continue
            raise ValueError(f"The page returned HTTP {exc.code}") from exc
        content_type = (response.headers.get_content_type() or "").lower()
        declared = response.headers.get("Content-Length")
        if declared and int(declared) > max_bytes:
            raise ValueError("The remote resource is too large")
        data = response.read(max_bytes + 1)
        if len(data) > max_bytes:
            raise ValueError("The remote resource is too large")
        return data, current, content_type
    raise ValueError("The page redirected too many times")


def _candidate_from_srcset(value: str) -> list[str]:
    return [part.strip().split()[0] for part in value.split(",") if part.strip()]


class PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.description = ""
        self.text: list[str] = []
        self.images: list[dict[str, str]] = []
        self.structured: list[Any] = []
        self._capture: str | None = None
        self._buffer: list[str] = []
        self._json_ld = False

    def handle_starttag(self, tag: str, attrs_list: list[tuple[str, str | None]]) -> None:
        attrs = {k.lower(): (v or "") for k, v in attrs_list}
        tag = tag.lower()
        if tag == "title":
            self._capture, self._buffer = "title", []
        elif tag in {"h1", "h2", "h3", "p", "li"}:
            self._capture, self._buffer = "text", []
        elif tag == "script" and attrs.get("type", "").lower() == "application/ld+json":
            self._capture, self._buffer, self._json_ld = "json", [], True
        elif tag == "meta":
            key = (attrs.get("property") or attrs.get("name") or "").lower()
            content = attrs.get("content", "").strip()
            if key in {"description", "og:description", "twitter:description"} and content and not self.description:
                self.description = content
            if key in {"og:image", "twitter:image", "twitter:image:src"} and content:
                self.images.append({"url": content, "alt": "social preview"})
        elif tag in {"img", "source"}:
            alt = attrs.get("alt", "").strip()
            for candidate in [attrs.get("src", ""), attrs.get("data-src", ""), attrs.get("data-lazy-src", ""), *_candidate_from_srcset(attrs.get("srcset", ""))]:
                if candidate:
                    self.images.append({"url": candidate, "alt": alt})

    def handle_endtag(self, tag: str) -> None:
        if self._capture == "title" and tag.lower() == "title":
            self.title = " ".join(self._buffer).strip()
            self._capture = None
        elif self._capture == "text" and tag.lower() in {"h1", "h2", "h3", "p", "li"}:
            value = re.sub(r"\s+", " ", " ".join(self._buffer)).strip()
            if len(value) >= 2:
                self.text.append(value)
            self._capture = None
        elif self._capture == "json" and tag.lower() == "script":
            try:
                self.structured.append(json.loads("".join(self._buffer)))
            except (TypeError, ValueError):
                pass
            self._capture, self._json_ld = None, False

    def handle_data(self, data: str) -> None:
        if self._capture:
            self._buffer.append(data)


def _walk_json_images(value: Any) -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key.lower() in {"image", "images", "contenturl", "thumbnailurl"}:
                if isinstance(item, str):
                    found.append(item)
                elif isinstance(item, list):
                    found.extend(x for x in item if isinstance(x, str))
            found.extend(_walk_json_images(item))
    elif isinstance(value, list):
        for item in value:
            found.extend(_walk_json_images(item))
    return found


def _structured_products(value: Any) -> list[dict]:
    items: list[dict] = []
    if isinstance(value, dict):
        kind = value.get("@type")
        kinds = kind if isinstance(kind, list) else [kind]
        if any(str(item).lower() == "product" for item in kinds):
            items.append({k: value.get(k) for k in ("name", "description", "brand", "sku", "offers", "category") if value.get(k)})
        for child in value.values():
            items.extend(_structured_products(child))
    elif isinstance(value, list):
        for child in value:
            items.extend(_structured_products(child))
    return items


def inspect_page(url: str, output_dir: Path) -> dict:
    html, final_url, content_type = _fetch(url, max_bytes=MAX_HTML, accept="text/html,application/xhtml+xml")
    if "html" not in content_type:
        raise ValueError("The URL did not return an HTML page")
    parser = PageParser()
    parser.feed(html.decode("utf-8", errors="replace"))
    base = final_url
    candidates = list(parser.images)
    for document in parser.structured:
        candidates.extend({"url": item, "alt": "structured product image"} for item in _walk_json_images(document))

    image_dir = output_dir / "url_images"
    image_dir.mkdir(parents=True, exist_ok=True)
    images: list[dict] = []
    seen: set[str] = set()
    for candidate in candidates:
        if len(images) >= 12:
            break
        absolute = urllib.parse.urljoin(base, candidate["url"])
        if absolute in seen or absolute.startswith("data:"):
            continue
        seen.add(absolute)
        try:
            raw, resolved, media_type = _fetch(absolute, max_bytes=MAX_IMAGE, accept="image/*")
            if not media_type.startswith("image/"):
                continue
            suffix = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}.get(media_type, ".img")
            path = image_dir / f"image_{len(images) + 1:02d}{suffix}"
            path.write_bytes(raw)
            with Image.open(path) as image:
                image.verify()
            with Image.open(path) as image:
                width, height = image.size
            if width < 280 or height < 280:
                path.unlink(missing_ok=True)
                continue
            images.append({"url": resolved, "file": str(path), "alt": candidate.get("alt", "")[:300], "width": width, "height": height})
        except (OSError, ValueError, urllib.error.URLError):
            continue

    text = []
    seen_text: set[str] = set()
    for item in parser.text:
        normalized = item.strip()
        if normalized and normalized not in seen_text:
            seen_text.add(normalized)
            text.append(normalized)
        if sum(len(part) for part in text) > 18_000:
            break
    products = []
    for document in parser.structured:
        products.extend(_structured_products(document))
    if not text and not products:
        raise ValueError("The page did not expose enough readable product content; upload product images or a description")
    return {
        "url": final_url,
        "host": urllib.parse.urlsplit(final_url).hostname,
        "title": parser.title[:500],
        "description": parser.description[:1500],
        "content": text,
        "structured_products": products[:10],
        "images": images,
    }
