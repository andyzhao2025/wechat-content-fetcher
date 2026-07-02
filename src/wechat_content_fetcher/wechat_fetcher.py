from __future__ import annotations

import shutil
import subprocess

from wechat_content_fetcher.wechat import parse_url_md_output


class UrlMdNotFoundError(RuntimeError):
    pass


class WechatFetchError(RuntimeError):
    pass


class UrlMdWechatFetcher:
    def __init__(self, binary_name: str = "url-md"):
        self.binary_name = binary_name

    def fetch(self, url: str, timeout_seconds: int = 45):
        if not shutil.which(self.binary_name):
            raise UrlMdNotFoundError(f"{self.binary_name} binary not found in PATH")

        completed = subprocess.run(
            [
                self.binary_name,
                "md",
                url,
                "--quiet",
                "--timeout",
                str(timeout_seconds),
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout_seconds + 5,
        )
        if completed.returncode != 0:
            stderr = completed.stderr.strip()
            hint = stderr or f"{self.binary_name} failed with exit code {completed.returncode}"
            raise WechatFetchError(hint)

        return parse_url_md_output(completed.stdout, url)
