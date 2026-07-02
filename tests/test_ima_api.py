import pytest

from wechat_content_fetcher.ima_client import (
    IMAApiError,
    IMAApiRunner,
    IMAKnowledgeBaseClient,
    IMAKnowledgeItem,
    IMAListPage,
    extract_wechat_article_url,
    parse_ima_list_page,
    parse_ima_response,
)


def test_parse_ima_response_returns_data_on_success():
    payload = '{"code":0,"msg":"success","data":{"items":[1,2,3]}}'

    data = parse_ima_response(payload)

    assert data == {"items": [1, 2, 3]}


def test_parse_ima_response_raises_on_business_error():
    payload = '{"code":200002,"msg":"skill auth failed","data":{}}'

    with pytest.raises(IMAApiError) as exc:
        parse_ima_response(payload)

    assert exc.value.code == 200002
    assert "skill auth failed" in str(exc.value)


def test_parse_ima_list_page_extracts_items_and_pagination():
    payload = """
    {
      "code": 0,
      "msg": "success",
      "data": {
        "knowledge_list": [
          {
            "media_id": "media-1",
            "title": "Article One",
            "parent_folder_id": "folder-a"
          },
          {
            "folder_id": "folder-child",
            "name": "Sub Folder",
            "file_number": 2,
            "folder_number": 0,
            "parent_folder_id": "folder-a",
            "is_top": false
          }
        ],
        "is_end": false,
        "next_cursor": "cursor-2",
        "current_path": [
          {
            "folder_id": "folder-a",
            "name": "Favorites",
            "file_number": 1,
            "folder_number": 1,
            "parent_folder_id": "kb-1",
            "is_top": true
          }
        ]
      }
    }
    """

    page = parse_ima_list_page(payload)

    assert page.is_end is False
    assert page.next_cursor == "cursor-2"
    assert page.current_path == ["Favorites"]
    assert page.items == [
        IMAKnowledgeItem(
            item_type="article",
            item_id="media-1",
            title="Article One",
            parent_folder_id="folder-a",
        ),
        IMAKnowledgeItem(
            item_type="folder",
            item_id="folder-child",
            title="Sub Folder",
            parent_folder_id="folder-a",
        ),
    ]


def test_parse_ima_list_page_recognizes_media_type_99_as_folder():
    payload = """
    {
      "code": 0,
      "msg": "success",
      "data": {
        "knowledge_list": [
          {
            "media_id": "folder-embedded",
            "title": "01 直流侧",
            "parent_folder_id": "folder-root",
            "media_type": 99
          },
          {
            "media_id": "media-2",
            "title": "Article Two",
            "parent_folder_id": "folder-root",
            "media_type": 11
          }
        ],
        "is_end": true,
        "next_cursor": "",
        "current_path": []
      }
    }
    """

    page = parse_ima_list_page(payload)

    assert page.items == [
        IMAKnowledgeItem(
            item_type="folder",
            item_id="folder-embedded",
            title="01 直流侧",
            parent_folder_id="folder-root",
        ),
        IMAKnowledgeItem(
            item_type="article",
            item_id="media-2",
            title="Article Two",
            parent_folder_id="folder-root",
        ),
    ]


def test_parse_ima_list_page_tolerates_missing_lists():
    payload = '{"code":0,"msg":"success","data":{"is_end":true,"next_cursor":"","current_path":[]}}'

    page = parse_ima_list_page(payload)

    assert page == IMAListPage(items=[], is_end=True, next_cursor="", current_path=[])


@pytest.mark.parametrize(
    ("media_payload", "expected"),
    [
        ('{"code":0,"msg":"success","data":{"url_info":{"url":"https://mp.weixin.qq.com/s/abc"}}}', "https://mp.weixin.qq.com/s/abc"),
        ('{"code":0,"msg":"success","data":{"url_info":{"url":"https://example.com/plain"}}}', None),
        ('{"code":0,"msg":"success","data":{"media_type":11}}', None),
    ],
)
def test_extract_wechat_article_url_only_returns_wechat_links(media_payload: str, expected: str | None):
    assert extract_wechat_article_url(media_payload) == expected


class FakeRunner:
    def __init__(self, responses: dict[tuple[str, str], str]):
        self.responses = responses
        self.calls: list[tuple[str, str]] = []

    def call(self, api_path: str, body: dict):
        key = (api_path, str(body))
        self.calls.append(key)
        try:
            return self.responses[key]
        except KeyError as exc:
            raise AssertionError(f"Unexpected API call: {key}") from exc


def test_list_folder_articles_recurses_into_nested_folders():
    root_body = {
        "knowledge_base_id": "kb-1",
        "cursor": "",
        "limit": 50,
        "folder_id": "folder-root",
    }
    child_body = {
        "knowledge_base_id": "kb-1",
        "cursor": "",
        "limit": 50,
        "folder_id": "folder-child",
    }
    responses = {
        (
            "openapi/wiki/v1/get_knowledge_list",
            str(root_body),
        ): """
        {
          "code": 0,
          "msg": "success",
          "data": {
            "knowledge_list": [
              {
                "media_id": "folder-child",
                "title": "01 直流侧",
                "parent_folder_id": "folder-root",
                "media_type": 99
              },
              {
                "media_id": "media-root",
                "title": "Root Article",
                "parent_folder_id": "folder-root",
                "media_type": 11
              }
            ],
            "is_end": true,
            "next_cursor": "",
            "current_path": []
          }
        }
        """,
        (
            "openapi/wiki/v1/get_knowledge_list",
            str(child_body),
        ): """
        {
          "code": 0,
          "msg": "success",
          "data": {
            "knowledge_list": [
              {
                "media_id": "media-child",
                "title": "Child Article",
                "parent_folder_id": "folder-child",
                "media_type": 11
              }
            ],
            "is_end": true,
            "next_cursor": "",
            "current_path": []
          }
        }
        """,
        (
            "openapi/wiki/v1/get_media_info",
            str({"media_id": "media-root"}),
        ): '{"code":0,"msg":"success","data":{"url_info":{"url":"https://mp.weixin.qq.com/s/root"}}}',
        (
            "openapi/wiki/v1/get_media_info",
            str({"media_id": "media-child"}),
        ): '{"code":0,"msg":"success","data":{"url_info":{"url":"https://mp.weixin.qq.com/s/child"}}}',
    }
    client = IMAKnowledgeBaseClient(FakeRunner(responses))

    articles = client.list_folder_articles("kb-1", "folder-root")

    assert [(article.article_id, article.title, article.source_url) for article in articles] == [
        ("media-root", "Root Article", "https://mp.weixin.qq.com/s/root"),
        ("media-child", "Child Article", "https://mp.weixin.qq.com/s/child"),
    ]


def test_list_folder_articles_skips_media_info_failures():
    body = {
        "knowledge_base_id": "kb-1",
        "cursor": "",
        "limit": 50,
        "folder_id": "folder-root",
    }
    responses = {
        (
            "openapi/wiki/v1/get_knowledge_list",
            str(body),
        ): """
        {
          "code": 0,
          "msg": "success",
          "data": {
            "knowledge_list": [
              {
                "media_id": "media-bad",
                "title": "Broken Article",
                "parent_folder_id": "folder-root",
                "media_type": 11
              },
              {
                "media_id": "media-good",
                "title": "Good Article",
                "parent_folder_id": "folder-root",
                "media_type": 11
              }
            ],
            "is_end": true,
            "next_cursor": "",
            "current_path": []
          }
        }
        """,
        (
            "openapi/wiki/v1/get_media_info",
            str({"media_id": "media-bad"}),
        ): '{"code":-100,"msg":"fetch failed"}',
        (
            "openapi/wiki/v1/get_media_info",
            str({"media_id": "media-good"}),
        ): '{"code":0,"msg":"success","data":{"url_info":{"url":"https://mp.weixin.qq.com/s/good"}}}',
    }
    client = IMAKnowledgeBaseClient(FakeRunner(responses))

    articles = client.list_folder_articles("kb-1", "folder-root")

    assert [(article.article_id, article.title, article.source_url) for article in articles] == [
        ("media-good", "Good Article", "https://mp.weixin.qq.com/s/good"),
    ]
