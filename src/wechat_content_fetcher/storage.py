from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from wechat_content_fetcher.models import SyncRunRecord, TargetSyncState


def load_state(state_file: Path) -> dict[str, TargetSyncState]:
    if not state_file.exists():
        return {}

    raw = json.loads(state_file.read_text(encoding="utf-8"))
    snapshots: dict[str, TargetSyncState] = {}
    for key, item in raw.items():
        if "known_article_ids" in item or "sync_status" in item:
            snapshots[key] = TargetSyncState(
                target_key=key,
                sync_status=item.get("sync_status", "never_started"),
                known_article_ids=item.get("known_article_ids", item.get("article_ids", [])),
                pending_article_ids=item.get("pending_article_ids", []),
                article_pages=item.get("article_pages", {}),
                article_groups=item.get("article_groups", {}),
                last_seen_fingerprint=item.get("last_seen_fingerprint", ""),
                last_successful_fingerprint=item.get("last_successful_fingerprint", ""),
                last_successful_incremental_sync_at=item.get("last_successful_incremental_sync_at", ""),
                last_successful_full_sync_at=item.get("last_successful_full_sync_at", ""),
                last_successful_monthly_audit_at=item.get("last_successful_monthly_audit_at", ""),
                last_quota_exhausted_at=item.get("last_quota_exhausted_at", ""),
                last_run_reason=item.get("last_run_reason", ""),
                last_run_status=item.get("last_run_status", ""),
                last_error=item.get("last_error", ""),
            )
            continue

        snapshots[key] = TargetSyncState(
            target_key=key,
            sync_status="complete",
            known_article_ids=item.get("article_ids", []),
            pending_article_ids=[],
            article_pages=item.get("article_pages", {}),
            article_groups=item.get("article_groups", {}),
        )
    return snapshots


def save_state(state_file: Path, snapshots: dict[str, TargetSyncState]) -> None:
    state_file.parent.mkdir(parents=True, exist_ok=True)
    raw = {
        key: {
            "sync_status": snapshot.sync_status,
            "known_article_ids": snapshot.known_article_ids,
            "pending_article_ids": snapshot.pending_article_ids,
            "article_pages": snapshot.article_pages,
            "article_groups": snapshot.article_groups,
            "last_seen_fingerprint": snapshot.last_seen_fingerprint,
            "last_successful_fingerprint": snapshot.last_successful_fingerprint,
            "last_successful_incremental_sync_at": snapshot.last_successful_incremental_sync_at,
            "last_successful_full_sync_at": snapshot.last_successful_full_sync_at,
            "last_successful_monthly_audit_at": snapshot.last_successful_monthly_audit_at,
            "last_quota_exhausted_at": snapshot.last_quota_exhausted_at,
            "last_run_reason": snapshot.last_run_reason,
            "last_run_status": snapshot.last_run_status,
            "last_error": snapshot.last_error,
        }
        for key, snapshot in snapshots.items()
    }
    state_file.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")


def append_run_log(run_log_file: Path, record: SyncRunRecord) -> None:
    run_log_file.parent.mkdir(parents=True, exist_ok=True)
    with run_log_file.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")


def load_run_log(run_log_file: Path) -> list[SyncRunRecord]:
    if not run_log_file.exists():
        return []

    records: list[SyncRunRecord] = []
    for line in run_log_file.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        records.append(SyncRunRecord(**payload))
    return records
