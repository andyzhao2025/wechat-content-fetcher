from __future__ import annotations

import argparse
import json
from pathlib import Path

from wechat_content_fetcher.config import load_config
from wechat_content_fetcher.ima_client import IMAApiRunner, IMAKnowledgeBaseClient
from wechat_content_fetcher.models import SyncDependencies
from wechat_content_fetcher.pages import prepare_github_pages_artifact
from wechat_content_fetcher.sync import run_fixture_sync, run_ima_sync
from wechat_content_fetcher.wechat_fetcher import UrlMdWechatFetcher


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export WeChat articles from IMA folders into a static site.")
    parser.add_argument("--config", default="config.example.json", help="Path to JSON config file.")
    parser.add_argument(
        "--mode",
        choices=["fixture", "ima", "pages"],
        default="fixture",
        help="Execution mode. 'fixture' runs the built-in fixture data. 'ima' calls the local IMA API bridge and url-md. 'pages' prepares a GitHub Pages artifact from the current output directory.",
    )
    parser.add_argument(
        "--ima-script",
        default=str(
            Path(__file__).resolve().parents[3] / "ima-skills-unpacked" / "ima-skill" / "ima_api.cjs"
        ),
        help="Path to ima_api.cjs bridge script.",
    )
    parser.add_argument(
        "--reason",
        choices=["scheduled_daily", "manual", "monthly_audit"],
        default="scheduled_daily",
        help="Execution reason for IMA mode.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force processing even if metadata fingerprint is unchanged.",
    )
    parser.add_argument(
        "--full-rescan",
        action="store_true",
        help="Fetch all articles instead of only changed or pending ones.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    config = load_config(Path(args.config))
    if args.mode == "fixture":
        summary = run_fixture_sync(config)
        print(
            f"fixture sync complete: targets={summary.targets_processed}, "
            f"pages={summary.rendered_pages}, indexes={summary.updated_indexes}"
        )
        return 0

    if args.mode == "ima":
        summary = run_ima_sync(
            config,
            dependencies=SyncDependencies(
                ima_client=IMAKnowledgeBaseClient(IMAApiRunner(Path(args.ima_script))),
                wechat_fetcher=UrlMdWechatFetcher(),
            ),
            reason=args.reason,
            force=args.force,
            full_rescan=args.full_rescan,
        )
        print(
            f"ima sync {summary.status}: targets={summary.targets_processed}, "
            f"pages={summary.rendered_pages}, indexes={summary.updated_indexes}, "
            f"skipped={summary.targets_skipped}, partial={summary.targets_partial}"
        )
        if summary.error_summary:
            print(f"details: {summary.error_summary}")
        print(
            "IMA_SYNC_RESULT="
            + json.dumps(
                {
                    "status": summary.status,
                    "targets_processed": summary.targets_processed,
                    "rendered_pages": summary.rendered_pages,
                    "updated_indexes": summary.updated_indexes,
                    "targets_skipped": summary.targets_skipped,
                    "targets_partial": summary.targets_partial,
                    "error_summary": summary.error_summary,
                    "quota_exhausted": summary.quota_exhausted,
                },
                ensure_ascii=False,
            )
        )
        return 0

    if args.mode == "pages":
        artifact_dir = prepare_github_pages_artifact(config)
        print(f"github pages artifact prepared: {artifact_dir}")
        return 0

    raise ValueError(f"unsupported mode: {args.mode}")


if __name__ == "__main__":
    raise SystemExit(main())
