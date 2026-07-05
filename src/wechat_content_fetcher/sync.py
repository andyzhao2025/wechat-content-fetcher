from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from wechat_content_fetcher.bundle import BundleArticleRecord, write_target_bundles
from wechat_content_fetcher.config import SiteConfig
from wechat_content_fetcher.fixtures import build_fixture_articles
from wechat_content_fetcher.models import (
    FolderSnapshot,
    RenderedArticle,
    SourceArticle,
    SyncDependencies,
    TargetConfig,
    WechatArticle,
)
from wechat_content_fetcher.renderer import render_article_page, render_folder_index
from wechat_content_fetcher.slug import slugify
from wechat_content_fetcher.storage import load_state, save_state
from wechat_content_fetcher.wechat_fetcher import WechatFetchError


@dataclass(frozen=True)
class SyncSummary:
    rendered_pages: int
    updated_indexes: int
    targets_processed: int


@dataclass(frozen=True)
class TargetRenderResult:
    rendered_pages: int
    updated_indexes: int
    rendered_articles: list[RenderedArticle]
    article_lookup: dict[str, WechatArticle]


def run_fixture_sync(config: SiteConfig) -> SyncSummary:
    fixture_articles = build_fixture_articles()
    state = load_state(config.state_file)
    rendered_pages = 0
    updated_indexes = 0

    for target in config.targets:
        previous_snapshot = state.get(target.target_key)
        source_articles = [
            SourceArticle(article_id=article_id, title=article.title, source_url=article.source_url)
            for article_id, article in sorted(fixture_articles.items())
        ]
        article_lookup = dict(fixture_articles)
        result = _render_target(
            config=config,
            target=target,
            source_articles=source_articles,
            fetch_article=lambda source: article_lookup[source.article_id],
            state=state,
        )
        rendered_pages += result.rendered_pages
        updated_indexes += result.updated_indexes
        _write_bundles_if_enabled(config, target, result, previous_snapshot)

    save_state(config.state_file, state)
    render_root_index(config)
    return SyncSummary(
        rendered_pages=rendered_pages,
        updated_indexes=updated_indexes,
        targets_processed=len(config.targets),
    )


def run_ima_sync(config: SiteConfig, dependencies: SyncDependencies) -> SyncSummary:
    state = load_state(config.state_file)
    rendered_pages = 0
    updated_indexes = 0

    for target in config.targets:
        previous_snapshot = state.get(target.target_key)
        source_articles = dependencies.ima_client.list_folder_articles(
            target.knowledge_base_id,
            target.folder_id,
        )
        if not source_articles and previous_snapshot is not None:
            continue
        result = _render_target(
            config=config,
            target=target,
            source_articles=source_articles,
            fetch_article=lambda source: dependencies.wechat_fetcher.fetch(source.source_url),
            state=state,
        )
        rendered_pages += result.rendered_pages
        updated_indexes += result.updated_indexes
        if result.rendered_pages == 0 and source_articles and previous_snapshot is not None:
            state[target.target_key] = previous_snapshot
            continue
        _write_bundles_if_enabled(config, target, result, previous_snapshot)

    save_state(config.state_file, state)
    render_root_index(config)
    return SyncSummary(
        rendered_pages=rendered_pages,
        updated_indexes=updated_indexes,
        targets_processed=len(config.targets),
    )


def _render_target(
    config: SiteConfig,
    target: TargetConfig,
    source_articles: list[SourceArticle],
    fetch_article,
    state: dict[str, FolderSnapshot],
) -> TargetRenderResult:
    folder_dir = config.output_dir / slugify(target.folder_name, fallback_prefix="folder")
    folder_dir.mkdir(parents=True, exist_ok=True)

    rendered: list[RenderedArticle] = []
    article_pages: dict[str, str] = {}
    rendered_pages = 0
    used_page_names: set[str] = set()
    article_lookup: dict[str, WechatArticle] = {}

    for source_article in source_articles:
        try:
            article: WechatArticle = fetch_article(source_article)
        except WechatFetchError:
            continue
        page_name = _build_unique_page_name(
            article_title=article.title,
            article_id=source_article.article_id,
            used_page_names=used_page_names,
        )
        page_path = folder_dir / page_name
        render_article_page(page_path, article)
        rendered_pages += 1
        article_lookup[source_article.article_id] = article
        article_pages[source_article.article_id] = str(Path(folder_dir.name) / page_name)
        rendered.append(
            RenderedArticle(
                article_id=source_article.article_id,
                title=article.title,
                author=article.author,
                publish_time=article.publish_time,
                source_url=article.source_url,
                page_path=Path(page_name),
                group_name=source_article.group_name,
            )
        )

    render_folder_index(folder_dir / "index.html", target.folder_name, rendered)
    state[target.target_key] = FolderSnapshot(
        target_key=target.target_key,
        article_ids=[article.article_id for article in rendered],
        article_pages=article_pages,
        article_groups={article.article_id: article.group_name for article in rendered},
    )
    return TargetRenderResult(
        rendered_pages=rendered_pages,
        updated_indexes=1,
        rendered_articles=rendered,
        article_lookup=article_lookup,
    )


def _build_unique_page_name(article_title: str, article_id: str, used_page_names: set[str]) -> str:
    base_slug = slugify(article_title)
    candidate = f"{base_slug}.html"
    if candidate not in used_page_names:
        used_page_names.add(candidate)
        return candidate

    suffix = slugify(article_id, fallback_prefix="article")
    candidate = f"{base_slug}-{suffix}.html"
    counter = 2
    while candidate in used_page_names:
        candidate = f"{base_slug}-{suffix}-{counter}.html"
        counter += 1

    used_page_names.add(candidate)
    return candidate


def _write_bundles_if_enabled(
    config: SiteConfig,
    target: TargetConfig,
    result: TargetRenderResult,
    previous_snapshot: FolderSnapshot | None,
) -> None:
    if not config.build_notebooklm_bundles:
        return

    records = [
        BundleArticleRecord(
            rendered=rendered_article,
            article=result.article_lookup[rendered_article.article_id],
        )
        for rendered_article in result.rendered_articles
    ]
    write_target_bundles(
        config=config,
        target=target,
        records=records,
        previous_snapshot=previous_snapshot,
    )


def render_root_index(config: SiteConfig) -> None:
    links = "\n".join(
        f'<li><a href="{slugify(target.folder_name, fallback_prefix="folder")}/index.html">{target.folder_name}</a></li>'
        for target in config.targets
    )
    html = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{config.site_title}</title>
</head>
<body>
  <main>
    <h1>{config.site_title}</h1>
    <ul>
      {links}
    </ul>
  </main>
</body>
</html>
"""
    config.output_dir.mkdir(parents=True, exist_ok=True)
    (config.output_dir / "index.html").write_text(html, encoding="utf-8")
