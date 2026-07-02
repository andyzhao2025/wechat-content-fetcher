from __future__ import annotations

import yaml

from wechat_content_fetcher.models import WechatArticle


def parse_url_md_output(raw: str, source_url: str) -> WechatArticle:
    if raw.startswith("---\n"):
        parts = raw.split("---\n", 2)
        if len(parts) == 3:
            frontmatter = yaml.safe_load(parts[1]) or {}
            body = parts[2].lstrip("\n").rstrip()
            return WechatArticle(
                source_url=source_url,
                title=str(frontmatter.get("title") or "Untitled WeChat Article"),
                author=str(frontmatter.get("author") or ""),
                publish_time=str(frontmatter.get("publish_time") or ""),
                cover_url=str(frontmatter.get("cover_url") or ""),
                markdown_body=body,
            )

    return WechatArticle(
        source_url=source_url,
        title="Untitled WeChat Article",
        author="",
        publish_time="",
        cover_url="",
        markdown_body=raw.strip(),
    )
