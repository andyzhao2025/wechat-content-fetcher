from __future__ import annotations

from dataclasses import replace
import hashlib
import os
from pathlib import Path
import re
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

from wechat_content_fetcher.models import WechatArticle
from wechat_content_fetcher.slug import slugify


MARKDOWN_IMAGE_PATTERN = re.compile(r"!\[[^\]]*\]\((https?://[^\s)]+)(?:\s+\"[^\"]*\")?\)")
KNOWN_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg"}
CONTENT_TYPE_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/bmp": ".bmp",
    "image/svg+xml": ".svg",
}


def mirror_article_assets(
    output_dir: Path,
    article_id: str,
    article: WechatArticle,
    timeout_seconds: int = 30,
) -> WechatArticle:
    remote_urls = _collect_remote_image_urls(article)
    if not remote_urls:
        return article

    asset_dir = output_dir / "assets" / slugify(article_id, fallback_prefix="article")
    asset_paths: dict[str, Path] = {}
    local_cover_path: Path | None = None

    for remote_url in remote_urls:
        try:
            asset_path = _download_image(remote_url, asset_dir, timeout_seconds)
        except OSError:
            continue

        asset_paths[remote_url] = asset_path
        if remote_url == article.cover_url:
            local_cover_path = asset_path

    return replace(article, asset_paths=asset_paths, local_cover_path=local_cover_path)


def localize_article_for_output(article: WechatArticle, output_path: Path) -> WechatArticle:
    if not article.asset_paths and not article.local_cover_path:
        return article

    markdown_body = article.markdown_body
    for remote_url, asset_path in article.asset_paths.items():
        markdown_body = markdown_body.replace(remote_url, _relative_asset_path(asset_path, output_path))

    cover_url = article.cover_url
    if article.local_cover_path:
        cover_url = _relative_asset_path(article.local_cover_path, output_path)

    return replace(article, cover_url=cover_url, markdown_body=markdown_body)


def _collect_remote_image_urls(article: WechatArticle) -> list[str]:
    seen: set[str] = set()
    ordered_urls: list[str] = []

    def add_if_remote(url: str) -> None:
        if not url.startswith(("http://", "https://")):
            return
        if url in seen:
            return
        seen.add(url)
        ordered_urls.append(url)

    add_if_remote(article.cover_url)
    for remote_url in MARKDOWN_IMAGE_PATTERN.findall(article.markdown_body):
        add_if_remote(remote_url)

    return ordered_urls


def _download_image(remote_url: str, asset_dir: Path, timeout_seconds: int) -> Path:
    asset_dir.mkdir(parents=True, exist_ok=True)

    extension = _infer_extension_from_url(remote_url)
    name_root = hashlib.sha256(remote_url.encode("utf-8")).hexdigest()[:16]
    if extension:
        candidate = asset_dir / f"{name_root}{extension}"
        if candidate.exists():
            return candidate
    else:
        existing_files = sorted(asset_dir.glob(f"{name_root}.*"))
        if existing_files:
            return existing_files[0]

    request = Request(
        remote_url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://mp.weixin.qq.com/",
        },
    )
    with urlopen(request, timeout=timeout_seconds) as response:
        payload = response.read()
        if not extension:
            content_type = response.headers.get_content_type()
            extension = CONTENT_TYPE_EXTENSIONS.get(content_type, ".img")

    candidate = asset_dir / f"{name_root}{extension}"
    if not candidate.exists():
        candidate.write_bytes(payload)
    return candidate


def _infer_extension_from_url(remote_url: str) -> str:
    parsed = urlparse(remote_url)
    suffix = Path(parsed.path).suffix.lower()
    if suffix in KNOWN_IMAGE_EXTENSIONS:
        return suffix

    query = parse_qs(parsed.query)
    wx_fmt = (query.get("wx_fmt") or [""])[0].lower()
    if wx_fmt == "jpeg":
        return ".jpg"
    if wx_fmt in {"png", "gif", "webp", "bmp"}:
        return f".{wx_fmt}"
    if wx_fmt == "svg":
        return ".svg"
    return ""


def _relative_asset_path(asset_path: Path, output_path: Path) -> str:
    return Path(os.path.relpath(asset_path, output_path.parent)).as_posix()
