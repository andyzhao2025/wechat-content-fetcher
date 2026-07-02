from pathlib import Path

from wechat_content_fetcher.models import RenderedArticle
from wechat_content_fetcher.renderer import render_folder_index


def test_render_folder_index_lists_all_articles(tmp_path: Path):
    output_path = tmp_path / "index.html"
    articles = [
        RenderedArticle(
            article_id="a1",
            title="First Article",
            author="Alice",
            publish_time="2026-06-30",
            source_url="https://mp.weixin.qq.com/s/1",
            page_path=Path("first-article.html"),
        ),
        RenderedArticle(
            article_id="a2",
            title="Second Article",
            author="Bob",
            publish_time="2026-06-29",
            source_url="https://mp.weixin.qq.com/s/2",
            page_path=Path("second-article.html"),
        ),
    ]

    render_folder_index(
        output_path=output_path,
        folder_title="Favorites",
        articles=articles,
    )

    html = output_path.read_text(encoding="utf-8")
    assert "Favorites" in html
    assert "First Article" in html
    assert "Second Article" in html
    assert "first-article.html" in html
    assert "second-article.html" in html
