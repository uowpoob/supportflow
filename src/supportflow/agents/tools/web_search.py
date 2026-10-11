"""本地资料不足时的联网搜索，只返回真实 URL 和网页摘要，不生成答案。"""

from urllib.parse import urlsplit

import httpx

from supportflow.agents.graph.state import WebSource


class WebSearchUnavailable(RuntimeError):
    """配置缺失、服务失败或响应格式异常；错误不包含密钥和请求正文。"""


async def search_web(query: str) -> list[WebSource]:
    """使用 Tavily Search 获取本轮资料；未配置时不会发送网络请求。"""
    from supportflow.core.config import settings

    query = query.strip()
    if not query:
        raise ValueError("搜索问题不能为空")
    api_key = settings.TAVILY_API_KEY.get_secret_value().strip()
    if not api_key:
        raise WebSearchUnavailable("联网搜索未配置")

    try:
        async with httpx.AsyncClient(
            trust_env=False, timeout=settings.WEB_SEARCH_TIMEOUT_SECONDS,
        ) as client:
            response = await client.post(
                settings.TAVILY_BASE_URL.rstrip("/") + "/search",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "query": query,
                    "topic": "general",
                    "search_depth": "basic",
                    "max_results": settings.WEB_SEARCH_MAX_RESULTS,
                    "include_answer": False,
                    "include_raw_content": False,
                },
            )
            response.raise_for_status()
            results = response.json()["results"]
    except (httpx.HTTPError, httpx.InvalidURL, ValueError, KeyError, TypeError) as exc:
        raise WebSearchUnavailable(f"联网搜索暂不可用（{type(exc).__name__}）") from exc

    if not isinstance(results, list):
        raise WebSearchUnavailable("联网搜索返回格式异常")
    sources: list[WebSource] = []
    seen_urls: set[str] = set()
    for result in results:
        if not isinstance(result, dict):
            continue
        title, url, content = (result.get(key) for key in ("title", "url", "content"))
        if not all(isinstance(value, str) and value.strip() for value in (title, url, content)):
            continue
        url = url.strip()
        try:
            parsed = urlsplit(url)
        except ValueError:
            continue
        if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
            continue
        if url in seen_urls:
            continue
        seen_urls.add(url)
        sources.append({"title": title.strip()[:300], "url": url, "content": content.strip()[:4000]})
        if len(sources) >= settings.WEB_SEARCH_MAX_RESULTS:
            break
    return sources
