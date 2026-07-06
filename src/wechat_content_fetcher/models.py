from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class TargetConfig:
    knowledge_base_id: str
    folder_id: str
    folder_name: str
    knowledge_base_name: str | None = None

    @property
    def target_key(self) -> str:
        return f"{self.knowledge_base_id}:{self.folder_id}"


@dataclass(frozen=True)
class WechatArticle:
    source_url: str
    title: str
    author: str
    publish_time: str
    cover_url: str
    markdown_body: str
    asset_paths: dict[str, Path] = field(default_factory=dict)
    local_cover_path: Path | None = None


@dataclass(frozen=True)
class RenderedArticle:
    article_id: str
    title: str
    author: str
    publish_time: str
    source_url: str
    page_path: Path
    group_name: str = ""


@dataclass(frozen=True)
class FolderDelta:
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class FolderSnapshot:
    target_key: str
    article_ids: list[str]
    article_pages: dict[str, str]
    article_groups: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class SourceArticle:
    article_id: str
    title: str
    source_url: str
    group_name: str = ""


@dataclass(frozen=True)
class SyncDependencies:
    ima_client: object
    wechat_fetcher: object


@dataclass(frozen=True)
class TargetSyncState:
    target_key: str
    sync_status: str = "never_started"
    known_article_ids: list[str] = field(default_factory=list)
    pending_article_ids: list[str] = field(default_factory=list)
    article_pages: dict[str, str] = field(default_factory=dict)
    article_groups: dict[str, str] = field(default_factory=dict)
    last_seen_fingerprint: str = ""
    last_successful_fingerprint: str = ""
    last_successful_incremental_sync_at: str = ""
    last_successful_full_sync_at: str = ""
    last_successful_monthly_audit_at: str = ""
    last_quota_exhausted_at: str = ""
    last_run_reason: str = ""
    last_run_status: str = ""
    last_error: str = ""

    @property
    def article_ids(self) -> list[str]:
        return self.known_article_ids

    def as_folder_snapshot(self) -> FolderSnapshot:
        return FolderSnapshot(
            target_key=self.target_key,
            article_ids=list(self.known_article_ids),
            article_pages=dict(self.article_pages),
            article_groups=dict(self.article_groups),
        )


@dataclass(frozen=True)
class SyncRunRecord:
    run_id: str
    started_at: str
    ended_at: str
    reason: str
    status: str
    targets: list[str] = field(default_factory=list)
    fingerprint_before: dict[str, str] = field(default_factory=dict)
    fingerprint_after: dict[str, str] = field(default_factory=dict)
    articles_added: dict[str, list[str]] = field(default_factory=dict)
    articles_removed: dict[str, list[str]] = field(default_factory=dict)
    articles_fetched: dict[str, list[str]] = field(default_factory=dict)
    articles_failed: dict[str, list[str]] = field(default_factory=dict)
    pending_article_ids: dict[str, list[str]] = field(default_factory=dict)
    quota_exhausted: bool = False
    publish_changed: bool = False
    published: bool = False
    error_summary: str = ""
