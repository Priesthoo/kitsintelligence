"""
Financial Intelligence connector combining two free, no-signup APIs:
exchangerate.host for forex rates (Naira and major currency pairs) and
CoinGecko for cryptocurrency prices. A single hydration pass produces
both, since both are lightweight and frequently checked together in
economic-risk dashboards.
"""
from __future__ import annotations

from typing import Any

from app.connectors.base import BaseConnector, ConnectorResult, register_connector


@register_connector("financial_forex_crypto")
class ForexAndCryptoConnector(BaseConnector):
    """
    config:
        {
            "base_currency": "USD",
            "target_currencies": ["NGN", "EUR", "GBP", "CNY"],
            "crypto_ids": ["bitcoin", "ethereum", "tether"]
        }
    credentials:
        {"access_key": "..."}  # optional -- only required if exchangerate.host
                                 enforces the access_key requirement on your plan
    """

    FOREX_URL = "https://api.exchangerate.host/latest"
    CRYPTO_URL = "https://api.coingecko.com/api/v3/simple/price"

    async def fetch(self) -> ConnectorResult:
        base_currency = self.config.get("base_currency", "USD")
        targets = self.config.get("target_currencies", ["NGN", "EUR", "GBP"])
        crypto_ids = self.config.get("crypto_ids", ["bitcoin", "ethereum"])

        records: list[dict[str, Any]] = []
        raw_count = 0

        forex_params = {"base": base_currency, "symbols": ",".join(targets)}
        if "access_key" in self.credentials:
            forex_params["access_key"] = self.credentials["access_key"]

        forex_response = await self.client.get(self.FOREX_URL, params=forex_params)
        forex_response.raise_for_status()
        forex_payload = forex_response.json()
        rates = forex_payload.get("rates", {})
        raw_count += len(rates)

        for currency, rate in rates.items():
            records.append(
                {
                    "type": "forex",
                    "base_currency": base_currency,
                    "quote_currency": currency,
                    "rate": rate,
                    "observed_at": forex_payload.get("date"),
                }
            )

        crypto_response = await self.client.get(
            self.CRYPTO_URL, params={"ids": ",".join(crypto_ids), "vs_currencies": "usd"}
        )
        crypto_response.raise_for_status()
        crypto_payload = crypto_response.json()
        raw_count += len(crypto_payload)

        for coin_id, prices in crypto_payload.items():
            records.append(
                {
                    "type": "crypto",
                    "asset": coin_id,
                    "quote_currency": "usd",
                    "rate": prices.get("usd"),
                    "observed_at": None,
                }
            )

        return ConnectorResult(
            records=records, raw_count=raw_count, metadata={"source": "exchangerate_host+coingecko"}
        )