from __future__ import annotations

from pathlib import Path

from wechat_content_fetcher.sync import SyncSummary


def test_cli_returns_zero_for_partial_ima_sync(monkeypatch, tmp_path: Path, capsys):
    from wechat_content_fetcher import cli

    config_path = tmp_path / "config.json"
    config_path.write_text(
        """{
  "site_title": "Demo",
  "output_dir": "site_output/demo",
  "state_file": ".state.json",
  "targets": []
}""",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        cli,
        "run_ima_sync",
        lambda *args, **kwargs: SyncSummary(
            rendered_pages=0,
            updated_indexes=0,
            targets_processed=1,
            status="partial",
            targets_skipped=0,
            targets_partial=1,
            error_summary="IMA quota exhausted",
            quota_exhausted=True,
        ),
    )

    monkeypatch.setattr(
        "sys.argv",
        [
            "run_fetcher.py",
            "--config",
            str(config_path),
            "--mode",
            "ima",
        ],
    )

    assert cli.main() == 0
    stdout = capsys.readouterr().out
    assert "ima sync partial" in stdout
    assert "details: IMA quota exhausted" in stdout
