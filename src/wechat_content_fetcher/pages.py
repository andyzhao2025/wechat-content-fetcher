from __future__ import annotations

from pathlib import Path
import shutil

from wechat_content_fetcher.config import SiteConfig


def prepare_github_pages_artifact(config: SiteConfig, artifact_dir_name: str = "_pages") -> Path:
    source_dir = config.output_dir
    artifact_dir = _resolve_artifact_dir(source_dir, artifact_dir_name)

    if artifact_dir.exists():
        shutil.rmtree(artifact_dir)
    shutil.copytree(
        source_dir,
        artifact_dir,
        ignore=shutil.ignore_patterns(artifact_dir_name),
    )
    (artifact_dir / ".nojekyll").write_text("", encoding="utf-8")
    if config.base_url:
        _rewrite_notebooklm_url_lists(artifact_dir, config.base_url)
    return artifact_dir


def _resolve_artifact_dir(source_dir: Path, artifact_dir_name: str) -> Path:
    for candidate in (source_dir, *source_dir.parents):
        if candidate.name == "site_output":
            return candidate / artifact_dir_name
    return source_dir.parent / artifact_dir_name


def _rewrite_notebooklm_url_lists(artifact_dir: Path, base_url: str) -> None:
    notebooklm_root = artifact_dir / "notebooklm"
    if not notebooklm_root.exists():
        return

    for target_dir in notebooklm_root.iterdir():
        if not target_dir.is_dir():
            continue
        bundle_files = sorted(
            path.name
            for path in target_dir.glob("*.html")
            if path.name != "index.html"
        )
        urls = [
            f"{base_url.rstrip('/')}/notebooklm/{target_dir.name}/{file_name}"
            for file_name in bundle_files
        ]
        (target_dir / "notebooklm-urls.txt").write_text(
            "\n".join(urls) + ("\n" if urls else ""),
            encoding="utf-8",
        )
