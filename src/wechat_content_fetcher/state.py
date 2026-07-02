from __future__ import annotations

from wechat_content_fetcher.models import FolderDelta, FolderSnapshot


def compute_folder_delta(previous: FolderSnapshot | None, current_ids: list[str]) -> FolderDelta:
    if previous is None:
        return FolderDelta(added=sorted(current_ids), removed=[], unchanged=[])

    previous_ids = set(previous.article_ids)
    current_set = set(current_ids)

    return FolderDelta(
        added=sorted(current_set - previous_ids),
        removed=sorted(previous_ids - current_set),
        unchanged=sorted(current_set & previous_ids),
    )
