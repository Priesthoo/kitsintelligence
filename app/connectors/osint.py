"""
GDELT 2.0 Doc API connector. GDELT monitors global news media in over 100
languages and is free with no API key -- a strong general-purpose OSINT
source for tracking mentions of specific topics, regions, or entities
across worldwide press.
"""
from __future__ import annotations

from typing import Any

from app.connectors.base import BaseConnector, ConnectorResult, register_connector


@register_connector("osint_gdelt")
class GDELTConnector(BaseConnector):
    """
    config:
        {"queries": ["Nigeria security", "West Africa piracy"], "max_records_per_query": 25, "timespan": "24h"}
    """

    BASE_URL = "https://api.gdeltproject.org/api/v2/doc/doc"

    async def fetch(self) -> ConnectorResult:
        queries: list[str] = self.config.get("queries", ["Nigeria"])
        max_records = self.config.get("max_records_per_query", 25)
        timespan = self.config.get("timespan", "24h")

        records: list[dict[str, Any]] = []
        raw_count = 0

        for query in queries:
            params = {
                "query": query,
                "mode": "artlist",
                "maxrecords": max_records,
                "timespan": timespan,
                "format": "json",
            }
            response = await self.client.get(self.BASE_URL, params=params)
            response.raise_for_status()

            try:
                payload = response.json()
            except ValueError:
                continue

            articles = payload.get("articles", [])
            raw_count += len(articles)

            for article in articles:
                records.append(
                    {
                        "query": query,
                        "title": article.get("title"),
                        "url": article.get("url"),
                        "source_domain": article.get("domain"),
                        "language": article.get("language"),
                        "country": article.get("sourcecountry"),
                        "published_at": article.get("seendate"),
                        "observed_at": article.get("seendate"),
                    }
                )

        return ConnectorResult(records=records, raw_count=raw_count, metadata={"source": "gdelt", "queries": queries})