from __future__ import annotations

from filecmp import cmpfiles
from filecmp import dircmp
from pathlib import Path


def build_commit_message(date_text: str) -> str:
    return f"chore: daily sync {date_text}"


def site_has_changes(previous_dir: Path, current_dir: Path) -> bool:
    if not previous_dir.exists() and current_dir.exists():
        return True
    if previous_dir.exists() and not current_dir.exists():
        return True
    if not previous_dir.exists() and not current_dir.exists():
        return False

    comparison = dircmp(previous_dir, current_dir)
    _, mismatches, errors = cmpfiles(previous_dir, current_dir, comparison.common_files, shallow=False)
    if comparison.left_only or comparison.right_only or mismatches or errors or comparison.funny_files:
        return True

    for subdir in comparison.common_dirs:
        if site_has_changes(previous_dir / subdir, current_dir / subdir):
            return True
    return False
