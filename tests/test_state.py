from wechat_content_fetcher.models import FolderSnapshot, TargetConfig
from wechat_content_fetcher.state import compute_folder_delta


def test_compute_folder_delta_tracks_added_removed_and_unchanged_articles():
    target = TargetConfig(
        knowledge_base_id="kb_1",
        folder_id="folder_1",
        folder_name="Favorites",
    )
    previous = FolderSnapshot(
        target_key=target.target_key,
        article_ids=["a1", "a2"],
        article_pages={"a1": "favorites/a1.html", "a2": "favorites/a2.html"},
    )
    current_ids = ["a2", "a3"]

    delta = compute_folder_delta(previous, current_ids)

    assert delta.added == ["a3"]
    assert delta.removed == ["a1"]
    assert delta.unchanged == ["a2"]
