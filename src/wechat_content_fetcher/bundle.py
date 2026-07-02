from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, UTC
from html import escape
import json
from pathlib import Path
import re

import markdown as markdown_lib

from wechat_content_fetcher.config import SiteConfig
from wechat_content_fetcher.models import FolderSnapshot, RenderedArticle, TargetConfig, WechatArticle
from wechat_content_fetcher.slug import slugify


@dataclass(frozen=True)
class BundleArticleRecord:
    rendered: RenderedArticle
    article: WechatArticle


def write_target_bundles(
    config: SiteConfig,
    target: TargetConfig,
    records: list[BundleArticleRecord],
    previous_snapshot: FolderSnapshot | None,
) -> None:
    bundle_root = config.output_dir / config.notebooklm_dir_name / slugify(target.folder_name, fallback_prefix="folder")
    bundle_root.mkdir(parents=True, exist_ok=True)
    manifest_path = bundle_root / "manifest.json"
    previous_manifest = _load_manifest(manifest_path)

    group_records = _group_records(records, target.folder_name)
    current_group_map = {record.rendered.article_id: _normalize_group_name(record.rendered.group_name, target.folder_name) for record in records}
    changed_groups = _determine_changed_groups(
        current_group_map=current_group_map,
        previous_snapshot=previous_snapshot,
        current_groups=set(group_records),
        previous_groups=set(previous_manifest.get("groups", {})),
        bundle_mode=config.bundle_mode,
    )

    groups_manifest: dict[str, dict] = {}
    previous_groups_manifest = previous_manifest.get("groups", {})
    all_group_names = sorted(set(group_records) | set(previous_groups_manifest))
    for group_name in all_group_names:
        if group_name not in changed_groups:
            groups_manifest[group_name] = previous_groups_manifest[group_name]
            continue

        _delete_group_files(bundle_root, previous_groups_manifest.get(group_name, {}).get("bundle_files", []))
        current_records = group_records.get(group_name, [])
        if not current_records:
            continue

        groups_manifest[group_name] = _write_group_bundles(
            bundle_root=bundle_root,
            group_name=group_name,
            records=current_records,
            max_bundle_articles=config.max_bundle_articles,
            max_bundle_words=config.max_bundle_words,
            base_url=config.base_url,
        )

    manifest = {
        "target_key": target.target_key,
        "target_name": target.folder_name,
        "generated_at": datetime.now(UTC).isoformat(),
        "groups": groups_manifest,
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_notebooklm_index(bundle_root, target.folder_name, groups_manifest)
    _write_url_manifest(bundle_root, groups_manifest, config.base_url)


def _load_manifest(manifest_path: Path) -> dict:
    if not manifest_path.exists():
        return {}
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def _group_records(records: list[BundleArticleRecord], fallback_group_name: str) -> dict[str, list[BundleArticleRecord]]:
    groups: dict[str, list[BundleArticleRecord]] = {}
    for record in records:
        group_name = _normalize_group_name(record.rendered.group_name, fallback_group_name)
        groups.setdefault(group_name, []).append(record)
    return groups


def _normalize_group_name(group_name: str, fallback_group_name: str) -> str:
    return (group_name or fallback_group_name).strip() or fallback_group_name


def _determine_changed_groups(
    current_group_map: dict[str, str],
    previous_snapshot: FolderSnapshot | None,
    current_groups: set[str],
    previous_groups: set[str],
    bundle_mode: str,
) -> set[str]:
    if bundle_mode != "incremental" or previous_snapshot is None:
        return current_groups | previous_groups

    previous_group_map = previous_snapshot.article_groups
    changed_groups: set[str] = set()
    all_article_ids = set(current_group_map) | set(previous_group_map)
    for article_id in all_article_ids:
        previous_group = previous_group_map.get(article_id)
        current_group = current_group_map.get(article_id)
        if previous_group == current_group:
            continue
        if previous_group:
            changed_groups.add(previous_group)
        if current_group:
            changed_groups.add(current_group)
    return changed_groups


def _delete_group_files(bundle_root: Path, bundle_files: list[str]) -> None:
    for bundle_file in bundle_files:
        path = bundle_root / bundle_file
        if path.exists():
            path.unlink()


def _write_group_bundles(
    bundle_root: Path,
    group_name: str,
    records: list[BundleArticleRecord],
    max_bundle_articles: int,
    max_bundle_words: int,
    base_url: str,
) -> dict:
    chunks: list[list[BundleArticleRecord]] = []
    current_chunk: list[BundleArticleRecord] = []
    current_word_count = 0

    for record in records:
        article_word_count = _estimate_word_count(record.article.markdown_body)
        would_exceed_words = current_chunk and current_word_count + article_word_count > max_bundle_words
        would_exceed_articles = current_chunk and len(current_chunk) >= max_bundle_articles
        if would_exceed_words or would_exceed_articles:
            chunks.append(current_chunk)
            current_chunk = []
            current_word_count = 0
        current_chunk.append(record)
        current_word_count += article_word_count

    if current_chunk:
        chunks.append(current_chunk)

    group_slug = slugify(group_name, fallback_prefix="group")
    bundle_files: list[str] = []
    article_ids: list[str] = []
    bundle_urls: list[str] = []

    for index, chunk in enumerate(chunks, start=1):
        file_name = f"{group_slug}-part-{index:03d}.html"
        output_path = bundle_root / file_name
        output_path.write_text(_render_bundle_page(group_name, chunk), encoding="utf-8")
        bundle_files.append(file_name)
        article_ids.extend(record.rendered.article_id for record in chunk)
        if base_url:
            bundle_urls.append(_join_public_url(base_url, output_path.relative_to(bundle_root.parents[1]).as_posix()))

    return {
        "group_name": group_name,
        "group_slug": group_slug,
        "bundle_files": bundle_files,
        "bundle_urls": bundle_urls,
        "article_ids": article_ids,
        "article_count": len(article_ids),
        "word_count": sum(_estimate_word_count(record.article.markdown_body) for record in records),
    }


def _render_bundle_page(group_name: str, records: list[BundleArticleRecord]) -> str:
    sections = []
    for record in records:
        article = record.article
        body_html = markdown_lib.markdown(article.markdown_body)
        meta_parts = []
        if article.author:
            meta_parts.append(f"<span>{escape(article.author)}</span>")
        if article.publish_time:
            meta_parts.append(f"<time>{escape(article.publish_time)}</time>")
        meta_html = " ".join(meta_parts)
        sections.append(
            f"""
<section>
  <header>
    <h2>{escape(article.title)}</h2>
    <p><a href="{escape(article.source_url)}">原文链接</a></p>
    <p>{meta_html}</p>
  </header>
  <article>{body_html}</article>
</section>
"""
        )

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(group_name)}</title>
</head>
<body>
  <main>
    <h1>{escape(group_name)}</h1>
    {''.join(sections)}
  </main>
</body>
</html>
"""


def _write_notebooklm_index(bundle_root: Path, target_name: str, groups_manifest: dict[str, dict]) -> None:
    items = []
    for group_name in sorted(groups_manifest):
        group_manifest = groups_manifest[group_name]
        files = "".join(f'<li><a href="{escape(file_name)}">{escape(file_name)}</a></li>' for file_name in group_manifest["bundle_files"])
        items.append(
            f"""
<section>
  <h2>{escape(group_name)}</h2>
  <p>articles={group_manifest["article_count"]} words={group_manifest["word_count"]}</p>
  <ul>{files}</ul>
</section>
"""
        )

    html = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(target_name)} NotebookLM Bundles</title>
</head>
<body>
  <main>
    <h1>{escape(target_name)} NotebookLM Bundles</h1>
    {''.join(items)}
  </main>
</body>
</html>
"""
    (bundle_root / "index.html").write_text(html, encoding="utf-8")


def _write_url_manifest(bundle_root: Path, groups_manifest: dict[str, dict], base_url: str) -> None:
    urls: list[str] = []
    if base_url:
        for group_name in sorted(groups_manifest):
            urls.extend(groups_manifest[group_name]["bundle_urls"])
    else:
        for group_name in sorted(groups_manifest):
            urls.extend(groups_manifest[group_name]["bundle_files"])

    (bundle_root / "notebooklm-urls.txt").write_text("\n".join(urls) + ("\n" if urls else ""), encoding="utf-8")


def _join_public_url(base_url: str, relative_path: str) -> str:
    return f"{base_url.rstrip('/')}/{relative_path.lstrip('/')}"


def _estimate_word_count(text: str) -> int:
    return len(re.findall(r"[\u4e00-\u9fff]|[A-Za-z0-9_]+", text))
