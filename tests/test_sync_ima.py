from pathlib import Path

from wechat_content_fetcher.config import SiteConfig
from wechat_content_fetcher.models import FolderSnapshot, SourceArticle, SyncDependencies, TargetConfig
from wechat_content_fetcher.sync import run_ima_sync
from wechat_content_fetcher.storage import save_state
from wechat_content_fetcher.wechat_fetcher import WechatFetchError


class FakeIMAClient:
    def __init__(self):
        self.calls: list[tuple[str, str]] = []

    def list_folder_articles(self, knowledge_base_id: str, folder_id: str):
        self.calls.append((knowledge_base_id, folder_id))
        return [
            SourceArticle(article_id="media-1", title="Alpha Article", source_url="https://mp.weixin.qq.com/s/alpha"),
            SourceArticle(article_id="media-2", title="Beta Article", source_url="https://mp.weixin.qq.com/s/beta"),
        ]


class FakeWechatFetcher:
    def __init__(self):
        self.urls: list[str] = []

    def fetch(self, url: str):
        self.urls.append(url)
        suffix = url.rsplit("/", 1)[-1]
        from wechat_content_fetcher.models import WechatArticle

        return WechatArticle(
            source_url=url,
            title=f"Title {suffix}",
            author="Fetcher",
            publish_time="2026-06-30",
            cover_url="",
            markdown_body=f"# {suffix}\n\nbody",
        )


def test_run_ima_sync_generates_pages_and_indexes(tmp_path: Path):
    config = SiteConfig(
        site_title="IMA Export",
        output_dir=tmp_path / "site",
        state_file=tmp_path / "state.json",
        base_url="",
        publish_mode="github-pages",
        targets=[
            TargetConfig(
                knowledge_base_id="kb-1",
                folder_id="folder-1",
                folder_name="Favorites",
                knowledge_base_name="Knowledge Base One",
            )
        ],
    )
    ima_client = FakeIMAClient()
    wechat_fetcher = FakeWechatFetcher()

    summary = run_ima_sync(
        config,
        dependencies=SyncDependencies(
            ima_client=ima_client,
            wechat_fetcher=wechat_fetcher,
        ),
    )

    assert summary.targets_processed == 1
    assert summary.rendered_pages == 2
    assert summary.updated_indexes == 1
    assert ima_client.calls == [("kb-1", "folder-1")]
    assert wechat_fetcher.urls == [
        "https://mp.weixin.qq.com/s/alpha",
        "https://mp.weixin.qq.com/s/beta",
    ]

    folder_dir = config.output_dir / "favorites"
    assert (folder_dir / "title-alpha.html").exists()
    assert (folder_dir / "title-beta.html").exists()
    assert (folder_dir / "index.html").exists()
    assert (config.output_dir / "index.html").exists()

    state_text = config.state_file.read_text(encoding="utf-8")
    assert '"article_ids": [' in state_text
    assert '"media-1"' in state_text
    assert '"media-2"' in state_text


class PartiallyFailingWechatFetcher(FakeWechatFetcher):
    def fetch(self, url: str):
        self.urls.append(url)
        if url.endswith("/beta"):
            raise WechatFetchError("fetch failed")
        return super().fetch(url)


def test_run_ima_sync_skips_articles_that_fail_wechat_fetch(tmp_path: Path):
    config = SiteConfig(
        site_title="IMA Export",
        output_dir=tmp_path / "site",
        state_file=tmp_path / "state.json",
        base_url="",
        publish_mode="github-pages",
        targets=[
            TargetConfig(
                knowledge_base_id="kb-1",
                folder_id="folder-1",
                folder_name="Favorites",
                knowledge_base_name="Knowledge Base One",
            )
        ],
    )
    ima_client = FakeIMAClient()
    wechat_fetcher = PartiallyFailingWechatFetcher()

    summary = run_ima_sync(
        config,
        dependencies=SyncDependencies(
            ima_client=ima_client,
            wechat_fetcher=wechat_fetcher,
        ),
    )

    assert summary.targets_processed == 1
    assert summary.rendered_pages == 1
    assert summary.updated_indexes == 1
    assert ima_client.calls == [("kb-1", "folder-1")]

    folder_dir = config.output_dir / "favorites"
    assert (folder_dir / "title-alpha.html").exists()
    assert not (folder_dir / "title-beta.html").exists()
    assert (folder_dir / "index.html").exists()


class CollidingTitleWechatFetcher:
    def fetch(self, url: str):
        from wechat_content_fetcher.models import WechatArticle

        return WechatArticle(
            source_url=url,
            title="Same Title",
            author="Fetcher",
            publish_time="2026-07-01",
            cover_url="",
            markdown_body=f"# {url}\n\nbody",
        )


def test_run_ima_sync_uses_unique_filenames_for_colliding_slugs(tmp_path: Path):
    config = SiteConfig(
        site_title="IMA Export",
        output_dir=tmp_path / "site",
        state_file=tmp_path / "state.json",
        base_url="",
        publish_mode="github-pages",
        targets=[
            TargetConfig(
                knowledge_base_id="kb-1",
                folder_id="folder-1",
                folder_name="Favorites",
                knowledge_base_name="Knowledge Base One",
            )
        ],
    )
    ima_client = FakeIMAClient()
    wechat_fetcher = CollidingTitleWechatFetcher()

    summary = run_ima_sync(
        config,
        dependencies=SyncDependencies(
            ima_client=ima_client,
            wechat_fetcher=wechat_fetcher,
        ),
    )

    assert summary.rendered_pages == 2

    folder_dir = config.output_dir / "favorites"
    page_names = sorted(path.name for path in folder_dir.glob("*.html"))
    assert "same-title.html" in page_names
    assert "same-title-media-2.html" in page_names


class EmptyIMAClient:
    def __init__(self):
        self.calls: list[tuple[str, str]] = []

    def list_folder_articles(self, knowledge_base_id: str, folder_id: str):
        self.calls.append((knowledge_base_id, folder_id))
        return []


def test_run_ima_sync_keeps_previous_snapshot_when_ima_returns_empty(tmp_path: Path):
    config = SiteConfig(
        site_title="IMA Export",
        output_dir=tmp_path / "site",
        state_file=tmp_path / "state.json",
        base_url="",
        publish_mode="github-pages",
        targets=[
            TargetConfig(
                knowledge_base_id="kb-1",
                folder_id="folder-1",
                folder_name="Favorites",
                knowledge_base_name="Knowledge Base One",
            )
        ],
    )
    previous_snapshot = FolderSnapshot(
        target_key="kb-1:folder-1",
        article_ids=["media-1"],
        article_pages={"media-1": "favorites/title-alpha.html"},
        article_groups={"media-1": "01"},
    )
    save_state(config.state_file, {previous_snapshot.target_key: previous_snapshot})
    ima_client = EmptyIMAClient()
    wechat_fetcher = FakeWechatFetcher()

    summary = run_ima_sync(
        config,
        dependencies=SyncDependencies(
            ima_client=ima_client,
            wechat_fetcher=wechat_fetcher,
        ),
    )

    assert summary.targets_processed == 1
    assert summary.rendered_pages == 0
    assert summary.updated_indexes == 0
    assert ima_client.calls == [("kb-1", "folder-1")]
    assert wechat_fetcher.urls == []

    state_text = config.state_file.read_text(encoding="utf-8")
    assert '"media-1"' in state_text
    assert '"favorites/title-alpha.html"' in state_text
