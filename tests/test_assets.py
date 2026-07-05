from io import BytesIO
from pathlib import Path

from wechat_content_fetcher.assets import localize_article_for_output, mirror_article_assets
from wechat_content_fetcher.models import WechatArticle
from wechat_content_fetcher.renderer import render_article_page


class FakeResponse(BytesIO):
    def __init__(self, payload: bytes, content_type: str):
        super().__init__(payload)
        self._content_type = content_type
        self.headers = self

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
        return False

    def get_content_type(self):
        return self._content_type


def test_mirror_article_assets_downloads_cover_and_body_images(tmp_path: Path, monkeypatch):
    payload = b"fake-image-payload"

    def fake_urlopen(request, timeout):
        return FakeResponse(payload, "image/png")

    monkeypatch.setattr("wechat_content_fetcher.assets.urlopen", fake_urlopen)
    article = WechatArticle(
        source_url="https://mp.weixin.qq.com/s/demo",
        title="Demo",
        author="Author",
        publish_time="2026-07-05",
        cover_url="https://mmbiz.qpic.cn/cover?wx_fmt=png",
        markdown_body="![body](https://mmbiz.qpic.cn/body?wx_fmt=png)",
    )

    mirrored = mirror_article_assets(tmp_path / "site", "media-1", article)

    assert mirrored.local_cover_path is not None
    assert mirrored.local_cover_path.exists()
    assert len(mirrored.asset_paths) == 2
    assert all(path.exists() for path in mirrored.asset_paths.values())


def test_render_article_page_localizes_asset_paths(tmp_path: Path):
    asset_dir = tmp_path / "site" / "assets" / "media-1"
    asset_dir.mkdir(parents=True)
    cover_path = asset_dir / "cover.png"
    body_path = asset_dir / "body.png"
    cover_path.write_bytes(b"cover")
    body_path.write_bytes(b"body")

    article = WechatArticle(
        source_url="https://mp.weixin.qq.com/s/demo",
        title="Demo",
        author="Author",
        publish_time="2026-07-05",
        cover_url="https://mmbiz.qpic.cn/cover?wx_fmt=png",
        markdown_body="![body](https://mmbiz.qpic.cn/body?wx_fmt=png)",
        asset_paths={"https://mmbiz.qpic.cn/body?wx_fmt=png": body_path},
        local_cover_path=cover_path,
    )
    output_path = tmp_path / "site" / "favorites" / "demo.html"
    render_article_page(output_path, article)

    html = output_path.read_text(encoding="utf-8")
    assert '../assets/media-1/cover.png' in html
    assert '../assets/media-1/body.png' in html


def test_localize_article_for_bundle_uses_relative_asset_paths(tmp_path: Path):
    asset_dir = tmp_path / "site" / "assets" / "media-1"
    asset_dir.mkdir(parents=True)
    body_path = asset_dir / "body.png"
    body_path.write_bytes(b"body")

    article = WechatArticle(
        source_url="https://mp.weixin.qq.com/s/demo",
        title="Demo",
        author="Author",
        publish_time="2026-07-05",
        cover_url="",
        markdown_body="![body](https://mmbiz.qpic.cn/body?wx_fmt=png)",
        asset_paths={"https://mmbiz.qpic.cn/body?wx_fmt=png": body_path},
    )
    output_path = tmp_path / "site" / "notebooklm" / "01" / "01-part-001.html"

    localized = localize_article_for_output(article, output_path)

    assert "../../assets/media-1/body.png" in localized.markdown_body
