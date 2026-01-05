"""Binance exchange adapter (futures) — minimal implementation for position sync.

This adapter supports fetching positions using Binance Futures REST API and requires
the account to have API key and secret stored in the Account row.

It is intentionally small and dependency-free (uses httpx and HMAC) so it fits into
the existing service stack.
"""
from __future__ import annotations

import hmac
import hashlib
import time
from typing import Dict, List, Optional
import logging

import httpx


class BinanceAdapter:
    BASE = "https://fapi.binance.com"

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
        qs = f"timestamp={ts}&recvWindow={recv_window}"
        sig = self._sign(qs)
        url = f"{self.BASE}/fapi/v2/positionRisk?{qs}&signature={sig}"

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
        qs = f"timestamp={ts}&recvWindow={recv_window}"
        sig = self._sign(qs)
        url = f"{self.BASE}/fapi/v2/account?{qs}&signature={sig}"

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
        # fetch server time to avoid timestamp errors
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
        qs = f"timestamp={ts}&recvWindow={recv_window}"
        sig = self._sign(qs)
        url = f"{self.BASE}/fapi/v2/positionRisk?{qs}&signature={sig}"

        headers = {"X-MBX-APIKEY": self.api_key}
        try:
            async with self._get_client(timeout=20.0) as client:
                r = await client.get(url, headers=headers)
                return {"status": r.status_code, "text": r.text}
        except Exception as e:
            logging.exception("binance: fetch_positions_raw failed: %s", e)
            return {"status": 0, "text": str(e)}

    async def fetch_income_history(self, limit: int = 100) -> Optional[List[Dict]]:
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
        qs = f"timestamp={ts}&recvWindow={recv_window}&limit={limit}"
        sig = self._sign(qs)
        url = f"{self.BASE}/fapi/v1/income?{qs}&signature={sig}"

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

    async def fetch_user_trades(self, symbol: Optional[str] = None, limit: int = 100) -> Optional[List[Dict]]:
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
        qs = f"timestamp={ts}&recvWindow={recv_window}&limit={limit}"
        if symbol:
            qs += f"&symbol={symbol.upper()}"
        sig = self._sign(qs)
        url = f"{self.BASE}/fapi/v1/userTrades?{qs}&signature={sig}"

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


def create_adapter_for_account(account) -> Optional[BinanceAdapter]:
    if not account.api_key or not account.api_secret:
        return None
    # ensure account.exchange is binance (allow uppercase/lowercase)
    if getattr(account, 'exchange', '').lower() not in ('binance', 'binance-futures', 'fapi', 'futures'):
        return None
    
    # Check for proxy in settings
    proxy = None
    if hasattr(account, 'settings') and account.settings:
        proxy = account.settings.get('proxy')
    
    return BinanceAdapter(account.api_key, account.api_secret, proxy=proxy)
