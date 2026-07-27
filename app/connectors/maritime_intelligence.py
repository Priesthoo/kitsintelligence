"""
AISHub connector. AISHub is a free, community-run AIS (Automatic
Identification System) data-sharing network; access requires a free
username obtained by contributing a receiving station (or a shared
demo username for evaluation). Returns live vessel positions.
"""
from __future__ import annotations

from typing import Any

from app.connectors.base import BaseConnector, ConnectorResult, register_connector
from app.exceptions.base import ConnectorError


@register_connector("maritime_aishub")
class AISHubConnector(BaseConnector):
    """
    config:
        {"bounding_box": {"lat_min": 4.0, "lat_max": 14.0, "lon_min": 2.5, "lon_max": 14.5}}
        # default bounding box roughly covers Nigerian territorial + EEZ waters
    credentials:
        {"username": "<aishub_username>"}  # required -- https://www.aishub.net
    """

    BASE_URL = "http://data.aishub.net/ws.php"

    async def fetch(self) -> ConnectorResult:
        if "username" not in self.credentials:
            raise ConnectorError("AISHub connector requires a 'username' credential")

        bbox = self.config.get(
            "bounding_box", {"lat_min": 4.0, "lat_max": 14.0, "lon_min": 2.5, "lon_max": 14.5}
        )
        params = {
            "username": self.credentials["username"],
            "format": "1",
            "output": "json",
            "compress": "0",
            "latmin": bbox["lat_min"],
            "latmax": bbox["lat_max"],
            "lonmin": bbox["lon_min"],
            "lonmax": bbox["lon_max"],
        }

        response = await self.client.get(self.BASE_URL, params=params)
        response.raise_for_status()
        payload = response.json()

        # AISHub returns [ {status_block}, [vessel_records...] ]
        if not isinstance(payload, list) or len(payload) < 2:
            return ConnectorResult(records=[], raw_count=0, metadata={"source": "aishub", "note": "empty_or_unexpected_response"})

        status_block, vessels = payload[0], payload[1]
        if isinstance(status_block, list):
            status_block = status_block[0] if status_block else {}

        records: list[dict[str, Any]] = []
        for vessel in vessels:
            lat, lon = vessel.get("LATITUDE"), vessel.get("LONGITUDE")
            if lat is None or lon is None:
                continue
            records.append(
                {
                    "mmsi": vessel.get("MMSI"),
                    "imo": vessel.get("IMO"),
                    "name": vessel.get("NAME"),
                    "latitude": lat,
                    "longitude": lon,
                    "speed_knots": vessel.get("SOG"),
                    "course_degrees": vessel.get("COG"),
                    "navigation_status": vessel.get("NAVSTAT"),
                    "vessel_type": vessel.get("TYPE"),
                    "destination": vessel.get("DEST"),
                    "observed_at": vessel.get("TIME"),
                }
            )

        return ConnectorResult(
            records=records,
            raw_count=len(vessels),
            metadata={"source": "aishub", "status": status_block.get("ERROR", False)},
        )