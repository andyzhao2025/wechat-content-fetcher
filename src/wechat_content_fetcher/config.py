from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json

from wechat_content_fetcher.models import TargetConfig


@dataclass(frozen=True)
class SiteConfig:
    site_title: str
    output_dir: Path
    state_file: Path
    targets: list[TargetConfig]
    base_url: str = ""
    publish_mode: str = "github-pages"
    build_notebooklm_bundles: bool = True
    notebooklm_dir_name: str = "notebooklm"
    bundle_mode: str = "incremental"
    max_bundle_articles: int = 25
    max_bundle_words: int = 120000


def load_config(config_path: Path) -> SiteConfig:
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    targets = [
        TargetConfig(
            knowledge_base_id=item["knowledge_base_id"],
            folder_id=item["folder_id"],
            folder_name=item["folder_name"],
            knowledge_base_name=item.get("knowledge_base_name"),
        )
        for item in raw["targets"]
    ]
    output_dir = Path(raw.get("output_dir", "site_output"))
    state_file = Path(raw.get("state_file", ".qiaomu-state.json"))
    return SiteConfig(
        site_title=raw.get("site_title", "Qiaomu WeChat Library"),
        output_dir=output_dir,
        state_file=state_file,
        targets=targets,
        base_url=raw.get("base_url", ""),
        publish_mode=raw.get("publish_mode", "github-pages"),
        build_notebooklm_bundles=raw.get("build_notebooklm_bundles", True),
        notebooklm_dir_name=raw.get("notebooklm_dir_name", "notebooklm"),
        bundle_mode=raw.get("bundle_mode", "incremental"),
        max_bundle_articles=int(raw.get("max_bundle_articles", 25)),
        max_bundle_words=int(raw.get("max_bundle_words", 120000)),
    )
