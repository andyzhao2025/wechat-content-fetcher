from __future__ import annotations

from html import escape
from pathlib import Path

import markdown as markdown_lib

from wechat_content_fetcher.assets import localize_article_for_output
from wechat_content_fetcher.models import RenderedArticle
from wechat_content_fetcher.models import WechatArticle


def render_folder_index(output_path: Path, folder_title: str, articles: list[RenderedArticle]) -> None:
    article_items = "\n".join(
        (
            "<li>"
            f"<a href=\"{escape(article.page_path.as_posix())}\">{escape(article.title)}</a>"
            f" <span>{escape(article.author)}</span>"
            f" <time>{escape(article.publish_time)}</time>"
            "</li>"
        )
        for article in articles
    )

    html = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(folder_title)}</title>
</head>
<body>
  <main>
    <h1>{escape(folder_title)}</h1>
    <ol>
      {article_items}
    </ol>
  </main>
</body>
</html>
"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")


def render_article_page(output_path: Path, article: WechatArticle) -> None:
    article = localize_article_for_output(article, output_path)
    body_html = markdown_lib.markdown(article.markdown_body)
    cover_html = (
        f'<img src="{escape(article.cover_url)}" alt="{escape(article.title)} cover">'
        if article.cover_url
        else ""
    )
    html = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(article.title)}</title>
</head>
<body>
  <main>
    <header>
      <p><a href="{escape(article.source_url)}">原文链接</a></p>
      <h1>{escape(article.title)}</h1>
      <p>{escape(article.author)}</p>
      <time>{escape(article.publish_time)}</time>
      {cover_html}
    </header>
    <article>{body_html}</article>
  </main>
</body>
</html>
"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
