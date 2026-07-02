from __future__ import annotations

from pathlib import Path
import json

from wechat_content_fetcher.models import FolderSnapshot


def load_state(state_file: Path) -> dict[str, FolderSnapshot]:
    if not state_file.exists():
        return {}

    raw = json.loads(state_file.read_text(encoding="utf-8"))
    snapshots: dict[str, FolderSnapshot] = {}
    for key, item in raw.items():
        snapshots[key] = FolderSnapshot(
            target_key=key,
            article_ids=item.get("article_ids", []),
            article_pages=item.get("article_pages", {}),
            article_groups=item.get("article_groups", {}),
        )
    return snapshots


def save_state(state_file: Path, snapshots: dict[str, FolderSnapshot]) -> None:
    state_file.parent.mkdir(parents=True, exist_ok=True)
    raw = {
        key: {
            "article_ids": snapshot.article_ids,
            "article_pages": snapshot.article_pages,
            "article_groups": snapshot.article_groups,
        }
        for key, snapshot in snapshots.items()
    }
    state_file.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
