from __future__ import annotations

import json
from pathlib import Path

from wechat_content_fetcher.models import (
    FolderSnapshot,
    SyncRunRecord,
    TargetConfig,
    TargetSyncState,
)
from wechat_content_fetcher.state import compute_folder_delta
from wechat_content_fetcher.storage import (
    append_run_log,
    load_run_log,
    load_state,
    save_state,
)


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


def test_load_state_migrates_legacy_snapshot_format(tmp_path: Path):
    state_file = tmp_path / "state.json"
    state_file.write_text(
        json.dumps(
            {
                "kb-1:folder-1": {
                    "article_ids": ["media-1"],
                    "article_pages": {"media-1": "favorites/title-alpha.html"},
                    "article_groups": {"media-1": "01"},
                }
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    state = load_state(state_file)

    loaded = state["kb-1:folder-1"]
    assert loaded.target_key == "kb-1:folder-1"
    assert loaded.sync_status == "complete"
    assert loaded.known_article_ids == ["media-1"]
    assert loaded.pending_article_ids == []
    assert loaded.article_pages == {"media-1": "favorites/title-alpha.html"}
    assert loaded.article_groups == {"media-1": "01"}


def test_save_and_load_state_preserves_rich_target_fields(tmp_path: Path):
    state_file = tmp_path / "state.json"
    original = TargetSyncState(
        target_key="kb-1:folder-1",
        sync_status="partial",
        known_article_ids=["media-1", "media-2"],
        pending_article_ids=["media-2"],
        article_pages={"media-1": "favorites/title-alpha.html"},
        article_groups={"media-1": "01", "media-2": "02"},
        last_seen_fingerprint="seen-1",
        last_successful_fingerprint="success-1",
        last_successful_incremental_sync_at="2026-07-06T00:10:00+08:00",
        last_successful_full_sync_at="2026-07-05T08:00:00+08:00",
        last_successful_monthly_audit_at="2026-07-01T00:00:00+08:00",
        last_quota_exhausted_at="2026-07-06T00:11:00+08:00",
        last_run_reason="scheduled_daily",
        last_run_status="partial",
        last_error="quota exhausted",
    )

    save_state(state_file, {original.target_key: original})
    loaded = load_state(state_file)

    restored = loaded[original.target_key]
    assert restored == original


def test_append_run_log_persists_append_only_records(tmp_path: Path):
    log_file = tmp_path / "run-log.jsonl"
    first = SyncRunRecord(
        run_id="run-1",
        started_at="2026-07-06T00:01:00+08:00",
        ended_at="2026-07-06T00:02:00+08:00",
        reason="scheduled_daily",
        status="skipped",
        targets=["kb-1:folder-1"],
        fingerprint_before={"kb-1:folder-1": "fp-1"},
        fingerprint_after={"kb-1:folder-1": "fp-1"},
        articles_added={"kb-1:folder-1": []},
        articles_removed={"kb-1:folder-1": []},
        articles_fetched={"kb-1:folder-1": []},
        articles_failed={"kb-1:folder-1": []},
        pending_article_ids={"kb-1:folder-1": []},
        quota_exhausted=False,
        publish_changed=False,
        published=False,
        error_summary="",
    )
    second = SyncRunRecord(
        run_id="run-2",
        started_at="2026-07-07T00:01:00+08:00",
        ended_at="2026-07-07T00:05:00+08:00",
        reason="manual",
        status="success",
        targets=["kb-1:folder-1"],
        fingerprint_before={"kb-1:folder-1": "fp-1"},
        fingerprint_after={"kb-1:folder-1": "fp-2"},
        articles_added={"kb-1:folder-1": ["media-2"]},
        articles_removed={"kb-1:folder-1": []},
        articles_fetched={"kb-1:folder-1": ["media-2"]},
        articles_failed={"kb-1:folder-1": []},
        pending_article_ids={"kb-1:folder-1": []},
        quota_exhausted=False,
        publish_changed=True,
        published=True,
        error_summary="",
    )

    append_run_log(log_file, first)
    append_run_log(log_file, second)

    records = load_run_log(log_file)
    assert records == [first, second]
