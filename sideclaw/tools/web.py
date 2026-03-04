"""Web tools: search and fetch."""

from typing import Any

import httpx

from sideclaw.tools.base import Tool


class WebSearchTool(Tool):
    """Search the web using Brave Search API."""

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key

    @property
    def name(self) -> str:
        return "web_search"

    @property
    def description(self) -> str:
        return "Search the web and return results"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "Search query"}},
            "required": ["query"],
        }

    async def execute(self, **kwargs) -> str:
        if not self._api_key:
            return "Error: Web search API key not configured"
        query = kwargs["query"]
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    "https://api.search.brave.com/res/v1/web/search",
                    params={"q": query, "count": 5},
                    headers={"X-Subscription-Token": self._api_key, "Accept": "application/json"},
                    timeout=15,
                )
                resp.raise_for_status()
                data = resp.json()
                results = data.get("web", {}).get("results", [])
                if not results:
                    return "No results found."
                lines = []
                for r in results[:5]:
                    lines.append(f"**{r['title']}**\n{r.get('description', '')}\n{r['url']}\n")
                return "\n".join(lines)
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as e:
            return f"Error: {e}"


class WebFetchTool(Tool):
    """Fetch content from a URL."""

    @property
    def name(self) -> str:
        return "web_fetch"

    @property
    def description(self) -> str:
        return "Fetch the text content of a URL"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {"url": {"type": "string", "description": "URL to fetch"}},
            "required": ["url"],
        }

    async def execute(self, **kwargs) -> str:
        url = kwargs["url"]
        try:
            async with httpx.AsyncClient(follow_redirects=True) as client:
                resp = await client.get(url, timeout=15)
                resp.raise_for_status()
                text = resp.text
                if len(text) > 10000:
                    text = text[:10000] + "\n\n... (truncated)"
                return text
        except (httpx.HTTPError, TypeError, ValueError) as e:
            return f"Error fetching {url}: {e}"
