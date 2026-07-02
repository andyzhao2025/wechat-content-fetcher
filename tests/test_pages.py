from pathlib import Path

from wechat_content_fetcher.config import SiteConfig
from wechat_content_fetcher.pages import prepare_github_pages_artifact


def test_prepare_github_pages_artifact_copies_site_and_adds_nojekyll(tmp_path: Path):
    output_dir = tmp_path / "site_output" / "ima-storage-design"
    output_dir.mkdir(parents=True)
    (output_dir / "index.html").write_text("<html>ok</html>", encoding="utf-8")
    (output_dir / "nested").mkdir()
    (output_dir / "nested" / "page.html").write_text("<html>nested</html>", encoding="utf-8")

    config = SiteConfig(
        site_title="Demo",
        output_dir=output_dir,
        state_file=tmp_path / "state.json",
        base_url="",
        publish_mode="github-pages",
        targets=[],
    )

    artifact_dir = prepare_github_pages_artifact(config)

    assert artifact_dir == output_dir.parent / "_pages"
    assert (artifact_dir / "index.html").read_text(encoding="utf-8") == "<html>ok</html>"
    assert (artifact_dir / "nested" / "page.html").read_text(encoding="utf-8") == "<html>nested</html>"
    assert (artifact_dir / ".nojekyll").exists()
