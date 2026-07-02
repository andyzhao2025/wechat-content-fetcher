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
