from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from wechat_content_fetcher.ima_client import IMAApiError, IMAApiRunner, IMAKnowledgeBaseClient


def test_ima_api_runner_uses_explicit_node_heap_limit(monkeypatch):
    captured: dict[str, object] = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(command, 0, stdout='{"code":0,"data":{}}', stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    runner = IMAApiRunner(Path("C:/tmp/ima_api.cjs"))
    runner.call("openapi/wiki/v1/get_knowledge_list", {"limit": 1})

    assert captured["command"][:2] == ["node", "--max-old-space-size=4096"]


def test_ima_api_runner_uses_configured_node_binary(monkeypatch):
    captured: dict[str, object] = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        return subprocess.CompletedProcess(command, 0, stdout='{"code":0,"data":{}}', stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setenv("WECHAT_FETCHER_NODE_BIN", "/opt/openclaw/node")

    runner = IMAApiRunner(Path("/tmp/ima_api.cjs"))
    runner.call("openapi/wiki/v1/get_knowledge_list", {"limit": 1})

    assert captured["command"][:2] == ["/opt/openclaw/node", "--max-old-space-size=4096"]


class QuotaExceededRunner:
    def call(self, api_path: str, body: dict):
        if api_path == "openapi/wiki/v1/get_knowledge_list":
            return json.dumps(
                {
                    "code": 0,
                    "data": {
                        "knowledge_list": [
                            {
                                "media_id": "media-1",
                                "title": "Alpha",
                                "parent_folder_id": "folder-1",
                                "media_type": 6,
                            }
                        ],
                        "is_end": True,
                        "next_cursor": "",
                        "current_path": [],
                    },
                },
                ensure_ascii=False,
            )
        raise IMAApiError(220021, "资料获取次数已达上限，请明天再尝试")


def test_ima_knowledge_base_client_raises_when_media_quota_is_exhausted():
    client = IMAKnowledgeBaseClient(QuotaExceededRunner())

    with pytest.raises(IMAApiError) as exc_info:
        client.list_folder_articles("kb-1", "folder-1")

    assert exc_info.value.code == 220021
    assert [article.article_id for article in exc_info.value.partial_articles] == []


def test_ima_api_error_exposes_quota_exhaustion_helper():
    error = IMAApiError(220021, "资料获取次数已达上限，请明天再尝试")

    assert error.code == 220021
    assert error.is_quota_exhausted is True
