from pathlib import Path

from wechat_content_fetcher.models import WechatArticle
from wechat_content_fetcher.renderer import render_article_page


def test_render_article_page_outputs_html_with_source_and_content(tmp_path: Path):
    output_path = tmp_path / "article.html"
    article = WechatArticle(
        source_url="https://mp.weixin.qq.com/s/example",
        title="Sample Article",
        author="Alice",
        publish_time="2026-06-30",
        cover_url="https://example.com/cover.jpg",
        markdown_body="# Heading\n\nBody text.",
    )

    render_article_page(output_path, article)

    html = output_path.read_text(encoding="utf-8")
    assert "Sample Article" in html
    assert "Alice" in html
    assert "https://mp.weixin.qq.com/s/example" in html
    assert "<h1>Heading</h1>" in html
    assert "Body text." in html
