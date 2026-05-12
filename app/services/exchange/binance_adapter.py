"""Binance exchange adapter (futures) — minimal implementation for position sync.

This adapter supports fetching positions using Binance Futures REST API and requires
the account to have API key and secret stored in the Account row.

It is intentionally small and dependency-free (uses httpx and HMAC) so it fits into
the existing service stack.
"""
from __future__ import annotations

import hmac
import hashlib
import json
import time
from typing import Dict, List, Optional
import logging
from urllib.parse import urlencode

import httpx

from app.services.exchange.okx_adapter import OkxAdapter
from app.services.exchange.polymarket_adapter import PolymarketAdapter


class BinanceAdapter:
    BASE = "https://fapi.binance.com"
    SPOT_BASE = "https://api.binance.com"

    def __init__(self, api_key: str, api_secret: str, proxy: Optional[str] = None):
        self.api_key = api_key
        self.api_secret = api_secret
        self.proxy = proxy

    def _get_client(self, timeout: float = 10.0) -> httpx.AsyncClient:
        """Create an httpx client with optional proxy support."""
        if self.proxy:
            return httpx.AsyncClient(timeout=timeout, proxies=self.proxy)
        return httpx.AsyncClient(timeout=timeout)

    def _sign(self, params: str) -> str:
        return hmac.new(self.api_secret.encode('utf-8'), params.encode('utf-8'), hashlib.sha256).hexdigest()

    def _build_signed_query(self, params: List[tuple[str, object]]) -> str:
        normalized_params = []
        for key, value in params:
            if value is None:
                continue

            normalized_value = value.upper() if key == "symbol" and isinstance(value, str) else value
            normalized_params.append((key, str(normalized_value)))

        qs = urlencode(normalized_params)
        return f"{qs}&signature={self._sign(qs)}"

    def _build_signed_url(self, *, base: str, request_path: str, params: List[tuple[str, object]]) -> str:
        return f"{base}{request_path}?{self._build_signed_query(params)}"

    async def _get_server_time(self, base: str, time_path: str) -> int:
        try:
            async with self._get_client(timeout=10.0) as client:
                t_res = await client.get(f"{base}{time_path}")
                if t_res.status_code == 200:
                    payload = t_res.json()
                    server_time = payload.get("serverTime") if isinstance(payload, dict) else None
                    if server_time:
                        return int(server_time)
        except Exception:
            logging.exception("binance: failed to fetch server time from %s%s", base, time_path)

        return int(time.time() * 1000)

    async def _signed_get_raw(
        self,
        *,
        base: str,
        time_path: str,
        request_path: str,
        extra_params: Optional[List[tuple[str, object]]] = None,
        recv_window: int = 15000,
    ) -> Dict:
        ts = await self._get_server_time(base, time_path)
        query_parts: List[tuple[str, object]] = [
            ("timestamp", ts),
            ("recvWindow", recv_window),
        ]
        if extra_params:
            query_parts.extend(extra_params)
        url = self._build_signed_url(base=base, request_path=request_path, params=query_parts)
        headers = {"X-MBX-APIKEY": self.api_key}

        try:
            async with self._get_client(timeout=20.0) as client:
                response = await client.get(url, headers=headers)
                return {
                    "status_code": response.status_code,
                    "body": response.text,
                    "status": response.status_code,
                    "text": response.text,
                }
        except Exception as e:
            logging.exception("binance: signed GET failed for %s: %s", request_path, e)
            error_text = str(e)
            return {
                "status_code": 0,
                "body": error_text,
                "status": 0,
                "text": error_text,
            }

    def _parse_error_payload(self, body: str) -> Dict:
        try:
            payload = json.loads(body)
        except (TypeError, ValueError):
            return {"code": None, "message": None}

        if not isinstance(payload, dict):
            return {"code": None, "message": None}

        code = payload.get("code")
        try:
            code = int(code) if code is not None else None
        except (TypeError, ValueError):
            code = None

        return {
            "code": code,
            "message": payload.get("msg") or payload.get("message"),
        }

    def _mask_api_key(self) -> str:
        if not self.api_key:
            return ""
        if len(self.api_key) <= 8:
            return self.api_key
        return f"{self.api_key[:4]}****{self.api_key[-4:]}"

    def _build_connectivity_hint(self, scope: str, status_code: int, code: Optional[int]) -> str:
        if status_code == 200:
            return "接口访问正常。"

        if status_code == 0:
            return "请求没有拿到有效响应，优先检查代理配置、容器网络和 DNS。"

        if code == -2015:
            if scope == "futures":
                return "Binance 拒绝了这组 key 的合约账户访问。优先检查 API Key 是否开启了 Futures/永续合约权限，以及 IP 白名单是否包含当前服务出口 IP。仅切换统一账户/经典账户通常不会直接返回 -2015。"
            return "Binance 拒绝了这组 key 的现货账户访问。优先检查 API Key 是否仍有效，以及 IP 白名单是否包含当前服务出口 IP。"

        if code == -1021:
            return "请求时间戳与 Binance 服务器偏差过大，优先检查机器时间同步。"

        if status_code == 401:
            return "Binance 返回 401，通常与 API Key、IP 白名单或接口权限配置有关。"

        if status_code >= 500:
            return "Binance 服务端暂时不可用，可以稍后重试。"

        return "接口请求失败，请结合返回码和返回消息继续排查。"

    def _summarize_connectivity_check(self, scope: str, endpoint: str, raw_result: Dict) -> Dict:
        status_code = int(raw_result.get("status_code") or raw_result.get("status") or 0)
        body = raw_result.get("body") or raw_result.get("text") or ""
        error_payload = self._parse_error_payload(body)

        return {
            "scope": scope,
            "endpoint": endpoint,
            "ok": status_code == 200,
            "status_code": status_code,
            "code": error_payload["code"],
            "message": error_payload["message"],
            "hint": self._build_connectivity_hint(scope, status_code, error_payload["code"]),
        }

    def _build_overall_hint(self, spot_check: Dict, futures_check: Dict) -> str:
        if spot_check["ok"] and futures_check["ok"]:
            return "现货与合约账户接口都可用，当前没有权限层面的阻塞。"

        if spot_check["ok"] and not futures_check["ok"]:
            if futures_check.get("code") == -2015:
                return "现货接口正常，但合约接口被 Binance 拒绝。更像是 Futures 权限未开启、合约权限被关闭，或 IP 白名单未覆盖当前服务出口 IP，而不是代码兼容问题。"
            return "现货接口正常，但合约接口异常，优先检查合约权限和 Binance 账户侧限制。"

        if not spot_check["ok"] and futures_check["ok"]:
            return "合约接口正常，但现货接口异常，说明 key 本身可用，问题更偏向现货权限限制。"

        if spot_check.get("code") == -2015 and futures_check.get("code") == -2015:
            return "现货和合约都返回 -2015。这通常说明 API Key 无效、已删除，或 IP 白名单不匹配；比账户模式切换更像凭证或权限问题。"

        return "现货和合约接口都不可用，请优先检查 API Key 是否仍有效、IP 白名单是否正确，以及 Binance 账户是否限制了对应接口权限。"

    async def test_connectivity(self) -> Dict:
        spot_raw = await self._signed_get_raw(
            base=self.SPOT_BASE,
            time_path="/api/v3/time",
            request_path="/api/v3/account",
        )
        futures_raw = await self._signed_get_raw(
            base=self.BASE,
            time_path="/fapi/v1/time",
            request_path="/fapi/v2/account",
        )

        spot_check = self._summarize_connectivity_check("spot", "/api/v3/account", spot_raw)
        futures_check = self._summarize_connectivity_check("futures", "/fapi/v2/account", futures_raw)

        return {
            "key_masked": self._mask_api_key(),
            "spot_account": spot_check,
            "futures_account": futures_check,
            "overall_hint": self._build_overall_hint(spot_check, futures_check),
            "account_mode_note": "如果你最近把 Binance 账户从统一账户切回经典多资金钱包，更常见的连带影响是 API 权限、IP 白名单或 API Key 重新配置；单纯账户模式切换通常不会直接映射成 -2015。",
        }

    async def fetch_positions(self) -> Optional[List[Dict]]:
        """Fetch the user's futures positions via /fapi/v2/positionRisk.

        Returns list of position dicts from Binance, or None on error.
        """
        # Use server time to avoid local clock skew issues
        try:
            async with self._get_client(timeout=10.0) as client:
                t_res = await client.get(f"{self.BASE}/fapi/v1/time")
                if t_res.status_code == 200:
                    server_ts = t_res.json().get("serverTime")
                else:
                    server_ts = int(time.time() * 1000)
        except Exception:
            server_ts = int(time.time() * 1000)

        ts = int(server_ts)
        # include a recvWindow to account for small clock skew if any
        recv_window = 15000
        url = self._build_signed_url(
            base=self.BASE,
            request_path="/fapi/v2/positionRisk",
            params=[
                ("timestamp", ts),
                ("recvWindow", recv_window),
            ],
        )

        headers = {"X-MBX-APIKEY": self.api_key}

        try:
            async with self._get_client(timeout=20.0) as client:
                r = await client.get(url, headers=headers)
                if r.status_code == 200:
                    return r.json()
                logging.error("binance: non-200 status %s body=%s", r.status_code, r.text)
        except Exception as e:
            logging.exception("binance: fetch_positions failed: %s", e)

        return None

    async def fetch_account_info(self) -> Optional[Dict]:
        """Fetch account information including balances via /fapi/v2/account.
        
        Returns dict with account info, or None on error.
        """
        try:
            async with self._get_client(timeout=10.0) as client:
                t_res = await client.get(f"{self.BASE}/fapi/v1/time")
                if t_res.status_code == 200:
                    server_ts = t_res.json().get("serverTime")
                else:
                    server_ts = int(time.time() * 1000)
        except Exception:
            server_ts = int(time.time() * 1000)

        ts = int(server_ts)
        recv_window = 15000
        url = self._build_signed_url(
            base=self.BASE,
            request_path="/fapi/v2/account",
            params=[
                ("timestamp", ts),
                ("recvWindow", recv_window),
            ],
        )

        headers = {"X-MBX-APIKEY": self.api_key}

        try:
            async with self._get_client(timeout=20.0) as client:
                r = await client.get(url, headers=headers)
                if r.status_code == 200:
                    return r.json()
                logging.error("binance: fetch_account_info non-200 status %s body=%s", r.status_code, r.text)
        except Exception as e:
            logging.exception("binance: fetch_account_info failed: %s", e)

        return None

    async def fetch_positions_raw(self) -> Dict:
        """Return raw HTTP result (status and body) for debugging instead of parsing.

        Returns a dict: {status: int, text: str}
        """
        return await self._signed_get_raw(
            base=self.BASE,
            time_path="/fapi/v1/time",
            request_path="/fapi/v2/positionRisk",
        )

    async def fetch_income_history(
        self,
        limit: int = 100,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        symbol: Optional[str] = None,
        income_type: Optional[str] = None,
    ) -> Optional[List[Dict]]:
        """Fetch income history (funding fees, realized pnl, etc) via /fapi/v1/income.
        
        Returns list of income dicts, or None on error.
        """
        try:
            async with self._get_client(timeout=10.0) as client:
                t_res = await client.get(f"{self.BASE}/fapi/v1/time")
                if t_res.status_code == 200:
                    server_ts = t_res.json().get("serverTime")
                else:
                    server_ts = int(time.time() * 1000)
        except Exception:
            server_ts = int(time.time() * 1000)

        ts = int(server_ts)
        recv_window = 15000
        query_parts = [
            ("timestamp", ts),
            ("recvWindow", recv_window),
            ("limit", limit),
        ]
        if start_time is not None:
            query_parts.append(("startTime", int(start_time)))
        if end_time is not None:
            query_parts.append(("endTime", int(end_time)))
        if symbol:
            query_parts.append(("symbol", symbol))
        if income_type:
            query_parts.append(("incomeType", income_type))

        url = self._build_signed_url(
            base=self.BASE,
            request_path="/fapi/v1/income",
            params=query_parts,
        )

        headers = {"X-MBX-APIKEY": self.api_key}

        try:
            async with self._get_client(timeout=20.0) as client:
                r = await client.get(url, headers=headers)
                if r.status_code == 200:
                    return r.json()
                logging.error("binance: fetch_income_history non-200 status %s body=%s", r.status_code, r.text)
        except Exception as e:
            logging.exception("binance: fetch_income_history failed: %s", e)

        return None

    async def fetch_user_trades(
        self,
        symbol: Optional[str] = None,
        limit: int = 100,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
    ) -> Optional[List[Dict]]:
        """Fetch user's trade history via /fapi/v1/userTrades.
        
        Returns list of trade dicts, or None on error.
        """
        try:
            async with self._get_client(timeout=10.0) as client:
                t_res = await client.get(f"{self.BASE}/fapi/v1/time")
                if t_res.status_code == 200:
                    server_ts = t_res.json().get("serverTime")
                else:
                    server_ts = int(time.time() * 1000)
        except Exception:
            server_ts = int(time.time() * 1000)

        ts = int(server_ts)
        recv_window = 15000
        query_parts = [
            ("timestamp", ts),
            ("recvWindow", recv_window),
            ("limit", limit),
        ]
        if symbol:
            query_parts.append(("symbol", symbol))
        if start_time is not None:
            query_parts.append(("startTime", int(start_time)))
        if end_time is not None:
            query_parts.append(("endTime", int(end_time)))

        url = self._build_signed_url(
            base=self.BASE,
            request_path="/fapi/v1/userTrades",
            params=query_parts,
        )

        headers = {"X-MBX-APIKEY": self.api_key}

        try:
            async with self._get_client(timeout=20.0) as client:
                r = await client.get(url, headers=headers)
                if r.status_code == 200:
                    return r.json()
                logging.error("binance: fetch_user_trades non-200 status %s body=%s", r.status_code, r.text)
        except Exception as e:
            logging.exception("binance: fetch_user_trades failed: %s", e)

        return None


def create_adapter_for_account(account):
    if not account.api_key or not account.api_secret:
        return None

    # Check for proxy in settings
    proxy = None
    use_demo = False
    if hasattr(account, 'settings') and account.settings:
        proxy = account.settings.get('proxy')
        use_demo = bool(account.settings.get('okx_demo') or account.settings.get('use_demo'))

    exchange = getattr(account, 'exchange', '').lower()
    if exchange in ('binance', 'binance-futures', 'fapi', 'futures'):
        return BinanceAdapter(account.api_key, account.api_secret, proxy=proxy)
    if exchange in ('okx', 'okex'):
        if not getattr(account, 'api_passphrase', None):
            return None
        return OkxAdapter(
            account.api_key,
            account.api_secret,
            account.api_passphrase,
            proxy=proxy,
            use_demo=use_demo,
        )
    if exchange == 'polymarket':
        return PolymarketAdapter(
            account.api_key,
            account.api_secret,
            api_passphrase=getattr(account, 'api_passphrase', None),
            settings=getattr(account, 'settings', None),
            proxy=proxy,
        )

    return None
