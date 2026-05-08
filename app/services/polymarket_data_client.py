import os
from typing import Any, Dict, List, Optional

import httpx


class PolymarketAPIError(Exception):
    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


class PolymarketDataClient:
    def __init__(self, timeout: float = 10.0):
        self.timeout = timeout
        self.data_api_base = os.getenv("POLYMARKET_DATA_API_BASE", "https://data-api.polymarket.com").rstrip("/")
        self.gamma_api_base = os.getenv("POLYMARKET_GAMMA_API_BASE", "https://gamma-api.polymarket.com").rstrip("/")
        self.headers = {
            "Accept": "application/json",
            "User-Agent": "trade-helper-polymarket/1.0",
        }

    async def _get_json(
        self,
        *,
        base_url: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        allow_404: bool = False,
    ) -> Any:
        async with httpx.AsyncClient(timeout=self.timeout, headers=self.headers) as client:
            response = await client.get(f"{base_url}{path}", params=params)

        if response.status_code == 404 and allow_404:
            return None

        if response.status_code != 200:
            raise PolymarketAPIError(
                f"Polymarket API 请求失败: {path} HTTP {response.status_code} {response.text}",
                status_code=response.status_code,
            )

        try:
            return response.json()
        except ValueError as exc:
            raise PolymarketAPIError(f"Polymarket API 返回了无效 JSON: {path}") from exc

    async def get_leaderboard(
        self,
        *,
        category: str = "OVERALL",
        time_period: str = "WEEK",
        order_by: str = "PNL",
        limit: int = 10,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        payload = await self._get_json(
            base_url=self.data_api_base,
            path="/v1/leaderboard",
            params={
                "category": category,
                "timePeriod": time_period,
                "orderBy": order_by,
                "limit": limit,
                "offset": offset,
            },
        )
        return payload if isinstance(payload, list) else []

    async def get_public_profile(self, address: str) -> Optional[Dict[str, Any]]:
        payload = await self._get_json(
            base_url=self.gamma_api_base,
            path="/public-profile",
            params={"address": address},
            allow_404=True,
        )
        return payload if isinstance(payload, dict) else None

    async def get_activity(
        self,
        user: str,
        *,
        limit: int = 100,
        offset: int = 0,
        activity_type: Optional[str] = None,
        start: Optional[int] = None,
        end: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {"user": user, "limit": limit, "offset": offset}
        if activity_type:
            params["type"] = activity_type
        if start is not None:
            params["start"] = start
        if end is not None:
            params["end"] = end
        payload = await self._get_json(base_url=self.data_api_base, path="/activity", params=params)
        return payload if isinstance(payload, list) else []

    async def get_trades(
        self,
        user: str,
        *,
        limit: int = 100,
        offset: int = 0,
        taker_only: bool = True,
    ) -> List[Dict[str, Any]]:
        payload = await self._get_json(
            base_url=self.data_api_base,
            path="/trades",
            params={
                "user": user,
                "limit": limit,
                "offset": offset,
                "takerOnly": str(taker_only).lower(),
            },
        )
        return payload if isinstance(payload, list) else []

    async def get_positions(
        self,
        user: str,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        payload = await self._get_json(
            base_url=self.data_api_base,
            path="/positions",
            params={"user": user, "limit": limit, "offset": offset},
        )
        return payload if isinstance(payload, list) else []

    async def get_closed_positions(
        self,
        user: str,
        *,
        limit: int = 50,
        offset: int = 0,
        sort_by: str = "TIMESTAMP",
        sort_direction: str = "DESC",
    ) -> List[Dict[str, Any]]:
        payload = await self._get_json(
            base_url=self.data_api_base,
            path="/closed-positions",
            params={
                "user": user,
                "limit": limit,
                "offset": offset,
                "sortBy": sort_by,
                "sortDirection": sort_direction,
            },
        )
        return payload if isinstance(payload, list) else []
