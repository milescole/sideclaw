import json
import sys
from types import SimpleNamespace
from typing import ClassVar

import httpx

from sideclaw.config.schema import WebSearchProvider
from sideclaw.tools.web import WebFetchTool, WebSearchTool


class _FakeResponse:
    def __init__(
        self,
        *,
        status_code: int = 200,
        text: str = "",
        json_data: object | None = None,
        headers: dict[str, str] | None = None,
        url: str = "https://example.com/final",
    ) -> None:
        self.status_code = status_code
        self.text = text
        self._json_data = json_data
        self.headers = headers or {}
        self.url = url

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            request = httpx.Request("GET", self.url)
            response = httpx.Response(self.status_code, request=request)
            message = "boom"
            raise httpx.HTTPStatusError(message, request=request, response=response)

    def json(self) -> object:
        if self._json_data is None:
            msg = "No JSON payload"
            raise ValueError(msg)
        return self._json_data


class _FakeAsyncClient:
    responses: ClassVar[list[_FakeResponse]] = []
    last_get_kwargs: ClassVar[dict[str, object]] = {}

    def __init__(self, **kwargs) -> None:
        self.init_kwargs = kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def get(self, url: str, **kwargs):
        type(self).last_get_kwargs = {"url": url, **kwargs, "client_kwargs": self.init_kwargs}
        return type(self).responses.pop(0)


async def test_web_search_formats_brave_results(monkeypatch) -> None:
    _FakeAsyncClient.responses = [
        _FakeResponse(
            json_data={
                "web": {
                    "results": [
                        {
                            "title": "Result One",
                            "url": "https://example.com/1",
                            "description": "First description",
                            "age": "2 days ago",
                        },
                        {
                            "title": "Result Two",
                            "url": "https://example.com/2",
                            "description": "Second description",
                        },
                    ]
                }
            }
        )
    ]
    monkeypatch.setattr("sideclaw.tools.web.httpx.AsyncClient", _FakeAsyncClient)
    tool = WebSearchTool(provider=WebSearchProvider.brave, api_key="brave_test_key")

    result = await tool.execute(query="sideclaw", count=2)

    assert "Results for: sideclaw" in result
    assert "1. Result One" in result
    assert "https://example.com/2" in result
    assert "Published: 2 days ago" in result
    assert "Site: example.com" in result
    assert _FakeAsyncClient.last_get_kwargs["params"] == {"q": "sideclaw", "count": 2}


async def test_web_search_supports_optional_brave_filters(monkeypatch) -> None:
    _FakeAsyncClient.responses = [_FakeResponse(json_data={"web": {"results": []}})]
    monkeypatch.setattr("sideclaw.tools.web.httpx.AsyncClient", _FakeAsyncClient)
    tool = WebSearchTool(provider=WebSearchProvider.brave, api_key="brave_test_key")

    result = await tool.execute(
        query="sideclaw docs",
        count=7,
        country="US",
        search_lang="en",
        ui_lang="en-US",
        freshness="pw",
    )

    assert result == "No results for: sideclaw docs"
    assert _FakeAsyncClient.last_get_kwargs["params"] == {
        "q": "sideclaw docs",
        "count": 7,
        "country": "US",
        "search_lang": "en",
        "ui_lang": "en-US",
        "freshness": "pw",
    }


async def test_web_search_retries_transient_brave_errors(monkeypatch) -> None:
    _FakeAsyncClient.responses = [
        _FakeResponse(status_code=500, json_data={"error": "server error"}),
        _FakeResponse(json_data={"web": {"results": []}}),
    ]
    monkeypatch.setattr("sideclaw.tools.web.httpx.AsyncClient", _FakeAsyncClient)
    tool = WebSearchTool(provider=WebSearchProvider.brave, api_key="brave_test_key")

    result = await tool.execute(query="retry me")

    assert result == "No results for: retry me"
    assert _FakeAsyncClient.responses == []


async def test_web_search_rejects_invalid_country() -> None:
    tool = WebSearchTool(provider=WebSearchProvider.brave, api_key="brave_test_key")

    result = await tool.execute(query="sideclaw", country="us")

    assert "Invalid 'country'" in result


async def test_web_fetch_rejects_invalid_scheme() -> None:
    tool = WebFetchTool()

    result = await tool.execute(url="file:///etc/passwd")

    parsed = json.loads(result)
    assert parsed["success"] is False
    assert "Only http/https allowed" in parsed["error"]


async def test_web_fetch_extracts_html_with_fallback_markdown(monkeypatch) -> None:
    _FakeAsyncClient.responses = [
        _FakeResponse(
            text=(
                "<html><body><article><h1>Hello</h1><p>Paragraph</p>"
                '<a href="https://example.com/docs">Docs</a></article></body></html>'
            ),
            headers={"content-type": "text/html; charset=utf-8"},
        )
    ]
    monkeypatch.setattr("sideclaw.tools.web.httpx.AsyncClient", _FakeAsyncClient)
    monkeypatch.delitem(sys.modules, "readability", raising=False)
    tool = WebFetchTool()

    result = await tool.execute(url="https://example.com", extract_mode="markdown")

    parsed = json.loads(result)
    assert parsed["success"] is True
    assert parsed["extractor"] == "fallback"
    assert "# Hello" in parsed["text"]
    assert "[Docs](https://example.com/docs)" in parsed["text"]


async def test_web_fetch_formats_json_payload(monkeypatch) -> None:
    _FakeAsyncClient.responses = [
        _FakeResponse(
            json_data={"ok": True, "name": "sideclaw"},
            headers={"content-type": "application/json"},
        )
    ]
    monkeypatch.setattr("sideclaw.tools.web.httpx.AsyncClient", _FakeAsyncClient)
    tool = WebFetchTool(max_chars=500)

    result = await tool.execute(url="https://example.com/data.json")

    parsed = json.loads(result)
    assert parsed["success"] is True
    assert parsed["extractor"] == "json"
    assert '"name": "sideclaw"' in parsed["text"]


async def test_web_fetch_uses_readability_when_available(monkeypatch) -> None:
    class _FakeDocument:
        def __init__(self, text: str) -> None:
            self._text = text

        def summary(self) -> str:
            return "<div><p>Readable body</p></div>"

        def title(self) -> str:
            return "Readable Title"

    _FakeAsyncClient.responses = [
        _FakeResponse(
            text="<html><body><article>ignored</article></body></html>",
            headers={"content-type": "text/html"},
        )
    ]
    monkeypatch.setattr("sideclaw.tools.web.httpx.AsyncClient", _FakeAsyncClient)
    monkeypatch.setitem(sys.modules, "readability", SimpleNamespace(Document=_FakeDocument))
    tool = WebFetchTool()

    result = await tool.execute(url="https://example.com")

    parsed = json.loads(result)
    assert parsed["success"] is True
    assert parsed["extractor"] == "readability"
    assert parsed["text"].startswith("# Readable Title")
