from __future__ import annotations

import hashlib
import hmac
import time
from urllib.parse import urlencode

import requests


class BinanceTestnetExecutor:
    """Authenticated Binance Spot Testnet adapter.

    This class is deliberately testnet-only. It never uses the production
    Binance API endpoint.
    """

    BASE_URL = "https://testnet.binance.vision"

    def __init__(self, api_key: str, api_secret: str, timeout: int = 10):
        if not api_key or not api_secret:
            raise ValueError("Binance Testnet API key and secret are required.")
        self.api_key = api_key.strip()
        self.api_secret = api_secret.strip()
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"X-MBX-APIKEY": self.api_key})

    def _signed_request(self, method: str, path: str, params: dict | None = None):
        params = dict(params or {})
        params["timestamp"] = int(time.time() * 1000)
        params["recvWindow"] = 5000

        # Sign the percent-encoded payload, as required for current signed REST requests.
        query = urlencode(params, doseq=True)
        signature = hmac.new(
            self.api_secret.encode("utf-8"),
            query.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        params["signature"] = signature

        response = self.session.request(
            method,
            self.BASE_URL + path,
            params=params,
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def account(self):
        return self._signed_request("GET", "/api/v3/account")

    def exchange_info(self, symbol: str = "BTCUSDT"):
        response = self.session.get(
            self.BASE_URL + "/api/v3/exchangeInfo",
            params={"symbol": symbol.upper()},
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def market_order(self, symbol: str, side: str, quantity: str):
        side = side.upper()
        if side not in {"BUY", "SELL"}:
            raise ValueError("side must be BUY or SELL")
        return self._signed_request(
            "POST",
            "/api/v3/order",
            {
                "symbol": symbol.upper(),
                "side": side,
                "type": "MARKET",
                "quantity": quantity,
                "newOrderRespType": "FULL",
            },
        )

    def order_status(self, symbol: str, order_id: int):
        return self._signed_request(
            "GET",
            "/api/v3/order",
            {"symbol": symbol.upper(), "orderId": int(order_id)},
        )

    def cancel_order(self, symbol: str, order_id: int):
        return self._signed_request(
            "DELETE",
            "/api/v3/order",
            {"symbol": symbol.upper(), "orderId": int(order_id)},
        )
