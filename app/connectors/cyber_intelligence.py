"""
AlienVault OTX (Open Threat Exchange) connector. Pulls the subscribed
pulse feed -- community-curated threat intelligence bundles containing
Indicators of Compromise (IOCs): malicious IPs, domains, file hashes,
CVEs. Requires a free OTX API key (credentials["api_key"]).
"""
from __future__ import annotations

from typing import Any

from app.connectors.base import BaseConnector, ConnectorResult, register_connector
from app.exceptions.base import ConnectorError


@register_connector("cyber_intel_otx")
class AlienVaultOTXConnector(BaseConnector):
    """
    config:
        {"limit": 20}
    credentials:
        {"api_key": "<otx_api_key>"}  # required -- https://otx.alienvault.com
    """

    PULSES_URL = "https://otx.alienvault.com/api/v1/pulses/subscribed"

    def default_headers(self) -> dict[str, str]:
        headers = super().default_headers()
        api_key = self.credentials.get("api_key")
        if api_key:
            headers["X-OTX-API-KEY"] = api_key ### it requires an apikey
        return headers

    async def fetch(self) -> ConnectorResult:
        if "api_key" not in self.credentials:
            raise ConnectorError("AlienVault OTX connector requires an 'api_key' credential")

        limit = self.config.get("limit", 20)
        response = await self.client.get(self.PULSES_URL, params={"limit": limit})
        response.raise_for_status()
        payload = response.json()

        pulses: list[dict[str, Any]] = payload.get("results", [])
        records: list[dict[str, Any]] = []

        for pulse in pulses:
            indicators = pulse.get("indicators", [])
            indicator_summary = {}
            for ind in indicators:
                ind_type = ind.get("type", "unknown")
                indicator_summary[ind_type] = indicator_summary.get(ind_type, 0) + 1

            records.append(
                {
                    "pulse_id": pulse.get("id"),
                    "name": pulse.get("name"),
                    "description": pulse.get("description"),
                    "author": pulse.get("author_name"),
                    "tags": pulse.get("tags", []),
                    "targeted_countries": pulse.get("targeted_countries", []),
                    "indicator_count": len(indicators),
                    "indicator_type_breakdown": indicator_summary,
                    "created": pulse.get("created"),
                    "observed_at": pulse.get("modified") or pulse.get("created"),
                }
            )

        return ConnectorResult(
            records=records, raw_count=len(pulses), metadata={"source": "alienvault_otx"}
        )