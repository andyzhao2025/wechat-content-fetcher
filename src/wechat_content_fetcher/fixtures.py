from __future__ import annotations

from wechat_content_fetcher.models import WechatArticle


def build_fixture_articles() -> dict[str, WechatArticle]:
    return {
        "fixture-1": WechatArticle(
            source_url="https://mp.weixin.qq.com/s/fixture-1",
            title="Fixture WeChat Article One",
            author="Fixture Author",
            publish_time="2026-06-30",
            cover_url="",
            markdown_body="# Fixture Heading\n\nFixture body.",
        ),
        "fixture-2": WechatArticle(
            source_url="https://mp.weixin.qq.com/s/fixture-2",
            title="Fixture WeChat Article Two",
            author="Fixture Author",
            publish_time="2026-06-29",
            cover_url="",
            markdown_body="# Another Heading\n\nAnother body.",
        ),
    }
