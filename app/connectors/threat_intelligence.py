"""
CISA Known Exploited Vulnerabilities (KEV) catalog connector. Free, no API
key required. This is the U.S. government's authoritative feed of
vulnerabilities actively exploited in the wild -- a strong baseline signal
for the Threat Intelligence category regardless of target geography.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from app.connectors.base import BaseConnector, ConnectorResult, register_connector


@register_connector("threat_intel_cisa_kev")
class CISAKnownExploitedVulnerabilitiesConnector(BaseConnector):
    """
    config:
        {"since_days": 30, "max_records": 100}  # both optional
    """

    CATALOG_URL = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"

    async def fetch(self) -> ConnectorResult:
        since_days = self.config.get("since_days", 30)
        max_records = self.config.get("max_records", 100)
        cutoff = datetime.now(timezone.utc) - timedelta(days=since_days)

        response = await self.client.get(self.CATALOG_URL)
        response.raise_for_status()
        payload = response.json()

        vulnerabilities: list[dict[str, Any]] = payload.get("vulnerabilities", [])
        records: list[dict[str, Any]] = []

        for vuln in vulnerabilities:
            date_added_str = vuln.get("dateAdded")
            try:
                date_added = datetime.fromisoformat(date_added_str).replace(tzinfo=timezone.utc)
            except (TypeError, ValueError):
                continue
            if date_added < cutoff:
                continue

            ransomware_use = vuln.get("knownRansomwareCampaignUse", "Unknown")
            severity = "critical" if ransomware_use == "Known" else "high"

            records.append(
                {
                    "cve_id": vuln.get("cveID"),
                    "vendor": vuln.get("vendorProject"),
                    "product": vuln.get("product"),
                    "vulnerability_name": vuln.get("vulnerabilityName"),
                    "date_added": vuln.get("dateAdded"),
                    "short_description": vuln.get("shortDescription"),
                    "required_action": vuln.get("requiredAction"),
                    "due_date": vuln.get("dueDate"),
                    "known_ransomware_use": ransomware_use,
                    "severity": severity,
                    "observed_at": vuln.get("dateAdded"),
                }
            )
            if len(records) >= max_records:
                break

        return ConnectorResult(
            records=records,
            raw_count=len(vulnerabilities),
            metadata={"source": "cisa_kev", "catalog_version": payload.get("catalogVersion")},
        )