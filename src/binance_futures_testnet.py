from __future__ import annotations

import hashlib
import hmac
import time
from decimal import Decimal, ROUND_DOWN
from urllib.parse import urlencode

import requests


class BinanceFuturesTestnetExecutor:
    """Binance USDⓈ-M Futures Testnet REST adapter.

    Testnet only. Default REST endpoint is Binance's current Futures Testnet
    endpoint. No production endpoint is used by this class.
    """

    BASE_URL = "https://demo-fapi.binance.com"

    def __init__(self, api_key: str, api_secret: str, timeout: int = 10):
        if not api_key or not api_secret:
            raise ValueError("Binance Futures Testnet API key and secret are required.")
        self.api_key = api_key.strip()
        self.api_secret = api_secret.strip()
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"X-MBX-APIKEY": self.api_key})

    def _request(self, method: str, path: str, params: dict | None = None, signed: bool = False):
        params = dict(params or {})
        if signed:
            params["timestamp"] = int(time.time() * 1000)
            params["recvWindow"] = 5000
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
        try:
            data = response.json()
        except ValueError:
            response.raise_for_status()
            raise RuntimeError(f"Binance returned non-JSON HTTP {response.status_code}")
        if not response.ok:
            code = data.get("code") if isinstance(data, dict) else None
            msg = data.get("msg") if isinstance(data, dict) else str(data)
            raise RuntimeError(f"Binance API error {code}: {msg}")
        return data

    def ping(self):
        return self._request("GET", "/fapi/v1/ping")

    def server_time(self):
        return self._request("GET", "/fapi/v1/time")

    def exchange_info(self, symbol: str = "BTCUSDT"):
        return self._request("GET", "/fapi/v1/exchangeInfo", {"symbol": symbol.upper()})

    def account(self):
        return self._request("GET", "/fapi/v3/account", signed=True)

    def balance(self):
        return self._request("GET", "/fapi/v3/balance", signed=True)

    def position_risk(self, symbol: str = "BTCUSDT"):
        return self._request("GET", "/fapi/v3/positionRisk", {"symbol": symbol.upper()}, signed=True)

    def user_trades(self, symbol: str = "BTCUSDT", limit: int = 20):
        return self._request("GET", "/fapi/v1/userTrades", {"symbol": symbol.upper(), "limit": int(limit)}, signed=True)

    def open_orders(self, symbol: str = "BTCUSDT"):
        return self._request("GET", "/fapi/v1/openOrders", {"symbol": symbol.upper()}, signed=True)

    def open_algo_orders(self, symbol: str = "BTCUSDT"):
        return self._request("GET", "/fapi/v1/openAlgoOrders", {"symbol": symbol.upper()}, signed=True)

    def order_status(self, symbol: str, order_id: int):
        return self._request(
            "GET", "/fapi/v1/order",
            {"symbol": symbol.upper(), "orderId": int(order_id)}, signed=True
        )

    def algo_order_status(self, algo_id: int | None = None, client_algo_id: str | None = None):
        params = {}
        if algo_id is not None:
            params["algoId"] = int(algo_id)
        elif client_algo_id:
            params["clientAlgoId"] = client_algo_id
        else:
            raise ValueError("algo_id or client_algo_id is required")
        return self._request("GET", "/fapi/v1/algoOrder", params, signed=True)

    def set_leverage(self, symbol: str, leverage: int):
        leverage = int(leverage)
        if not 1 <= leverage <= 125:
            raise ValueError("leverage must be between 1 and 125")
        return self._request("POST", "/fapi/v1/leverage", {
            "symbol": symbol.upper(), "leverage": leverage
        }, signed=True)

    def set_position_mode_one_way(self):
        return self._request("POST", "/fapi/v1/positionSide/dual", {
            "dualSidePosition": "false"
        }, signed=True)

    def market_order(self, symbol: str, side: str, quantity: str, client_order_id: str | None = None,
                     reduce_only: bool = False):
        side = side.upper()
        if side not in {"BUY", "SELL"}:
            raise ValueError("side must be BUY or SELL")
        params = {
            "symbol": symbol.upper(),
            "side": side,
            "type": "MARKET",
            "quantity": quantity,
            "newOrderRespType": "RESULT",
        }
        if client_order_id:
            params["newClientOrderId"] = client_order_id
        if reduce_only:
            params["reduceOnly"] = "true"
        return self._request("POST", "/fapi/v1/order", params, signed=True)

    def test_market_order(self, symbol: str, side: str, quantity: str):
        side = side.upper()
        if side not in {"BUY", "SELL"}:
            raise ValueError("side must be BUY or SELL")
        return self._request("POST", "/fapi/v1/order/test", {
            "symbol": symbol.upper(), "side": side, "type": "MARKET", "quantity": quantity
        }, signed=True)

    def cancel_order(self, symbol: str, order_id: int):
        return self._request("DELETE", "/fapi/v1/order", {
            "symbol": symbol.upper(), "orderId": int(order_id)
        }, signed=True)

    def cancel_all_orders(self, symbol: str):
        return self._request("DELETE", "/fapi/v1/allOpenOrders", {
            "symbol": symbol.upper()
        }, signed=True)

    def cancel_all_algo_orders(self, symbol: str):
        return self._request("DELETE", "/fapi/v1/algoOpenOrders", {
            "symbol": symbol.upper()
        }, signed=True)

    def close_position_market(self, symbol: str, quantity: str, current_position_amt: float):
        if current_position_amt == 0:
            return None
        side = "SELL" if current_position_amt > 0 else "BUY"
        return self.market_order(symbol, side, quantity, reduce_only=True)

    def algo_close_order(self, symbol: str, side: str, order_type: str,
                        trigger_price: str, client_algo_id: str | None = None):
        side = side.upper()
        order_type = order_type.upper()
        if side not in {"BUY", "SELL"}:
            raise ValueError("side must be BUY or SELL")
        if order_type not in {"STOP_MARKET", "TAKE_PROFIT_MARKET"}:
            raise ValueError("order_type must be STOP_MARKET or TAKE_PROFIT_MARKET")
        params = {
            "algoType": "CONDITIONAL",
            "symbol": symbol.upper(),
            "side": side,
            "type": order_type,
            "triggerPrice": trigger_price,
            "closePosition": "true",
            "workingType": "CONTRACT_PRICE",
        }
        if client_algo_id:
            params["clientAlgoId"] = client_algo_id
        return self._request("POST", "/fapi/v1/algoOrder", params, signed=True)


def floor_to_step(value: float | str, step: float | str) -> Decimal:
    value_d = Decimal(str(value))
    step_d = Decimal(str(step))
    if step_d <= 0:
        return value_d
    units = (value_d / step_d).to_integral_value(rounding=ROUND_DOWN)
    return units * step_d
