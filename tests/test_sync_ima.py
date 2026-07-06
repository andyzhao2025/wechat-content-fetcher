from __future__ import annotations

from pathlib import Path

from wechat_content_fetcher.config import SiteConfig
from wechat_content_fetcher.models import SourceArticle, SyncDependencies, TargetConfig, WechatArticle
from wechat_content_fetcher.sync import run_ima_sync
from wechat_content_fetcher.storage import load_run_log, load_state
from wechat_content_fetcher.wechat_fetcher import WechatFetchError


class FakeIMAClient:
    def __init__(self, articles: list[SourceArticle] | None = None):
        self.calls: list[tuple[str, str]] = []
        self.articles = articles or [
            SourceArticle(article_id="media-1", title="Alpha Article", source_url="https://mp.weixin.qq.com/s/alpha"),
            SourceArticle(article_id="media-2", title="Beta Article", source_url="https://mp.weixin.qq.com/s/beta"),
        ]

    def list_folder_articles(self, knowledge_base_id: str, folder_id: str):
        self.calls.append((knowledge_base_id, folder_id))
        return list(self.articles)


class QuotaAwareIMAClient(FakeIMAClient):
    def __init__(self, articles: list[SourceArticle] | None = None, quota_message: str = "资料获取次数已达上限，请明天再尝试"):
        super().__init__(articles=articles)
        self.quota_message = quota_message

    def quota_error(self):
        from wechat_content_fetcher.ima_client import IMAApiError

        return IMAApiError(220021, self.quota_message)


class FakeWechatFetcher:
    def __init__(self):
        self.urls: list[str] = []

    def fetch(self, url: str):
        self.urls.append(url)
        suffix = url.rsplit("/", 1)[-1]
        return WechatArticle(
            source_url=url,
            title=f"Title {suffix}",
            author="Fetcher",
            publish_time="2026-06-30",
            cover_url="",
            markdown_body=f"# {suffix}\n\nbody",
        )


class PartiallyFailingWechatFetcher(FakeWechatFetcher):
    def fetch(self, url: str):
        self.urls.append(url)
        if url.endswith("/beta"):
            raise WechatFetchError("fetch failed")
        return super().fetch(url)


class CollidingTitleWechatFetcher:
    def fetch(self, url: str):
        return WechatArticle(
            source_url=url,
            title="Same Title",
            author="Fetcher",
            publish_time="2026-07-01",
            cover_url="",
            markdown_body=f"# {url}\n\nbody",
        )


class QuotaFailingWechatFetcher(FakeWechatFetcher):
    def __init__(self, fail_on_url_suffix: str):
        super().__init__()
        self.fail_on_url_suffix = fail_on_url_suffix

    def fetch(self, url: str):
        self.urls.append(url)
        if url.endswith(self.fail_on_url_suffix):
            from wechat_content_fetcher.ima_client import IMAApiError

            raise IMAApiError(220021, "资料获取次数已达上限，请明天再尝试")
        return super().fetch(url)


def build_config(tmp_path: Path) -> SiteConfig:
    return SiteConfig(
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


def test_run_ima_sync_generates_pages_indexes_and_run_log(tmp_path: Path):
    config = build_config(tmp_path)
    ima_client = FakeIMAClient()
    wechat_fetcher = FakeWechatFetcher()

    summary = run_ima_sync(
        config,
        dependencies=SyncDependencies(
            ima_client=ima_client,
            wechat_fetcher=wechat_fetcher,
        ),
        reason="scheduled_daily",
    )

    assert summary.targets_processed == 1
    assert summary.rendered_pages == 2
    assert summary.updated_indexes == 1
    assert summary.status == "success"
    assert summary.targets_skipped == 0
    assert summary.targets_partial == 0
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

    state = load_state(config.state_file)
    target_state = state["kb-1:folder-1"]
    assert target_state.sync_status == "complete"
    assert target_state.known_article_ids == ["media-1", "media-2"]
    assert target_state.pending_article_ids == []
    assert target_state.last_run_reason == "scheduled_daily"
    assert target_state.last_run_status == "success"
    assert target_state.last_successful_fingerprint

    run_log = load_run_log(config.state_file.with_name("state.runs.jsonl"))
    assert len(run_log) == 1
    assert run_log[0].status == "success"


def test_run_ima_sync_skips_articles_that_fail_wechat_fetch(tmp_path: Path):
    config = build_config(tmp_path)
    ima_client = FakeIMAClient()
    wechat_fetcher = PartiallyFailingWechatFetcher()

    summary = run_ima_sync(
        config,
        dependencies=SyncDependencies(
            ima_client=ima_client,
            wechat_fetcher=wechat_fetcher,
        ),
        reason="scheduled_daily",
    )

    assert summary.targets_processed == 1
    assert summary.rendered_pages == 1
    assert summary.updated_indexes == 1
    assert summary.status == "partial"

    folder_dir = config.output_dir / "favorites"
    assert (folder_dir / "title-alpha.html").exists()
    assert not (folder_dir / "title-beta.html").exists()

    state = load_state(config.state_file)
    target_state = state["kb-1:folder-1"]
    assert target_state.sync_status == "partial"
    assert target_state.pending_article_ids == ["media-2"]


def test_run_ima_sync_uses_unique_filenames_for_colliding_slugs(tmp_path: Path):
    config = build_config(tmp_path)
    ima_client = FakeIMAClient()
    wechat_fetcher = CollidingTitleWechatFetcher()

    summary = run_ima_sync(
        config,
        dependencies=SyncDependencies(
            ima_client=ima_client,
            wechat_fetcher=wechat_fetcher,
        ),
        reason="scheduled_daily",
    )

    assert summary.rendered_pages == 2

    folder_dir = config.output_dir / "favorites"
    page_names = sorted(path.name for path in folder_dir.glob("*.html"))
    assert "same-title.html" in page_names
    assert "same-title-media-2.html" in page_names


def test_run_ima_sync_scheduled_daily_skips_when_fingerprint_is_unchanged(tmp_path: Path):
    config = build_config(tmp_path)
    first_ima_client = FakeIMAClient()
    first_fetcher = FakeWechatFetcher()

    first_summary = run_ima_sync(
        config,
        dependencies=SyncDependencies(
            ima_client=first_ima_client,
            wechat_fetcher=first_fetcher,
        ),
        reason="scheduled_daily",
    )
    assert first_summary.status == "success"

    second_ima_client = FakeIMAClient()
    second_fetcher = FakeWechatFetcher()
    second_summary = run_ima_sync(
        config,
        dependencies=SyncDependencies(
            ima_client=second_ima_client,
            wechat_fetcher=second_fetcher,
        ),
        reason="scheduled_daily",
    )

    assert second_summary.status == "skipped"
    assert second_summary.rendered_pages == 0
    assert second_summary.updated_indexes == 0
    assert second_fetcher.urls == []


def test_run_ima_sync_manual_reason_forces_processing_even_when_fingerprint_is_unchanged(tmp_path: Path):
    config = build_config(tmp_path)
    first_summary = run_ima_sync(
        config,
        dependencies=SyncDependencies(
            ima_client=FakeIMAClient(),
            wechat_fetcher=FakeWechatFetcher(),
        ),
        reason="scheduled_daily",
    )
    assert first_summary.status == "success"

    manual_fetcher = FakeWechatFetcher()
    manual_summary = run_ima_sync(
        config,
        dependencies=SyncDependencies(
            ima_client=FakeIMAClient(),
            wechat_fetcher=manual_fetcher,
        ),
        reason="manual",
        force=True,
    )

    assert manual_summary.status == "success"
    assert manual_summary.rendered_pages == 2
    assert len(manual_fetcher.urls) == 2


def test_run_ima_sync_keeps_previous_snapshot_when_ima_returns_empty(tmp_path: Path):
    config = build_config(tmp_path)
    run_ima_sync(
        config,
        dependencies=SyncDependencies(
            ima_client=FakeIMAClient(),
            wechat_fetcher=FakeWechatFetcher(),
        ),
        reason="scheduled_daily",
    )

    summary = run_ima_sync(
        config,
        dependencies=SyncDependencies(
            ima_client=FakeIMAClient(articles=[]),
            wechat_fetcher=FakeWechatFetcher(),
        ),
        reason="scheduled_daily",
    )

    assert summary.targets_processed == 1
    assert summary.rendered_pages == 0
    assert summary.updated_indexes == 0
    assert summary.status == "skipped"

    state = load_state(config.state_file)
    target_state = state["kb-1:folder-1"]
    assert "media-1" in target_state.known_article_ids
    assert target_state.article_pages["media-1"] == "favorites/title-alpha.html"


def test_run_ima_sync_records_partial_state_when_quota_is_exhausted_during_fetch(tmp_path: Path):
    config = build_config(tmp_path)
    ima_client = FakeIMAClient()
    wechat_fetcher = QuotaFailingWechatFetcher("beta")

    summary = run_ima_sync(
        config,
        dependencies=SyncDependencies(
            ima_client=ima_client,
            wechat_fetcher=wechat_fetcher,
        ),
        reason="scheduled_daily",
    )

    assert summary.status == "partial"
    assert summary.targets_partial == 1
    assert summary.rendered_pages == 1

    state = load_state(config.state_file)
    target_state = state["kb-1:folder-1"]
    assert target_state.sync_status == "partial"
    assert target_state.pending_article_ids == ["media-2"]
    assert target_state.last_quota_exhausted_at

    run_log = load_run_log(config.state_file.with_name("state.runs.jsonl"))
    assert run_log[-1].status == "partial"
    assert run_log[-1].quota_exhausted is True


def test_run_ima_sync_resumes_pending_articles_on_next_run(tmp_path: Path):
    config = build_config(tmp_path)
    partial_summary = run_ima_sync(
        config,
        dependencies=SyncDependencies(
            ima_client=FakeIMAClient(),
            wechat_fetcher=QuotaFailingWechatFetcher("beta"),
        ),
        reason="scheduled_daily",
    )
    assert partial_summary.status == "partial"

    recovery_fetcher = FakeWechatFetcher()
    recovery_summary = run_ima_sync(
        config,
        dependencies=SyncDependencies(
            ima_client=FakeIMAClient(),
            wechat_fetcher=recovery_fetcher,
        ),
        reason="scheduled_daily",
    )

    assert recovery_summary.status == "success"
    assert "https://mp.weixin.qq.com/s/beta" in recovery_fetcher.urls

    state = load_state(config.state_file)
    target_state = state["kb-1:folder-1"]
    assert target_state.sync_status == "complete"
    assert target_state.pending_article_ids == []


def test_run_ima_sync_monthly_audit_forces_full_rebuild(tmp_path: Path):
    config = build_config(tmp_path)
    run_ima_sync(
        config,
        dependencies=SyncDependencies(
            ima_client=FakeIMAClient(),
            wechat_fetcher=FakeWechatFetcher(),
        ),
        reason="scheduled_daily",
    )

    audit_fetcher = FakeWechatFetcher()
    audit_summary = run_ima_sync(
        config,
        dependencies=SyncDependencies(
            ima_client=FakeIMAClient(),
            wechat_fetcher=audit_fetcher,
        ),
        reason="monthly_audit",
        full_rescan=True,
    )

    assert audit_summary.status == "success"
    assert audit_summary.rendered_pages == 2
    assert len(audit_fetcher.urls) == 2

    state = load_state(config.state_file)
    target_state = state["kb-1:folder-1"]
    assert target_state.last_successful_monthly_audit_at
