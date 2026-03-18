from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional
from urllib.parse import urlencode

import httpx


OKX_PAGE_LIMIT = 100
OKX_RECENT_WINDOW_MS = 7 * 24 * 60 * 60 * 1000
MIN_SPLIT_WINDOW_MS = 5 * 60 * 1000
OKX_MIN_REQUEST_INTERVAL_SECONDS = 0.25
OKX_MAX_RETRIES = 5
OKX_BACKOFF_BASE_SECONDS = 1.0
OKX_BACKOFF_MAX_SECONDS = 8.0
OKX_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
OKX_RATE_LIMIT_CODES = {'50011'}


class OkxAdapter:
    BASE = "https://www.okx.com"
    supports_all_symbol_trades = True

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        api_passphrase: str,
        proxy: Optional[str] = None,
        use_demo: bool = False,
    ):
        self.api_key = api_key
        self.api_secret = api_secret
        self.api_passphrase = api_passphrase
        self.proxy = proxy
        self.use_demo = use_demo
        self._min_request_interval_seconds = OKX_MIN_REQUEST_INTERVAL_SECONDS
        self._next_request_at = 0.0

    def _get_client(self, timeout: float = 10.0) -> httpx.AsyncClient:
        if self.proxy:
            return httpx.AsyncClient(timeout=timeout, proxies=self.proxy)
        return httpx.AsyncClient(timeout=timeout)

    def _timestamp(self) -> str:
        return datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')

    def _sign(self, message: str) -> str:
        digest = hmac.new(
            self.api_secret.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256,
        ).digest()
        return base64.b64encode(digest).decode('utf-8')

    def _build_headers(self, method: str, request_path: str, body: str = '') -> Dict[str, str]:
        timestamp = self._timestamp()
        signature = self._sign(f'{timestamp}{method.upper()}{request_path}{body}')
        headers = {
            'OK-ACCESS-KEY': self.api_key,
            'OK-ACCESS-SIGN': signature,
            'OK-ACCESS-TIMESTAMP': timestamp,
            'OK-ACCESS-PASSPHRASE': self.api_passphrase,
            'Content-Type': 'application/json',
        }
        if self.use_demo:
            headers['x-simulated-trading'] = '1'
        return headers

    async def _wait_for_request_slot(self) -> None:
        now = time.monotonic()
        if self._next_request_at > now:
            await asyncio.sleep(self._next_request_at - now)
        self._next_request_at = max(self._next_request_at, time.monotonic()) + self._min_request_interval_seconds

    async def _sleep_before_retry(self, seconds: float) -> None:
        await asyncio.sleep(seconds)

    async def _request_raw_once(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, object]] = None,
        body: str = '',
        timeout: float = 20.0,
    ) -> Dict:
        encoded_params = urlencode(
            [(key, value) for key, value in (params or {}).items() if value not in (None, '')]
        )
        request_path = f'{path}?{encoded_params}' if encoded_params else path
        url = f'{self.BASE}{request_path}'
        headers = self._build_headers(method, request_path, body)

        try:
            async with self._get_client(timeout=timeout) as client:
                if method.upper() == 'GET':
                    response = await client.get(url, headers=headers)
                else:
                    response = await client.request(method.upper(), url, headers=headers, content=body)
        except Exception as exc:
            logging.exception('okx: %s request failed for %s: %s', method.upper(), path, exc)
            error_text = str(exc)
            return {
                'status_code': 0,
                'body': error_text,
                'payload': None,
            }

        try:
            payload = response.json()
        except ValueError:
            payload = None

        return {
            'status_code': response.status_code,
            'body': response.text,
            'payload': payload,
            'headers': dict(response.headers),
        }

    def _should_retry_raw_result(self, raw_result: Dict) -> bool:
        status_code = int(raw_result.get('status_code') or 0)
        error_payload = self._parse_error_payload(raw_result)
        error_code = str(error_payload.get('code') or '')
        return status_code in OKX_RETRYABLE_STATUS_CODES or error_code in OKX_RATE_LIMIT_CODES

    def _retry_delay_seconds(self, raw_result: Dict, attempt: int) -> float:
        headers = raw_result.get('headers') or {}
        retry_after = headers.get('retry-after') or headers.get('Retry-After')
        if retry_after is not None:
            try:
                parsed = float(retry_after)
                if parsed > 0:
                    return parsed
            except (TypeError, ValueError):
                pass

        exponential = OKX_BACKOFF_BASE_SECONDS * (2 ** max(attempt - 1, 0))
        return min(exponential, OKX_BACKOFF_MAX_SECONDS)

    async def _request_raw(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, object]] = None,
        body: str = '',
        timeout: float = 20.0,
    ) -> Dict:
        last_result: Dict = {
            'status_code': 0,
            'body': '',
            'payload': None,
            'headers': {},
        }

        for attempt in range(1, OKX_MAX_RETRIES + 1):
            await self._wait_for_request_slot()
            raw_result = await self._request_raw_once(
                method,
                path,
                params=params,
                body=body,
                timeout=timeout,
            )
            last_result = raw_result

            if not self._should_retry_raw_result(raw_result) or attempt >= OKX_MAX_RETRIES:
                return raw_result

            retry_seconds = self._retry_delay_seconds(raw_result, attempt)
            error_payload = self._parse_error_payload(raw_result)
            logging.warning(
                'okx: %s %s hit retryable response status=%s code=%s attempt=%s/%s retry_in=%.2fs',
                method.upper(),
                path,
                raw_result.get('status_code'),
                error_payload.get('code'),
                attempt,
                OKX_MAX_RETRIES,
                retry_seconds,
            )
            await self._sleep_before_retry(retry_seconds)

        return last_result

    def _response_ok(self, raw_result: Dict) -> bool:
        payload = raw_result.get('payload')
        if raw_result.get('status_code') != 200:
            return False
        if not isinstance(payload, dict):
            return False
        return str(payload.get('code', '')) == '0'

    def _extract_payload_rows(self, raw_result: Dict) -> Optional[List[Dict]]:
        if not self._response_ok(raw_result):
            return None
        payload = raw_result.get('payload') or {}
        rows = payload.get('data')
        return rows if isinstance(rows, list) else []

    def _mask_api_key(self) -> str:
        if not self.api_key:
            return ''
        if len(self.api_key) <= 8:
            return self.api_key
        return f'{self.api_key[:4]}****{self.api_key[-4:]}'

    def _parse_error_payload(self, raw_result: Dict) -> Dict:
        payload = raw_result.get('payload')
        if isinstance(payload, dict):
            return {
                'code': payload.get('code'),
                'message': payload.get('msg') or payload.get('message'),
            }
        try:
            parsed = json.loads(raw_result.get('body') or '')
        except (TypeError, ValueError):
            parsed = None
        if isinstance(parsed, dict):
            return {
                'code': parsed.get('code'),
                'message': parsed.get('msg') or parsed.get('message'),
            }
        return {'code': None, 'message': None}

    def _summarize_connectivity_check(self, scope: str, endpoint: str, raw_result: Dict) -> Dict:
        error_payload = self._parse_error_payload(raw_result)
        status_code = int(raw_result.get('status_code') or 0)

        hint = '接口访问正常。'
        if status_code == 0:
            hint = '请求没有拿到有效响应，优先检查代理配置、容器网络和 DNS。'
        elif not self._response_ok(raw_result):
            if status_code == 401:
                hint = 'OKX 返回 401，优先检查 API Key、Secret、Passphrase 是否匹配。'
            elif status_code == 429 or str(error_payload.get('code') or '') == '50011':
                hint = 'OKX 命中了频率限制，系统会自动退避重试；如果仍失败，需要降低补数频率。'
            elif status_code >= 500:
                hint = 'OKX 服务端暂时不可用，可以稍后重试。'
            else:
                hint = '接口请求失败，请结合返回码与返回消息继续排查。'

        return {
            'scope': scope,
            'endpoint': endpoint,
            'ok': self._response_ok(raw_result),
            'status_code': status_code,
            'code': error_payload.get('code'),
            'message': error_payload.get('message'),
            'hint': hint,
        }

    def _build_overall_hint(self, config_check: Dict, balance_check: Dict) -> str:
        if config_check['ok'] and balance_check['ok']:
            return 'OKX 账户配置与资金账户接口都可用，可以继续接持仓与历史回补。'
        if config_check['ok'] and not balance_check['ok']:
            return 'OKX 账户配置接口正常，但账户资金接口异常，优先检查交易权限和账户模式限制。'
        if not config_check['ok'] and balance_check['ok']:
            return 'OKX 资金接口正常，但账户配置接口异常，优先检查 API 权限范围。'
        return 'OKX 账户接口不可用，请优先检查 API Key、Secret、Passphrase 和 IP 白名单。'

    def _build_account_mode_note(self, config_rows: List[Dict]) -> Optional[str]:
        if not config_rows:
            return None
        config = config_rows[0]
        acct_lv = config.get('acctLv')
        pos_mode = config.get('posMode')
        if acct_lv or pos_mode:
            return f'OKX 账户模式: acctLv={acct_lv or "-"}, posMode={pos_mode or "-"}。'
        return None

    @staticmethod
    def _normalize_symbol(symbol: Optional[str]) -> Optional[str]:
        if not symbol:
            return None
        return symbol.replace('/', '').replace('-', '').strip().upper()

    @classmethod
    def _inst_id_to_symbol(cls, inst_id: Optional[str]) -> Optional[str]:
        if not inst_id:
            return None
        parts = str(inst_id).strip().upper().split('-')
        if len(parts) >= 2:
            return f'{parts[0]}{parts[1]}'
        return str(inst_id).replace('-', '').upper()

    @classmethod
    def _symbol_to_inst_id(cls, symbol: Optional[str]) -> Optional[str]:
        normalized = cls._normalize_symbol(symbol)
        if not normalized:
            return None
        for quote in ('USDT', 'USDC', 'USD'):
            if normalized.endswith(quote) and len(normalized) > len(quote):
                base = normalized[:-len(quote)]
                return f'{base}-{quote}-SWAP'
        return symbol if symbol and '-' in symbol else None

    @staticmethod
    def _normalize_position_side(value: Optional[str]) -> str:
        normalized = (value or 'net').strip().upper()
        if normalized == 'LONG':
            return 'LONG'
        if normalized == 'SHORT':
            return 'SHORT'
        return 'NET'

    async def test_connectivity(self) -> Dict:
        config_raw = await self._request_raw('GET', '/api/v5/account/config')
        balance_raw = await self._request_raw('GET', '/api/v5/account/balance')

        config_rows = self._extract_payload_rows(config_raw) or []
        config_check = self._summarize_connectivity_check('account', '/api/v5/account/config', config_raw)
        balance_check = self._summarize_connectivity_check('balance', '/api/v5/account/balance', balance_raw)

        return {
            'key_masked': self._mask_api_key(),
            'spot_account': config_check,
            'futures_account': balance_check,
            'overall_hint': self._build_overall_hint(config_check, balance_check),
            'account_mode_note': self._build_account_mode_note(config_rows),
        }

    async def fetch_positions_raw(self) -> Dict:
        raw_result = await self._request_raw(
            'GET',
            '/api/v5/account/positions',
            params={'instType': 'SWAP'},
        )
        return {
            'status_code': raw_result.get('status_code'),
            'status': raw_result.get('status_code'),
            'body': raw_result.get('body'),
            'text': raw_result.get('body'),
        }

    async def fetch_positions(self) -> Optional[List[Dict]]:
        raw_result = await self._request_raw(
            'GET',
            '/api/v5/account/positions',
            params={'instType': 'SWAP'},
        )
        rows = self._extract_payload_rows(raw_result)
        if rows is None:
            logging.error('okx: fetch_positions non-success body=%s', raw_result.get('body'))
            return None

        normalized_rows: List[Dict] = []
        for row in rows:
            symbol = self._inst_id_to_symbol(row.get('instId'))
            if not symbol:
                continue

            position_side = self._normalize_position_side(row.get('posSide'))
            raw_pos = float(row.get('pos') or 0.0)
            if position_side == 'LONG':
                position_amt = abs(raw_pos)
            elif position_side == 'SHORT':
                position_amt = -abs(raw_pos)
            else:
                position_amt = raw_pos

            normalized_rows.append({
                'symbol': symbol,
                'positionSide': position_side,
                'positionAmt': str(position_amt),
                'entryPrice': row.get('avgPx') or '0',
                'markPrice': row.get('markPx') or row.get('last') or '0',
                'unRealizedProfit': row.get('upl') or '0',
                'leverage': row.get('lever') or '1',
                'liquidationPrice': row.get('liqPx') or '0',
            })

        return normalized_rows

    async def fetch_account_info(self) -> Optional[Dict]:
        raw_result = await self._request_raw('GET', '/api/v5/account/balance')
        rows = self._extract_payload_rows(raw_result)
        if rows is None:
            logging.error('okx: fetch_account_info non-success body=%s', raw_result.get('body'))
            return None
        if not rows:
            return {
                'totalWalletBalance': 0.0,
                'totalMarginBalance': 0.0,
            }

        row = rows[0]
        total_eq = float(row.get('totalEq') or 0.0)
        adj_eq = float(row.get('adjEq') or row.get('totalEq') or 0.0)
        return {
            'totalWalletBalance': total_eq,
            'totalMarginBalance': adj_eq,
        }

    def _normalize_order_history_rows(self, rows: List[Dict], symbol: Optional[str] = None) -> List[Dict]:
        normalized_symbol = self._normalize_symbol(symbol)
        normalized_rows: List[Dict] = []
        for row in rows:
            mapped_symbol = self._inst_id_to_symbol(row.get('instId'))
            if normalized_symbol and mapped_symbol != normalized_symbol:
                continue

            qty = float(row.get('accFillSz') or row.get('fillSz') or row.get('sz') or 0.0)
            if qty <= 0:
                continue

            avg_price = float(row.get('avgPx') or row.get('fillPx') or row.get('px') or 0.0)
            fee = abs(float(row.get('fee') or 0.0))
            realized_pnl = float(row.get('pnl') or row.get('fillPnl') or 0.0)
            timestamp = int(row.get('fillTime') or row.get('uTime') or row.get('cTime') or 0)
            order_id = str(row.get('ordId') or '')
            trade_id = str(row.get('tradeId') or order_id or timestamp)
            side = str(row.get('side') or '').upper()

            normalized_rows.append({
                'id': trade_id,
                'tradeId': trade_id,
                'orderId': order_id,
                'symbol': mapped_symbol,
                'side': side,
                'positionSide': self._normalize_position_side(row.get('posSide')),
                'price': str(avg_price),
                'qty': str(qty),
                'quoteQty': str(round(avg_price * qty, 12)),
                'commission': str(fee),
                'commissionAsset': row.get('feeCcy'),
                'realizedPnl': str(realized_pnl),
                'time': timestamp,
            })

        return normalized_rows

    def _map_bill_type(self, row: Dict) -> Optional[str]:
        bill_type = str(row.get('type') or '')
        if bill_type == '8':
            return 'FUNDING_FEE'
        if bill_type == '1':
            return 'TRANSFER'
        return None

    def _normalize_bill_rows(self, rows: List[Dict], symbol: Optional[str] = None) -> List[Dict]:
        normalized_symbol = self._normalize_symbol(symbol)
        normalized_rows: List[Dict] = []

        for row in rows:
            mapped_type = self._map_bill_type(row)
            if not mapped_type:
                continue

            mapped_symbol = self._inst_id_to_symbol(row.get('instId'))
            if normalized_symbol and mapped_symbol != normalized_symbol:
                continue

            amount = float(
                row.get('balChg')
                or row.get('pnl')
                or row.get('fee')
                or row.get('sz')
                or 0.0
            )
            timestamp = int(row.get('ts') or 0)
            bill_id = str(row.get('billId') or f'{mapped_type}:{timestamp}')

            normalized_rows.append({
                'tranId': f'OKX_BILL_{bill_id}',
                'symbol': mapped_symbol,
                'incomeType': mapped_type,
                'asset': row.get('ccy'),
                'income': str(amount),
                'time': timestamp,
            })

        return normalized_rows

    async def _fetch_order_history_page(
        self,
        path: str,
        *,
        begin: int,
        end: int,
        symbol: Optional[str],
    ) -> Optional[List[Dict]]:
        params = {
            'instType': 'SWAP',
            'begin': begin,
            'end': end,
            'limit': OKX_PAGE_LIMIT,
        }
        inst_id = self._symbol_to_inst_id(symbol)
        if inst_id:
            params['instId'] = inst_id

        raw_result = await self._request_raw('GET', path, params=params)
        rows = self._extract_payload_rows(raw_result)
        if rows is None:
            logging.error('okx: order history request failed path=%s body=%s', path, raw_result.get('body'))
            return None
        return rows

    async def _fetch_order_history_range(
        self,
        *,
        start_ms: int,
        end_ms: int,
        symbol: Optional[str],
        use_archive: bool,
    ) -> Optional[List[Dict]]:
        if end_ms < start_ms:
            return []

        path = '/api/v5/trade/orders-history-archive' if use_archive else '/api/v5/trade/orders-history'
        rows = await self._fetch_order_history_page(path, begin=start_ms, end=end_ms, symbol=symbol)
        if rows is None:
            return None

        if len(rows) < OKX_PAGE_LIMIT or (end_ms - start_ms) <= MIN_SPLIT_WINDOW_MS:
            return self._normalize_order_history_rows(rows, symbol=symbol)

        middle = (start_ms + end_ms) // 2
        left_rows = await self._fetch_order_history_range(
            start_ms=start_ms,
            end_ms=middle,
            symbol=symbol,
            use_archive=use_archive,
        )
        if left_rows is None:
            return None
        right_rows = await self._fetch_order_history_range(
            start_ms=middle + 1,
            end_ms=end_ms,
            symbol=symbol,
            use_archive=use_archive,
        )
        if right_rows is None:
            return None
        return left_rows + right_rows

    async def fetch_user_trades(
        self,
        symbol: Optional[str] = None,
        limit: int = 100,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
    ) -> Optional[List[Dict]]:
        del limit

        end_ms = int(end_time or time.time() * 1000)
        start_ms = int(start_time or (end_ms - OKX_RECENT_WINDOW_MS))
        recent_cutoff_ms = int(time.time() * 1000) - OKX_RECENT_WINDOW_MS

        if end_ms < recent_cutoff_ms:
            return await self._fetch_order_history_range(
                start_ms=start_ms,
                end_ms=end_ms,
                symbol=symbol,
                use_archive=True,
            )

        if start_ms >= recent_cutoff_ms:
            return await self._fetch_order_history_range(
                start_ms=start_ms,
                end_ms=end_ms,
                symbol=symbol,
                use_archive=False,
            )

        archive_rows = await self._fetch_order_history_range(
            start_ms=start_ms,
            end_ms=recent_cutoff_ms - 1,
            symbol=symbol,
            use_archive=True,
        )
        if archive_rows is None:
            return None
        recent_rows = await self._fetch_order_history_range(
            start_ms=recent_cutoff_ms,
            end_ms=end_ms,
            symbol=symbol,
            use_archive=False,
        )
        if recent_rows is None:
            return None
        return archive_rows + recent_rows

    async def _fetch_recent_bills(self, *, start_ms: int, end_ms: int, symbol: Optional[str]) -> Optional[List[Dict]]:
        after: Optional[str] = None
        normalized_rows: List[Dict] = []

        while True:
            params: Dict[str, object] = {
                'instType': 'SWAP',
                'limit': OKX_PAGE_LIMIT,
            }
            if after:
                params['after'] = after

            raw_result = await self._request_raw('GET', '/api/v5/account/bills', params=params)
            rows = self._extract_payload_rows(raw_result)
            if rows is None:
                logging.error('okx: recent bills request failed body=%s', raw_result.get('body'))
                return None
            if not rows:
                break

            filtered_rows = [
                row for row in rows
                if start_ms <= int(row.get('ts') or 0) <= end_ms
            ]
            normalized_rows.extend(self._normalize_bill_rows(filtered_rows, symbol=symbol))

            oldest_ts = min(int(row.get('ts') or 0) for row in rows)
            after = str(rows[-1].get('billId') or rows[-1].get('ts') or '')
            if oldest_ts < start_ms or len(rows) < OKX_PAGE_LIMIT or not after:
                break

        return normalized_rows

    async def _fetch_archive_bills(self, *, start_ms: int, end_ms: int, symbol: Optional[str]) -> Optional[List[Dict]]:
        raw_result = await self._request_raw(
            'GET',
            '/api/v5/account/bills-archive',
            params={
                'instType': 'SWAP',
                'begin': start_ms,
                'end': end_ms,
                'limit': OKX_PAGE_LIMIT,
            },
        )
        rows = self._extract_payload_rows(raw_result)
        if rows is None:
            logging.error('okx: archive bills request failed body=%s', raw_result.get('body'))
            return None

        if len(rows) < OKX_PAGE_LIMIT or (end_ms - start_ms) <= MIN_SPLIT_WINDOW_MS:
            return self._normalize_bill_rows(rows, symbol=symbol)

        middle = (start_ms + end_ms) // 2
        left_rows = await self._fetch_archive_bills(start_ms=start_ms, end_ms=middle, symbol=symbol)
        if left_rows is None:
            return None
        right_rows = await self._fetch_archive_bills(start_ms=middle + 1, end_ms=end_ms, symbol=symbol)
        if right_rows is None:
            return None
        return left_rows + right_rows

    async def fetch_income_history(
        self,
        limit: int = 100,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        symbol: Optional[str] = None,
        income_type: Optional[str] = None,
    ) -> Optional[List[Dict]]:
        del limit, income_type

        end_ms = int(end_time or time.time() * 1000)
        start_ms = int(start_time or (end_ms - OKX_RECENT_WINDOW_MS))
        recent_cutoff_ms = int(time.time() * 1000) - OKX_RECENT_WINDOW_MS

        if end_ms < recent_cutoff_ms:
            return await self._fetch_archive_bills(start_ms=start_ms, end_ms=end_ms, symbol=symbol)

        if start_ms >= recent_cutoff_ms:
            return await self._fetch_recent_bills(start_ms=start_ms, end_ms=end_ms, symbol=symbol)

        archive_rows = await self._fetch_archive_bills(
            start_ms=start_ms,
            end_ms=recent_cutoff_ms - 1,
            symbol=symbol,
        )
        if archive_rows is None:
            return None
        recent_rows = await self._fetch_recent_bills(
            start_ms=recent_cutoff_ms,
            end_ms=end_ms,
            symbol=symbol,
        )
        if recent_rows is None:
            return None
        return archive_rows + recent_rows