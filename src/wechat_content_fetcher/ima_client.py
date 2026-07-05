from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from wechat_content_fetcher.models import SourceArticle


class IMAApiError(RuntimeError):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class IMAKnowledgeItem:
    item_type: str
    item_id: str
    title: str
    parent_folder_id: str


@dataclass(frozen=True)
class IMAListPage:
    items: list[IMAKnowledgeItem]
    is_end: bool
    next_cursor: str
    current_path: list[str]


def parse_ima_response(payload: str) -> dict:
    response = json.loads(payload)
    code = int(response.get("code", -1))
    if code != 0:
        raise IMAApiError(code, str(response.get("msg") or "IMA API request failed"))
    return response.get("data") or {}


def parse_ima_list_page(payload: str) -> IMAListPage:
    data = parse_ima_response(payload)
    items: list[IMAKnowledgeItem] = []
    for raw_item in data.get("knowledge_list", []):
        if raw_item.get("media_type") == 99:
            items.append(
                IMAKnowledgeItem(
                    item_type="folder",
                    item_id=str(raw_item.get("media_id") or raw_item.get("folder_id") or ""),
                    title=str(raw_item.get("title") or raw_item.get("name") or ""),
                    parent_folder_id=str(raw_item.get("parent_folder_id") or ""),
                )
            )
        elif "media_id" in raw_item:
            items.append(
                IMAKnowledgeItem(
                    item_type="article",
                    item_id=str(raw_item["media_id"]),
                    title=str(raw_item.get("title") or ""),
                    parent_folder_id=str(raw_item.get("parent_folder_id") or ""),
                )
            )
        elif "folder_id" in raw_item:
            items.append(
                IMAKnowledgeItem(
                    item_type="folder",
                    item_id=str(raw_item["folder_id"]),
                    title=str(raw_item.get("name") or ""),
                    parent_folder_id=str(raw_item.get("parent_folder_id") or ""),
                )
            )

    return IMAListPage(
        items=items,
        is_end=bool(data.get("is_end", True)),
        next_cursor=str(data.get("next_cursor") or ""),
        current_path=[str(item.get("name") or "") for item in data.get("current_path", [])],
    )


def extract_wechat_article_url(payload: str) -> str | None:
    data = parse_ima_response(payload)
    url = ((data.get("url_info") or {}).get("url")) if isinstance(data, dict) else None
    if not url or not isinstance(url, str):
        return None
    if "mp.weixin.qq.com/s/" not in url and "mp.weixin.qq.com/s?" not in url:
        return None
    return url


class IMAApiRunner:
    def __init__(self, script_path: Path):
        self.script_path = script_path

    def call(self, api_path: str, body: dict[str, Any]) -> str:
        command = [
            "node",
            "--max-old-space-size=4096",
            str(self.script_path),
            api_path,
            json.dumps(body, ensure_ascii=False),
            "{}",
        ]
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        if completed.returncode != 0:
            stderr = completed.stderr.strip() or '{"code":-100,"msg":"IMA API subprocess failed"}'
            try:
                parsed = json.loads(stderr)
            except json.JSONDecodeError as exc:
                raise RuntimeError(stderr) from exc
            raise IMAApiError(int(parsed.get("code", -100)), str(parsed.get("msg") or "IMA API subprocess failed"))
        return completed.stdout


class IMAKnowledgeBaseClient:
    def __init__(self, runner: IMAApiRunner):
        self.runner = runner

    def list_folder_articles(self, knowledge_base_id: str, folder_id: str) -> list[SourceArticle]:
        articles: list[SourceArticle] = []
        visited_folders: set[str] = set()
        self._collect_folder_articles(
            knowledge_base_id=knowledge_base_id,
            folder_id=folder_id,
            articles=articles,
            visited_folders=visited_folders,
            path_segments=(),
        )
        return articles

    def _collect_folder_articles(
        self,
        knowledge_base_id: str,
        folder_id: str,
        articles: list[SourceArticle],
        visited_folders: set[str],
        path_segments: tuple[str, ...],
    ) -> None:
        if folder_id in visited_folders:
            return
        visited_folders.add(folder_id)

        child_folder_ids: list[str] = []
        child_folder_paths: dict[str, tuple[str, ...]] = {}
        cursor = ""
        while True:
            body: dict[str, Any] = {
                "knowledge_base_id": knowledge_base_id,
                "cursor": cursor,
                "limit": 50,
            }
            if folder_id and folder_id != knowledge_base_id:
                body["folder_id"] = folder_id
            page = parse_ima_list_page(self.runner.call("openapi/wiki/v1/get_knowledge_list", body))
            for item in page.items:
                if item.item_type == "folder":
                    child_folder_ids.append(item.item_id)
                    child_folder_paths[item.item_id] = path_segments + (item.title,)
                    continue

                try:
                    media_payload = self.runner.call("openapi/wiki/v1/get_media_info", {"media_id": item.item_id})
                    source_url = extract_wechat_article_url(media_payload)
                except IMAApiError as exc:
                    if exc.code == 220021:
                        raise
                    continue
                if not source_url:
                    continue
                articles.append(
                    SourceArticle(
                        article_id=item.item_id,
                        title=item.title,
                        source_url=source_url,
                        group_name=path_segments[0] if path_segments else "",
                    )
                )
            if page.is_end:
                break
            cursor = page.next_cursor

        for child_folder_id in child_folder_ids:
            self._collect_folder_articles(
                knowledge_base_id=knowledge_base_id,
                folder_id=child_folder_id,
                articles=articles,
                visited_folders=visited_folders,
                path_segments=child_folder_paths.get(child_folder_id, path_segments),
            )
