"""
RSS news connector. Parses standard RSS 2.0 feeds using the stdlib XML
parser (no extra dependency needed) -- works against essentially any
public news outlet's RSS endpoint, so this one connector definition covers
however many feeds are configured per DataSource.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any

from app.connectors.base import BaseConnector, ConnectorResult, register_connector


@register_connector("news_rss")
class RSSNewsConnector(BaseConnector):
    """
    config:
        {
            "feeds": [
                {"name": "BBC Africa", "url": "https://feeds.bbci.co.uk/news/world/africa/rss.xml"},
                {"name": "Reuters Africa", "url": "https://www.reuters.com/arc/outboundfeeds/rss/category/africa/"}
            ],
            "max_items_per_feed": 20
        }
    """

    async def fetch(self) -> ConnectorResult:
        feeds: list[dict[str, str]] = self.config.get("feeds", [])
        max_items = self.config.get("max_items_per_feed", 20)
        records: list[dict[str, Any]] = []
        raw_count = 0

        for feed in feeds:
            response = await self.client.get(feed["url"])
            response.raise_for_status()

            try:
                root = ET.fromstring(response.content)
            except ET.ParseError:
                continue

            items = root.findall(".//item")
            raw_count += len(items)

            for item in items[:max_items]:
                title = item.findtext("title") or ""
                link = item.findtext("link") or ""
                pub_date = item.findtext("pubDate") or ""
                description = item.findtext("description") or ""

                records.append(
                    {
                        "feed_name": feed.get("name", feed["url"]),
                        "title": title.strip(),
                        "link": link.strip(),
                        "description": description.strip()[:1000],
                        "published_at": pub_date,
                        "observed_at": pub_date,
                    }
                )

        return ConnectorResult(records=records, raw_count=raw_count, metadata={"source": "rss", "feed_count": len(feeds)})