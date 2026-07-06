from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from wechat_content_fetcher.assets import mirror_article_assets
from wechat_content_fetcher.bundle import BundleArticleRecord, write_target_bundles
from wechat_content_fetcher.config import SiteConfig
from wechat_content_fetcher.fixtures import build_fixture_articles
from wechat_content_fetcher.ima_client import IMAApiError
from wechat_content_fetcher.models import (
    RenderedArticle,
    SourceArticle,
    SyncDependencies,
    SyncRunRecord,
    TargetConfig,
    TargetSyncState,
    WechatArticle,
)
from wechat_content_fetcher.renderer import render_article_page, render_folder_index
from wechat_content_fetcher.slug import slugify
from wechat_content_fetcher.state import compute_folder_delta
from wechat_content_fetcher.storage import append_run_log, load_state, save_state
from wechat_content_fetcher.wechat_fetcher import WechatFetchError


@dataclass(frozen=True)
class SyncSummary:
    rendered_pages: int
    updated_indexes: int
    targets_processed: int
    status: str = "success"
    targets_skipped: int = 0
    targets_partial: int = 0
    error_summary: str = ""
    quota_exhausted: bool = False


@dataclass(frozen=True)
class TargetRenderResult:
    rendered_pages: int
    updated_indexes: int
    rendered_articles: list[RenderedArticle]
    article_lookup: dict[str, WechatArticle]
    failed_article_ids: list[str]
    pending_article_ids: list[str]
    status: str
    quota_exhausted: bool


def run_fixture_sync(config: SiteConfig) -> SyncSummary:
    fixture_articles = build_fixture_articles()
    state = load_state(config.state_file)
    rendered_pages = 0
    updated_indexes = 0

    for target in config.targets:
        previous_state = state.get(target.target_key)
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
            previous_state=previous_state,
        )
        rendered_pages += result.rendered_pages
        updated_indexes += result.updated_indexes
        state[target.target_key] = _build_target_state(
            target_key=target.target_key,
            folder_slug=slugify(target.folder_name, fallback_prefix="folder"),
            source_articles=source_articles,
            rendered_articles=result.rendered_articles,
            pending_article_ids=result.pending_article_ids,
            sync_status="complete",
            last_run_reason="fixture",
            last_run_status="success",
            last_seen_fingerprint=_compute_fingerprint(source_articles),
            last_successful_fingerprint=_compute_fingerprint(source_articles),
        )
        _write_bundles_if_enabled(config, target, result, previous_state)

    save_state(config.state_file, state)
    render_root_index(config)
    return SyncSummary(
        rendered_pages=rendered_pages,
        updated_indexes=updated_indexes,
        targets_processed=len(config.targets),
    )


def run_ima_sync(
    config: SiteConfig,
    dependencies: SyncDependencies,
    reason: str = "scheduled_daily",
    force: bool = False,
    full_rescan: bool = False,
) -> SyncSummary:
    state = load_state(config.state_file)
    rendered_pages = 0
    updated_indexes = 0
    targets_skipped = 0
    targets_partial = 0
    quota_exhausted = False
    status = "success"
    error_summary = ""
    run_id = str(uuid4())
    started_at = _timestamp()

    fingerprint_before: dict[str, str] = {}
    fingerprint_after: dict[str, str] = {}
    articles_added: dict[str, list[str]] = {}
    articles_removed: dict[str, list[str]] = {}
    articles_fetched: dict[str, list[str]] = {}
    articles_failed: dict[str, list[str]] = {}
    pending_map: dict[str, list[str]] = {}

    for target in config.targets:
        previous_state = state.get(target.target_key)
        fingerprint_before[target.target_key] = (previous_state.last_successful_fingerprint if previous_state else "")
        try:
            source_articles = dependencies.ima_client.list_folder_articles(
                target.knowledge_base_id,
                target.folder_id,
            )
        except IMAApiError as exc:
            if not exc.is_quota_exhausted:
                raise

            source_articles = list(exc.partial_articles)
            quota_exhausted = True
            targets_partial += 1
            status = "partial"
            error_summary = "IMA quota exhausted"
            current_fingerprint = _compute_fingerprint(source_articles)
            fingerprint_after[target.target_key] = current_fingerprint
            articles_added[target.target_key] = []
            articles_removed[target.target_key] = []
            articles_fetched[target.target_key] = []
            articles_failed[target.target_key] = []
            pending_map[target.target_key] = list(previous_state.pending_article_ids) if previous_state else []
            state[target.target_key] = _build_target_state(
                target_key=target.target_key,
                folder_slug=slugify(target.folder_name, fallback_prefix="folder"),
                source_articles=source_articles,
                rendered_articles=[],
                pending_article_ids=list(previous_state.pending_article_ids) if previous_state else [],
                sync_status="partial",
                last_run_reason=reason,
                last_run_status="partial",
                last_seen_fingerprint=current_fingerprint,
                last_successful_fingerprint=(previous_state.last_successful_fingerprint if previous_state else ""),
                previous_state=previous_state,
                last_error="IMA quota exhausted",
                quota_exhausted=True,
                full_rescan=full_rescan or reason == "monthly_audit",
            )
            continue

        current_fingerprint = _compute_fingerprint(source_articles)
        fingerprint_after[target.target_key] = current_fingerprint

        if not source_articles and previous_state is not None:
            targets_skipped += 1
            articles_added[target.target_key] = []
            articles_removed[target.target_key] = []
            articles_fetched[target.target_key] = []
            articles_failed[target.target_key] = []
            pending_map[target.target_key] = list(previous_state.pending_article_ids)
            continue

        delta = compute_folder_delta(
            previous_state.as_folder_snapshot() if previous_state else None,
            [article.article_id for article in source_articles],
        )
        articles_added[target.target_key] = delta.added
        articles_removed[target.target_key] = delta.removed

        should_skip = (
            reason == "scheduled_daily"
            and not force
            and not full_rescan
            and previous_state is not None
            and not previous_state.pending_article_ids
            and current_fingerprint == previous_state.last_successful_fingerprint
        )
        if should_skip:
            targets_skipped += 1
            articles_fetched[target.target_key] = []
            articles_failed[target.target_key] = []
            pending_map[target.target_key] = []
            continue

        queue_ids = _build_fetch_queue(previous_state, source_articles, reason=reason, force=force, full_rescan=full_rescan)
        queued_articles = [article for article in source_articles if article.article_id in queue_ids]

        result = _render_target(
            config=config,
            target=target,
            source_articles=queued_articles,
            fetch_article=lambda source: dependencies.wechat_fetcher.fetch(source.source_url),
            previous_state=previous_state,
        )
        rendered_pages += result.rendered_pages
        updated_indexes += result.updated_indexes
        articles_fetched[target.target_key] = [article.article_id for article in result.rendered_articles]
        articles_failed[target.target_key] = list(result.failed_article_ids)
        pending_map[target.target_key] = list(result.pending_article_ids)

        if result.quota_exhausted:
            quota_exhausted = True
            targets_partial += 1
            status = "partial"
            if not error_summary:
                error_summary = "IMA quota exhausted"
        elif result.status == "partial":
            targets_partial += 1
            if status != "partial":
                status = "partial"

        merged_state = _merge_target_state(
            previous_state=previous_state,
            target_key=target.target_key,
            folder_slug=slugify(target.folder_name, fallback_prefix="folder"),
            source_articles=source_articles,
            result=result,
            reason=reason,
            current_fingerprint=current_fingerprint,
            full_rescan=full_rescan,
        )
        state[target.target_key] = merged_state
        _write_bundles_if_enabled(config, target, result, previous_state)

    save_state(config.state_file, state)
    render_root_index(config)
    ended_at = _timestamp()
    append_run_log(
        _run_log_file(config.state_file),
        SyncRunRecord(
            run_id=run_id,
            started_at=started_at,
            ended_at=ended_at,
            reason=reason,
            status=status if (targets_partial or rendered_pages or updated_indexes) else "skipped",
            targets=[target.target_key for target in config.targets],
            fingerprint_before=fingerprint_before,
            fingerprint_after=fingerprint_after,
            articles_added=articles_added,
            articles_removed=articles_removed,
            articles_fetched=articles_fetched,
            articles_failed=articles_failed,
            pending_article_ids=pending_map,
            quota_exhausted=quota_exhausted,
            publish_changed=False,
            published=False,
            error_summary=error_summary,
        ),
    )
    final_status = status
    if rendered_pages == 0 and updated_indexes == 0 and targets_partial == 0:
        final_status = "skipped"
    return SyncSummary(
        rendered_pages=rendered_pages,
        updated_indexes=updated_indexes,
        targets_processed=len(config.targets),
        status=final_status,
        targets_skipped=targets_skipped,
        targets_partial=targets_partial,
        error_summary=error_summary,
        quota_exhausted=quota_exhausted,
    )


def _render_target(
    config: SiteConfig,
    target: TargetConfig,
    source_articles: list[SourceArticle],
    fetch_article,
    previous_state: TargetSyncState | None,
) -> TargetRenderResult:
    folder_dir = config.output_dir / slugify(target.folder_name, fallback_prefix="folder")
    folder_dir.mkdir(parents=True, exist_ok=True)

    rendered: list[RenderedArticle] = []
    article_pages = dict(previous_state.article_pages) if previous_state else {}
    article_lookup: dict[str, WechatArticle] = {}
    rendered_pages = 0
    used_page_names: set[str] = set(Path(page).name for page in article_pages.values())
    failed_article_ids: list[str] = []
    pending_article_ids: list[str] = []
    quota_exhausted = False

    for source_article in source_articles:
        try:
            article: WechatArticle = fetch_article(source_article)
        except WechatFetchError:
            failed_article_ids.append(source_article.article_id)
            pending_article_ids.append(source_article.article_id)
            continue
        except IMAApiError as exc:
            if exc.is_quota_exhausted:
                quota_exhausted = True
                pending_article_ids.append(source_article.article_id)
                remaining = [item.article_id for item in source_articles if item.article_id not in article_lookup and item.article_id != source_article.article_id]
                pending_article_ids.extend(remaining)
                break
            raise

        article = mirror_article_assets(config.output_dir, source_article.article_id, article)
        page_name = _build_unique_page_name(
            article_title=article.title,
            article_id=source_article.article_id,
            used_page_names=used_page_names,
            existing_page=article_pages.get(source_article.article_id),
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

    merged_rendered = _merge_rendered_articles(previous_state, rendered, source_articles, folder_dir)
    render_folder_index(folder_dir / "index.html", target.folder_name, merged_rendered)
    status = "success"
    if quota_exhausted or failed_article_ids:
        status = "partial"

    return TargetRenderResult(
        rendered_pages=rendered_pages,
        updated_indexes=1 if source_articles or previous_state else 0,
        rendered_articles=merged_rendered,
        article_lookup=article_lookup,
        failed_article_ids=failed_article_ids,
        pending_article_ids=_dedupe_list(pending_article_ids),
        status=status,
        quota_exhausted=quota_exhausted,
    )


def _merge_rendered_articles(
    previous_state: TargetSyncState | None,
    newly_rendered: list[RenderedArticle],
    source_articles: list[SourceArticle],
    folder_dir: Path,
) -> list[RenderedArticle]:
    rendered_map = {article.article_id: article for article in newly_rendered}
    if previous_state is None:
        return list(newly_rendered)

    source_group_map = {article.article_id: article.group_name for article in source_articles}
    for article_id, relative_page in previous_state.article_pages.items():
        if article_id in rendered_map:
            continue
        file_name = Path(relative_page).name
        if not (folder_dir / file_name).exists():
            continue
        rendered_map[article_id] = RenderedArticle(
            article_id=article_id,
            title=file_name.removesuffix(".html"),
            author="",
            publish_time="",
            source_url="",
            page_path=Path(file_name),
            group_name=source_group_map.get(article_id, previous_state.article_groups.get(article_id, "")),
        )
    return [rendered_map[key] for key in sorted(rendered_map)]


def _build_unique_page_name(
    article_title: str,
    article_id: str,
    used_page_names: set[str],
    existing_page: str | None = None,
) -> str:
    if existing_page:
        existing_name = Path(existing_page).name
        used_page_names.add(existing_name)
        return existing_name

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
    previous_state: TargetSyncState | None,
) -> None:
    if not config.build_notebooklm_bundles:
        return

    records = [
        BundleArticleRecord(
            rendered=rendered_article,
            article=result.article_lookup[rendered_article.article_id],
        )
        for rendered_article in result.rendered_articles
        if rendered_article.article_id in result.article_lookup
    ]
    if not records and previous_state is None:
        return
    write_target_bundles(
        config=config,
        target=target,
        records=records,
        previous_snapshot=previous_state.as_folder_snapshot() if previous_state else None,
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


def _timestamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _compute_fingerprint(source_articles: list[SourceArticle]) -> str:
    normalized = "\n".join(
        f"{article.article_id}|{article.group_name}|{article.title}|{article.source_url}"
        for article in sorted(source_articles, key=lambda item: (item.article_id, item.group_name, item.title, item.source_url))
    )
    return sha256(normalized.encode("utf-8")).hexdigest()


def _build_fetch_queue(
    previous_state: TargetSyncState | None,
    source_articles: list[SourceArticle],
    reason: str,
    force: bool,
    full_rescan: bool,
) -> list[str]:
    if full_rescan or reason == "monthly_audit" or force or previous_state is None:
        return [article.article_id for article in source_articles]

    delta = compute_folder_delta(previous_state.as_folder_snapshot(), [article.article_id for article in source_articles])
    queue = list(previous_state.pending_article_ids) + list(delta.added)
    source_group_map = {article.article_id: article.group_name for article in source_articles}
    for article_id in delta.unchanged:
        if source_group_map.get(article_id, "") != previous_state.article_groups.get(article_id, ""):
            queue.append(article_id)
    return _dedupe_list(queue)


def _build_target_state(
    target_key: str,
    folder_slug: str,
    source_articles: list[SourceArticle],
    rendered_articles: list[RenderedArticle],
    pending_article_ids: list[str],
    sync_status: str,
    last_run_reason: str,
    last_run_status: str,
    last_seen_fingerprint: str,
    last_successful_fingerprint: str,
    previous_state: TargetSyncState | None = None,
    last_error: str = "",
    quota_exhausted: bool = False,
    full_rescan: bool = False,
) -> TargetSyncState:
    article_pages = dict(previous_state.article_pages) if previous_state else {}
    article_groups = dict(previous_state.article_groups) if previous_state else {}
    for article in rendered_articles:
        article_pages[article.article_id] = Path(folder_slug, article.page_path.name).as_posix()
        article_groups[article.article_id] = article.group_name

    now = _timestamp()
    return TargetSyncState(
        target_key=target_key,
        sync_status=sync_status,
        known_article_ids=[article.article_id for article in source_articles],
        pending_article_ids=list(pending_article_ids),
        article_pages=article_pages,
        article_groups=article_groups,
        last_seen_fingerprint=last_seen_fingerprint,
        last_successful_fingerprint=last_successful_fingerprint,
        last_successful_incremental_sync_at=now if sync_status == "complete" else (previous_state.last_successful_incremental_sync_at if previous_state else ""),
        last_successful_full_sync_at=now if sync_status == "complete" and full_rescan else (previous_state.last_successful_full_sync_at if previous_state else ""),
        last_successful_monthly_audit_at=now if sync_status == "complete" and full_rescan else (previous_state.last_successful_monthly_audit_at if previous_state else ""),
        last_quota_exhausted_at=now if quota_exhausted else (previous_state.last_quota_exhausted_at if previous_state else ""),
        last_run_reason=last_run_reason,
        last_run_status=last_run_status,
        last_error=last_error,
    )


def _merge_target_state(
    previous_state: TargetSyncState | None,
    target_key: str,
    folder_slug: str,
    source_articles: list[SourceArticle],
    result: TargetRenderResult,
    reason: str,
    current_fingerprint: str,
    full_rescan: bool,
) -> TargetSyncState:
    sync_status = "complete" if not result.pending_article_ids else "partial"
    return _build_target_state(
        target_key=target_key,
        folder_slug=folder_slug,
        source_articles=source_articles,
        rendered_articles=result.rendered_articles,
        pending_article_ids=result.pending_article_ids,
        sync_status=sync_status,
        last_run_reason=reason,
        last_run_status=result.status,
        last_seen_fingerprint=current_fingerprint,
        last_successful_fingerprint=current_fingerprint if sync_status == "complete" else (previous_state.last_successful_fingerprint if previous_state else ""),
        previous_state=previous_state,
        last_error="IMA quota exhausted" if result.quota_exhausted else "",
        quota_exhausted=result.quota_exhausted,
        full_rescan=full_rescan or reason == "monthly_audit",
    )


def _dedupe_list(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


def _run_log_file(state_file: Path) -> Path:
    return state_file.with_name(f"{state_file.stem}.runs.jsonl")
