"""
Reddit public JSON connector for social media intelligence. Uses Reddit's
unauthenticated read-only JSON endpoints (no OAuth needed for basic
polling). NOTE: anonymous access is rate-limited (~60 requests/10min) --
for production-scale polling across many subreddits, add a Reddit
"script" app's client_id/client_secret as credentials and extend this
connector to exchange them for an OAuth bearer token first.
"""
from __future__ import annotations

from typing import Any

from app.connectors.base import BaseConnector, ConnectorResult, register_connector


@register_connector("socmint_reddit")
class RedditConnector(BaseConnector):
    """
    config:
        {"subreddits": ["nigeria", "OSINT", "geopolitics"], "limit_per_subreddit": 25}
    """

    def default_headers(self) -> dict[str, str]:
        headers = super().default_headers()
        # Reddit blocks requests with generic/default User-Agents far more
        # aggressively than most APIs -- a descriptive, unique UA is required.
        headers["User-Agent"] = "OpIntPlatform-SOCMINT-Connector/1.0 (contact: ops@opint-platform.local)"
        return headers

    async def fetch(self) -> ConnectorResult:
        subreddits: list[str] = self.config.get("subreddits", ["worldnews"])
        limit = self.config.get("limit_per_subreddit", 25)

        records: list[dict[str, Any]] = []
        raw_count = 0

        for subreddit in subreddits:
            url = f"https://www.reddit.com/r/{subreddit}/new.json"
            response = await self.client.get(url, params={"limit": limit})
            response.raise_for_status()
            payload = response.json()

            children = payload.get("data", {}).get("children", [])
            raw_count += len(children)

            for child in children:
                post = child.get("data", {})
                records.append(
                    {
                        "subreddit": subreddit,
                        "post_id": post.get("id"),
                        "title": post.get("title"),
                        "author": post.get("author"),
                        "score": post.get("score"),
                        "num_comments": post.get("num_comments"),
                        "url": f"https://reddit.com{post.get('permalink', '')}",
                        "flair": post.get("link_flair_text"),
                        "created_utc": post.get("created_utc"),
                        "observed_at": post.get("created_utc"),
                    }
                )

        return ConnectorResult(
            records=records, raw_count=raw_count, metadata={"source": "reddit", "subreddits": subreddits}
        )