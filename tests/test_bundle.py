from pathlib import Path

from wechat_content_fetcher.bundle import BundleArticleRecord, write_target_bundles
from wechat_content_fetcher.config import SiteConfig
from wechat_content_fetcher.models import FolderSnapshot, RenderedArticle, TargetConfig, WechatArticle


def make_record(article_id: str, title: str, group_name: str, source_url: str) -> BundleArticleRecord:
    slug = source_url.rsplit("/", 1)[-1]
    return BundleArticleRecord(
        rendered=RenderedArticle(
            article_id=article_id,
            title=title,
            author="Author",
            publish_time="2026-07-01",
            source_url=source_url,
            page_path=Path(f"{slug}.html"),
            group_name=group_name,
        ),
        article=WechatArticle(
            source_url=source_url,
            title=title,
            author="Author",
            publish_time="2026-07-01",
            cover_url="",
            markdown_body=f"# {title}\n\nBody for {title}.",
        ),
    )


def test_write_target_bundles_generates_grouped_pages_and_url_manifest(tmp_path: Path):
    config = SiteConfig(
        site_title="Bundle Demo",
        output_dir=tmp_path / "site",
        state_file=tmp_path / "state.json",
        base_url="https://example.github.io/wechat",
        publish_mode="github-pages",
        notebooklm_dir_name="notebooklm",
        max_bundle_articles=2,
        max_bundle_words=1000,
        targets=[],
    )
    target = TargetConfig(
        knowledge_base_id="kb-1",
        folder_id="folder-1",
        folder_name="01储能系统设计",
    )
    records = [
        make_record("a1", "DC Article 1", "01 直流侧", "https://mp.weixin.qq.com/s/a1"),
        make_record("a2", "DC Article 2", "01 直流侧", "https://mp.weixin.qq.com/s/a2"),
        make_record("a3", "AC Article 1", "02 交流侧", "https://mp.weixin.qq.com/s/a3"),
    ]

    write_target_bundles(
        config=config,
        target=target,
        records=records,
        previous_snapshot=None,
    )

    bundle_root = config.output_dir / "notebooklm" / "01"
    assert (bundle_root / "index.html").exists()
    assert (bundle_root / "notebooklm-urls.txt").exists()
    manifest = (bundle_root / "manifest.json").read_text(encoding="utf-8")
    assert "01 直流侧" in manifest
    assert "02 交流侧" in manifest

    page_names = sorted(path.name for path in bundle_root.glob("*.html"))
    assert "01-part-001.html" in page_names
    assert "02-part-001.html" in page_names

    urls = (bundle_root / "notebooklm-urls.txt").read_text(encoding="utf-8")
    assert "https://example.github.io/wechat/notebooklm/01/01-part-001.html" in urls
    assert "https://example.github.io/wechat/notebooklm/01/02-part-001.html" in urls


def test_write_target_bundles_only_rebuilds_changed_group(tmp_path: Path):
    config = SiteConfig(
        site_title="Bundle Demo",
        output_dir=tmp_path / "site",
        state_file=tmp_path / "state.json",
        base_url="https://example.github.io/wechat",
        publish_mode="github-pages",
        notebooklm_dir_name="notebooklm",
        max_bundle_articles=3,
        max_bundle_words=1000,
        targets=[],
    )
    target = TargetConfig(
        knowledge_base_id="kb-1",
        folder_id="folder-1",
        folder_name="01储能系统设计",
    )
    first_records = [
        make_record("a1", "DC Article 1", "01 直流侧", "https://mp.weixin.qq.com/s/a1"),
        make_record("b1", "AC Article 1", "02 交流侧", "https://mp.weixin.qq.com/s/b1"),
    ]
    write_target_bundles(
        config=config,
        target=target,
        records=first_records,
        previous_snapshot=None,
    )

    bundle_root = config.output_dir / "notebooklm" / "01"
    unchanged_path = bundle_root / "02-part-001.html"
    unchanged_path.write_text(unchanged_path.read_text(encoding="utf-8") + "\nUNCHANGED-SENTINEL\n", encoding="utf-8")

    previous_snapshot = FolderSnapshot(
        target_key=target.target_key,
        article_ids=["a1", "b1"],
        article_pages={"a1": "01/a1.html", "b1": "01/b1.html"},
        article_groups={"a1": "01 直流侧", "b1": "02 交流侧"},
    )
    second_records = [
        make_record("a1", "DC Article 1", "01 直流侧", "https://mp.weixin.qq.com/s/a1"),
        make_record("a2", "DC Article 2", "01 直流侧", "https://mp.weixin.qq.com/s/a2"),
        make_record("b1", "AC Article 1", "02 交流侧", "https://mp.weixin.qq.com/s/b1"),
    ]
    write_target_bundles(
        config=config,
        target=target,
        records=second_records,
        previous_snapshot=previous_snapshot,
    )

    assert "UNCHANGED-SENTINEL" in unchanged_path.read_text(encoding="utf-8")
    dc_bundle = (bundle_root / "01-part-001.html").read_text(encoding="utf-8")
    assert "DC Article 2" in dc_bundle
