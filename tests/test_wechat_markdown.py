from wechat_content_fetcher.wechat import parse_url_md_output


def test_parse_url_md_output_extracts_frontmatter_and_markdown_body():
    raw = """---
title: Sample Article
author: Alice
publish_time: 2026-06-30
cover_url: https://example.com/cover.jpg
---

# Heading

Hello from WeChat.
"""

    article = parse_url_md_output(raw, "https://mp.weixin.qq.com/s/example")

    assert article.title == "Sample Article"
    assert article.author == "Alice"
    assert article.publish_time == "2026-06-30"
    assert article.cover_url == "https://example.com/cover.jpg"
    assert article.markdown_body == "# Heading\n\nHello from WeChat."
    assert article.source_url == "https://mp.weixin.qq.com/s/example"
