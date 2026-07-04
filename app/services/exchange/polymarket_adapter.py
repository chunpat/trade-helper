from __future__ import annotations

import logging
import os
import json
import time
from typing import Any, Dict, List, Optional

import httpx

try:
    from py_clob_client_v2.client import ClobClient
    from py_clob_client_v2.clob_types import ApiCreds, AssetType, BalanceAllowanceParams, OrderArgsV2, OrderPayload
    from py_clob_client_v2.endpoints import CANCEL, GET_API_KEYS
    from py_clob_client_v2.signing.hmac import build_hmac_signature
except Exception as exc:  # pragma: no cover - optional dependency in local dev
    ClobClient = None
    ApiCreds = None
    AssetType = None
    BalanceAllowanceParams = None
    OrderArgsV2 = None
    OrderPayload = None
    CANCEL = None
    GET_API_KEYS = None
    build_hmac_signature = None
    _SDK_IMPORT_ERROR = exc
else:  # pragma: no cover - import branch depends on environment
    _SDK_IMPORT_ERROR = None


class PolymarketAdapter:
    DEFAULT_CHAIN_ID = 137
    DEFAULT_SIGNATURE_TYPE = 0
    DEFAULT_RELAYER_HOST = "https://relayer-v2.polymarket.com"
    RELAYER_API_KEYS_ENDPOINT = "/relayer/api/keys"
    POLY_1271_ORDER_BLOCK_REASON = (
        "当前 py-clob-client-v2 / Polymarket deposit wallet(POLY_1271) 真实下单存在已知上游问题："
        "当前公开 create/derive 出来的 CLOB API key 实测仍绑定 owner/signer EOA，"
        "EOA 形态下单会被交易所要求改走 deposit wallet flow，"
        "而切回 deposit wallet 订单形态后又会返回 signer address 与 API key 绑定不匹配。"
        "请先不要启动 live 跟单或手工真实下单，可先通过 relayer wallet batch 转移资金，"
        "或改用当前已稳定支持的非 POLY_1271 账户。"
    )

    def __init__(
        self,
        wallet_address: str,
        private_key: str,
        api_passphrase: Optional[str] = None,
        settings: Optional[Dict[str, Any]] = None,
        proxy: Optional[str] = None,
    ):
        self.wallet_address = (wallet_address or "").strip()
        self.raw_secret = (private_key or "").strip()
        self.private_key = self._normalize_private_key(private_key)
        self.api_passphrase = (api_passphrase or "").strip() or None
        self.settings = settings or {}
        self.proxy = proxy
        self.host = str(
            self.settings.get("polymarket_clob_host")
            or os.getenv("POLYMARKET_CLOB_API_BASE")
            or "https://clob.polymarket.com"
        ).rstrip("/")
        self.relayer_host = str(
            self.settings.get("polymarket_relayer_host")
            or os.getenv("POLYMARKET_RELAYER_API_BASE")
            or self.DEFAULT_RELAYER_HOST
        ).rstrip("/")
        self.chain_id = int(self.settings.get("polymarket_chain_id") or self.DEFAULT_CHAIN_ID)
        self.signature_type = int(self.settings.get("polymarket_signature_type") or self.DEFAULT_SIGNATURE_TYPE)
        self.funder = (
            self.settings.get("polymarket_funder_address")
            or self.wallet_address
        )

    @staticmethod
    def _normalize_private_key(value: Optional[str]) -> str:
        normalized = (value or "").strip()
        if normalized and not normalized.startswith("0x"):
            normalized = f"0x{normalized}"
        return normalized

    def _get_http_client(self, timeout: float = 10.0) -> httpx.AsyncClient:
        if self.proxy:
            return httpx.AsyncClient(timeout=timeout, proxies=self.proxy)
        return httpx.AsyncClient(timeout=timeout)

    def _get_sync_http_client(self, timeout: float = 10.0) -> httpx.Client:
        if self.proxy:
            return httpx.Client(timeout=timeout, proxy=self.proxy)
        return httpx.Client(timeout=timeout)

    @staticmethod
    def _mask_wallet(value: str) -> str:
        if not value:
            return ""
        if len(value) <= 10:
            return value
        return f"{value[:6]}...{value[-4:]}"

    def _wallet_format_ok(self) -> bool:
        return self._wallet_address_ok() and self._signer_key_ok()

    def _wallet_address_ok(self) -> bool:
        wallet = self.wallet_address.lower()
        return wallet.startswith("0x") and len(wallet) == 42

    def _signer_key_ok(self) -> bool:
        private_key = self.private_key.lower()
        return private_key.startswith("0x") and len(private_key) == 66

    def _load_relayer_api_key(self) -> Optional[str]:
        explicit = str(self.settings.get("polymarket_relayer_api_key") or "").strip()
        if explicit:
            return explicit

        legacy_value = self.raw_secret
        if legacy_value and not self._signer_key_ok():
            return legacy_value
        return None

    def _load_relayer_api_key_address(self) -> Optional[str]:
        value = (
            self.settings.get("polymarket_relayer_api_key_address")
            or self.settings.get("polymarket_signer_address")
            or self.settings.get("polymarket_relayer_signer_address")
            or self.settings.get("polymarket_funder_address")
        )
        normalized = str(value or "").strip()
        return normalized or None

    def _relayer_address_ok(self) -> bool:
        address = (self._load_relayer_api_key_address() or "").lower()
        return address.startswith("0x") and len(address) == 42

    def _funder_ok_for_signature_type(self) -> bool:
        if self.signature_type != 3:
            return True
        funder = (self.funder or "").lower()
        return funder.startswith("0x") and len(funder) == 42

    def _mode_note(self) -> str:
        if self.signature_type == 3:
            return "当前按 deposit wallet / POLY_1271 模式初始化；wallet 地址用于 signer / POLY_ADDRESS，funder 地址必须是 deposit wallet 地址，而 relayer API key address 应该是 owner/signer 地址。Relayer auth 与 CLOB auth 是两套独立系统。"
        return "当前按 EOA 模式初始化；如果你的 Polymarket 账户已切到 deposit wallet 流程，需要在账户 settings 中补充 polymarket_signature_type=3 和 polymarket_funder_address。仅有 Relayer/API creds 不能代替新订单签名。"

    def _build_check(
        self,
        *,
        scope: str,
        endpoint: str,
        ok: bool,
        status_code: int,
        message: Optional[str] = None,
        hint: Optional[str] = None,
        code: Optional[int] = None,
    ) -> Dict[str, Any]:
        return {
            "scope": scope,
            "endpoint": endpoint,
            "ok": ok,
            "status_code": status_code,
            "code": code,
            "message": message,
            "hint": hint,
        }

    def _load_api_creds(self) -> Optional[ApiCreds]:
        if ApiCreds is None:
            return None
        api_key = self.settings.get("polymarket_clob_api_key")
        api_secret = self.settings.get("polymarket_clob_api_secret")
        api_passphrase = self.settings.get("polymarket_clob_api_passphrase")
        if api_key and api_secret and api_passphrase:
            return ApiCreds(
                api_key=str(api_key),
                api_secret=str(api_secret),
                api_passphrase=str(api_passphrase),
            )
        return None

    def _build_clob_client(self, *, creds: Optional[ApiCreds] = None) -> ClobClient:
        if ClobClient is None:
            raise RuntimeError(f"py-clob-client-v2 not installed: {_SDK_IMPORT_ERROR}")
        return ClobClient(
            host=self.host,
            chain_id=self.chain_id,
            key=self.private_key if self._signer_key_ok() else None,
            creds=creds,
            signature_type=self.signature_type,
            funder=self.funder,
            use_server_time=True,
            retry_on_error=False,
        )

    def can_place_orders(self) -> tuple[bool, Optional[str]]:
        if not self._wallet_address_ok():
            return False, "当前账户的钱包地址格式不正确，无法作为 Polymarket signer 地址。"
        if not self._signer_key_ok():
            return False, "当前账户仅配置了 Relayer/API 凭据或错误的私钥格式，缺少有效的 EVM signer 私钥，无法创建 Polymarket 订单签名。"
        if self.signature_type == 3:
            return False, self.POLY_1271_ORDER_BLOCK_REASON
        return True, None

    @staticmethod
    def _to_plain_dict(payload: Any) -> Dict[str, Any]:
        if isinstance(payload, dict):
            return payload
        if payload is None:
            return {}
        if hasattr(payload, "model_dump"):
            try:
                return payload.model_dump(mode="json")
            except Exception:
                pass
        if hasattr(payload, "dict"):
            try:
                return payload.dict()
            except Exception:
                pass
        if hasattr(payload, "__dict__"):
            return {
                key: value
                for key, value in payload.__dict__.items()
                if not key.startswith("_")
            }
        return {"value": str(payload)}

    @staticmethod
    def _extract_order_id(payload: Dict[str, Any]) -> Optional[str]:
        candidates = (
            payload.get("orderID"),
            payload.get("orderId"),
            payload.get("id"),
            payload.get("hash"),
            payload.get("order_hash"),
        )
        for item in candidates:
            if item:
                return str(item)
        order_payload = payload.get("order")
        if isinstance(order_payload, dict):
            return PolymarketAdapter._extract_order_id(order_payload)
        return None

    def _build_authed_client(self) -> ClobClient:
        creds = self.create_or_derive_api_creds()
        return self._build_clob_client(creds=creds)

    async def preflight_collateral_balance(self, side: str) -> Dict[str, Any]:
        side_upper = (side or "BUY").upper()
        endpoint = "/balance-allowance?asset_type=COLLATERAL"

        if side_upper != "BUY":
            return self._build_check(
                scope="collateral_balance",
                endpoint=endpoint,
                ok=True,
                status_code=204,
                message="样本信号不是 BUY，跳过 collateral 余额强校验",
                hint="SELL/减仓是否可执行取决于当前 conditional token 持仓，而不是 collateral 余额。",
            )

        if ClobClient is None or BalanceAllowanceParams is None or AssetType is None:
            return self._build_check(
                scope="collateral_balance",
                endpoint=endpoint,
                ok=False,
                status_code=500,
                message="未安装 py-clob-client-v2，无法读取 collateral 余额",
                hint="缺少官方 SDK 时，无法在 live 预检里确认 BUY 所需的 collateral 是否充足。",
            )

        try:
            client = self._build_authed_client()
            payload = client.get_balance_allowance(BalanceAllowanceParams(asset_type=AssetType.COLLATERAL))
        except Exception as exc:
            logging.exception("polymarket: collateral balance preflight failed")
            return self._build_check(
                scope="collateral_balance",
                endpoint=endpoint,
                ok=False,
                status_code=502,
                message=str(exc),
                hint="请检查当前账户是否已完成 CLOB 私有认证，以及环境是否能访问余额接口。",
            )

        balance_value = None
        if isinstance(payload, dict):
            balance_value = payload.get("balance")
        else:
            balance_value = getattr(payload, "balance", None)

        try:
            balance_amount = float(balance_value)
        except (TypeError, ValueError):
            return self._build_check(
                scope="collateral_balance",
                endpoint=endpoint,
                ok=False,
                status_code=502,
                message=f"无法解析 collateral 余额: {balance_value}",
                hint="余额接口已返回响应，但 balance 字段格式异常；请先核对 SDK 返回结构。",
            )

        if balance_amount <= 0:
            return self._build_check(
                scope="collateral_balance",
                endpoint=endpoint,
                ok=False,
                status_code=409,
                message=f"当前 collateral 余额为 {balance_value}",
                hint="认证与盘口检查已通过，但 BUY 类 live 下单仍会因无可用抵押资产失败；请先向 deposit wallet 充值。",
            )

        return self._build_check(
            scope="collateral_balance",
            endpoint=endpoint,
            ok=True,
            status_code=200,
            message=f"当前 collateral 余额为 {balance_value}",
            hint="BUY 样本信号所需的基础抵押资产存在，可继续评估价格、滑点与仓位限制。",
        )

    def _build_relayer_headers(self) -> Dict[str, str]:
        api_key = self._load_relayer_api_key()
        api_key_address = self._load_relayer_api_key_address()
        if not api_key:
            raise RuntimeError("缺少 polymarket_relayer_api_key，无法访问 relayer API")
        if not api_key_address:
            raise RuntimeError("缺少 polymarket_relayer_api_key_address，无法访问 relayer API")
        return {
            "RELAYER_API_KEY": api_key,
            "RELAYER_API_KEY_ADDRESS": api_key_address,
        }

    async def _relayer_request_async(self, endpoint: str) -> Any:
        headers = self._build_relayer_headers()
        url = f"{self.relayer_host}{endpoint}"
        async with self._get_http_client() as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            if not response.text:
                return {}
            return response.json()

    def _build_l2_headers(
        self,
        *,
        method: str,
        endpoint: str,
        body: Any = None,
        serialized_body: Optional[str] = None,
    ) -> Dict[str, str]:
        if build_hmac_signature is None:
            raise RuntimeError(f"py-clob-client-v2 not installed: {_SDK_IMPORT_ERROR}")
        if not self._wallet_address_ok():
            raise RuntimeError("钱包地址格式不正确，无法构造 POLY_ADDRESS 请求头")
        creds = self._load_api_creds()
        if creds is None:
            raise RuntimeError("缺少 polymarket_clob_api_key / polymarket_clob_api_secret / polymarket_clob_api_passphrase")

        ts = int(time.time())
        body_for_sig = serialized_body if serialized_body is not None else body
        return {
            "POLY_ADDRESS": self.wallet_address,
            "POLY_SIGNATURE": build_hmac_signature(creds.api_secret, str(ts), method, endpoint, body_for_sig),
            "POLY_TIMESTAMP": str(ts),
            "POLY_API_KEY": creds.api_key,
            "POLY_PASSPHRASE": creds.api_passphrase,
        }

    async def _l2_request_async(
        self,
        *,
        method: str,
        endpoint: str,
        body: Any = None,
        serialized_body: Optional[str] = None,
    ) -> Dict[str, Any]:
        headers = self._build_l2_headers(method=method, endpoint=endpoint, body=body, serialized_body=serialized_body)
        url = f"{self.host}{endpoint}"
        async with self._get_http_client() as client:
            response = await client.request(method=method, url=url, headers=headers, content=serialized_body)
            response.raise_for_status()
            if not response.text:
                return {}
            return response.json()

    def _l2_request_sync(
        self,
        *,
        method: str,
        endpoint: str,
        body: Any = None,
        serialized_body: Optional[str] = None,
    ) -> Dict[str, Any]:
        headers = self._build_l2_headers(method=method, endpoint=endpoint, body=body, serialized_body=serialized_body)
        url = f"{self.host}{endpoint}"
        with self._get_sync_http_client() as client:
            response = client.request(method=method, url=url, headers=headers, content=serialized_body)
            response.raise_for_status()
            if not response.text:
                return {}
            return response.json()

    def create_or_derive_api_creds(self) -> ApiCreds:
        cached = self._load_api_creds()
        if cached is not None:
            return cached
        if not self._signer_key_ok():
            raise RuntimeError("当前账户未配置有效的 EVM signer 私钥，且没有提供现成的 polymarket_clob_api_key / secret / passphrase")
        client = self._build_clob_client()
        return client.create_or_derive_api_key()

    def place_order(self, *, token_id: str, side: str, price: float, size: float, order_type: str = "GTC") -> Dict[str, Any]:
        if not token_id:
            raise ValueError("缺少 token_id，无法提交 Polymarket 订单")
        if price <= 0:
            raise ValueError("下单价格必须大于 0")
        if size <= 0:
            raise ValueError("下单数量必须大于 0")
        if OrderArgsV2 is None:
            raise RuntimeError(f"py-clob-client-v2 not installed: {_SDK_IMPORT_ERROR}")
        can_place, reason = self.can_place_orders()
        if not can_place:
            raise RuntimeError(reason or "当前账户不满足 Polymarket 下单条件")

        client = self._build_authed_client()
        response = client.create_and_post_order(
            OrderArgsV2(
                token_id=str(token_id),
                price=float(price),
                size=float(size),
                side=str(side).upper(),
            ),
            order_type=str(order_type).upper(),
            post_only=False,
            defer_exec=False,
        )
        payload = self._to_plain_dict(response)
        return {
            "ok": True,
            "order_id": self._extract_order_id(payload),
            "status": str(payload.get("status") or payload.get("state") or "submitted"),
            "response": payload,
        }

    def cancel_order(self, order_id: str) -> Dict[str, Any]:
        if not order_id:
            raise ValueError("缺少 order_id，无法撤销 Polymarket 订单")
        if OrderPayload is None or CANCEL is None:
            raise RuntimeError(f"py-clob-client-v2 not installed: {_SDK_IMPORT_ERROR}")

        if not self._signer_key_ok() and self._load_api_creds() is not None:
            body = {"orderID": str(order_id)}
            serialized = json.dumps(body, separators=(",", ":"), ensure_ascii=False)
            payload = self._l2_request_sync(method="DELETE", endpoint=CANCEL, body=body, serialized_body=serialized)
            return {
                "ok": True,
                "order_id": str(order_id),
                "status": str(payload.get("status") or payload.get("state") or "canceled"),
                "response": payload,
            }

        client = self._build_authed_client()
        response = client.cancel_order(OrderPayload(orderID=str(order_id)))
        payload = self._to_plain_dict(response)
        return {
            "ok": True,
            "order_id": str(order_id),
            "status": str(payload.get("status") or payload.get("state") or "canceled"),
            "response": payload,
        }

    async def test_connectivity(self) -> Dict[str, Any]:
        checks: List[Dict[str, Any]] = []

        wallet_ok = self._wallet_address_ok()
        signer_ok = self._signer_key_ok()
        cached_creds = self._load_api_creds()
        checks.append(
            self._build_check(
                scope="wallet",
                endpoint="local",
                ok=wallet_ok,
                status_code=200 if wallet_ok else 400,
                message=None if wallet_ok else "钱包地址格式不正确",
                hint="钱包地址应为 0x 开头 42 位。",
            )
        )
        if not wallet_ok:
            return {
                "key_masked": self._mask_wallet(self.wallet_address),
                "overall_hint": "钱包地址格式校验未通过，无法继续做 Polymarket 私有认证。",
                "account_mode_note": self._mode_note(),
                "checks": checks,
                "spot_account": None,
                "futures_account": None,
            }

        checks.append(
            self._build_check(
                scope="signer",
                endpoint="local",
                ok=signer_ok,
                status_code=200 if signer_ok else 400,
                message=None if signer_ok else "未检测到有效的 EVM signer 私钥",
                hint="真实下单创建订单签名时需要 0x 开头 66 位的 EVM 私钥。只有 Relayer/API creds 不足以下新单。",
            )
        )

        if self.signature_type == 3:
            funder_ok = self._funder_ok_for_signature_type()
            checks.append(
                self._build_check(
                    scope="funder",
                    endpoint="local",
                    ok=funder_ok,
                    status_code=200 if funder_ok else 400,
                    message=None if funder_ok else "POLY_1271 模式下 funder 地址不是 deposit wallet 地址",
                    hint="deposit wallet 模式里，wallet 地址应保存 owner/signer 地址，funder 地址应单独保存 deposit wallet 地址。",
                )
            )
            if signer_ok and funder_ok:
                checks.append(
                    self._build_check(
                        scope="order_submission",
                        endpoint="/order",
                        ok=False,
                        status_code=409,
                        message="当前账户认证已通过，但真实下单仍会被上游拒绝",
                        hint=self.POLY_1271_ORDER_BLOCK_REASON,
                    )
                )

        relayer_api_key = self._load_relayer_api_key()
        relayer_api_key_address = self._load_relayer_api_key_address()
        if relayer_api_key and relayer_api_key_address:
            try:
                await self._relayer_request_async(self.RELAYER_API_KEYS_ENDPOINT)
                checks.append(
                    self._build_check(
                        scope="relayer",
                        endpoint=self.RELAYER_API_KEYS_ENDPOINT,
                        ok=True,
                        status_code=200,
                        message="Relayer API key 可用于访问 relayer-v2 接口",
                        hint="说明当前账户可以继续做 deposit wallet 部署、wallet batch、nonce 查询等 relayer 操作。",
                    )
                )
            except Exception as exc:
                logging.exception("polymarket: relayer auth check failed")
                checks.append(
                    self._build_check(
                        scope="relayer",
                        endpoint=self.RELAYER_API_KEYS_ENDPOINT,
                        ok=False,
                        status_code=502,
                        message=str(exc),
                        hint="请检查 relayer API key 是否与 relayer API key address 匹配，并确认当前请求走的是 relayer-v2.polymarket.com。",
                    )
                )
        elif relayer_api_key or relayer_api_key_address:
            checks.append(
                self._build_check(
                    scope="relayer",
                    endpoint=self.RELAYER_API_KEYS_ENDPOINT,
                    ok=False,
                    status_code=400,
                    message="Relayer 配置不完整",
                    hint="需要同时提供 polymarket_relayer_api_key 与 polymarket_relayer_api_key_address。",
                )
            )
        else:
            checks.append(
                self._build_check(
                    scope="relayer",
                    endpoint=self.RELAYER_API_KEYS_ENDPOINT,
                    ok=True,
                    status_code=204,
                    message="未配置 relayer API key，跳过 relayer 检查",
                    hint="Relayer auth 主要用于 deposit wallet 部署和 wallet batch；与 CLOB 下单认证分开。",
                )
            )

        if ClobClient is None:
            checks.append(
                self._build_check(
                    scope="sdk",
                    endpoint="py-clob-client-v2",
                    ok=False,
                    status_code=500,
                    message="未安装 py-clob-client-v2",
                    hint="请先安装 requirements.txt 中的 py-clob-client-v2 依赖，再执行 Polymarket 私有认证检测。",
                )
            )
            return {
                "key_masked": self._mask_wallet(self.wallet_address),
                "overall_hint": "Polymarket 官方 Python SDK 不可用，当前只能完成本地格式检查。",
                "account_mode_note": self._mode_note(),
                "checks": checks,
                "spot_account": None,
                "futures_account": None,
            }

        creds = None
        if cached_creds is not None:
            checks.append(
                self._build_check(
                    scope="clob_l1",
                    endpoint="/auth/api-key | /auth/derive-api-key",
                    ok=True,
                    status_code=204,
                    message="已提供现成的 CLOB API 凭据，跳过 L1 派生",
                    hint="当前优先验证 Relayer/API 凭据的 L2 私有接口可达性。",
                )
            )
            creds = cached_creds
        else:
            try:
                creds = self.create_or_derive_api_creds()
                checks.append(
                    self._build_check(
                        scope="clob_l1",
                        endpoint="/auth/api-key | /auth/derive-api-key",
                        ok=True,
                        status_code=200,
                        message="L1 私钥签名与 API 凭据派生成功",
                        hint="说明当前钱包私钥可用于 CLOB L1 认证。",
                    )
                )
            except Exception as exc:
                logging.exception("polymarket: failed to derive api creds")
                checks.append(
                    self._build_check(
                        scope="clob_l1",
                        endpoint="/auth/api-key | /auth/derive-api-key",
                        ok=False,
                        status_code=502,
                        message=str(exc),
                        hint="请检查私钥是否与钱包地址匹配，以及当前环境是否能访问 clob.polymarket.com。",
                    )
                )
                return {
                    "key_masked": self._mask_wallet(self.wallet_address),
                    "overall_hint": "Polymarket L1 认证未通过，当前还不能继续进行私有交易预检。",
                    "account_mode_note": self._mode_note(),
                    "checks": checks,
                    "spot_account": None,
                    "futures_account": None,
                }

        try:
            if cached_creds is not None and not signer_ok:
                self._l2_request_async  # keep method referenced for tests / static tools
                await self._l2_request_async(method="GET", endpoint=GET_API_KEYS)
            else:
                authed_client = self._build_clob_client(creds=creds)
                authed_client.get_api_keys()
            checks.append(
                self._build_check(
                    scope="clob_l2",
                    endpoint="/auth/api-keys",
                    ok=True,
                    status_code=200,
                    message="L2 API 凭据可用于访问 CLOB 私有接口",
                    hint=(
                        "说明当前账户已经具备后续做私有接口请求的认证条件；如果缺少 signer 私钥，仍然不能创建新订单。"
                        if not signer_ok else
                        "说明当前账户已经具备后续做 balance/allowance、下单与撤单请求的认证条件。"
                    ),
                )
            )
        except Exception as exc:
            logging.exception("polymarket: l2 auth check failed")
            checks.append(
                self._build_check(
                    scope="clob_l2",
                    endpoint="/auth/api-keys",
                    ok=False,
                    status_code=502,
                    message=str(exc),
                    hint="L1 能通过但 L2 失败时，优先检查 CLOB API 凭据是否可派生、账户是否受地理限制、或 funder/signature_type 设置是否匹配。",
                )
            )

        overall_ok = all(check["ok"] for check in checks if check["status_code"] != 204)
        return {
            "key_masked": self._mask_wallet(self.wallet_address),
            "overall_hint": (
                self.POLY_1271_ORDER_BLOCK_REASON
                if any(check["scope"] == "order_submission" and not check["ok"] for check in checks) else
                "Polymarket 私有认证链路可用，当前可以继续做 live 下单前检查。"
                if overall_ok else
                "Relayer API key 可用，但当前 deposit wallet 配置仍有错误；请先修正 funder 地址和 signer/CLOB 凭据。"
                if any(check["scope"] == "relayer" and check["ok"] for check in checks) and any(check["scope"] == "funder" and not check["ok"] for check in checks) else
                "Polymarket API 凭据可用于私有接口认证，但缺少有效 signer 私钥时仍不能真实下单。"
                if cached_creds is not None and not signer_ok and any(check["scope"] == "clob_l2" and check["ok"] for check in checks) else
                "Polymarket 账户存在至少一个私有认证检查未通过，暂不建议进入 live。"
            ),
            "account_mode_note": self._mode_note(),
            "checks": checks,
            "spot_account": None,
            "futures_account": None,
        }

    async def preflight_orderbook(self, token_id: str, side: str) -> Dict[str, Any]:
        if not token_id:
            return self._build_check(
                scope="orderbook",
                endpoint="/book",
                ok=False,
                status_code=400,
                message="缺少 token_id，无法检查 orderbook",
                hint="只有拿到可执行信号里的 asset/token_id 后，才能继续做盘口预检。",
            )

        if ClobClient is None:
            return self._build_check(
                scope="orderbook",
                endpoint="/book",
                ok=False,
                status_code=500,
                message="未安装 py-clob-client-v2",
                hint="缺少官方 SDK，当前无法通过客户端读取 CLOB orderbook。",
            )

        try:
            client = self._build_clob_client()
            book = client.get_order_book(token_id)
        except Exception as exc:
            logging.exception("polymarket: failed to fetch order book for token %s", token_id)
            return self._build_check(
                scope="orderbook",
                endpoint=f"/book?token_id={token_id}",
                ok=False,
                status_code=502,
                message=str(exc),
                hint="请检查 token_id 是否有效、目标市场是否仍在交易，以及当前环境能否访问 CLOB 公共盘口接口。",
            )

        book_dict = book if isinstance(book, dict) else getattr(book, "__dict__", {})
        side_upper = (side or "BUY").upper()
        levels = book_dict.get("asks") if side_upper == "BUY" else book_dict.get("bids")
        has_liquidity = bool(levels)
        best_level = None
        if isinstance(levels, list) and levels:
            first_level = levels[0]
            if isinstance(first_level, dict):
                best_level = first_level.get("price") or first_level.get("value")
            elif isinstance(first_level, (list, tuple)) and first_level:
                best_level = first_level[0]
            else:
                best_level = first_level

        hint = "盘口存在对手方深度，可继续评估下单价格与滑点。" if has_liquidity else "盘口接口可访问，但当前没有足够的对手方深度；live 下单前应继续检查市场是否暂停、是否临近结算，或是否已经无流动性。"
        message = f"{side_upper} 方向最优档价格: {best_level}" if best_level is not None else "未拿到有效最优档价格"
        return self._build_check(
            scope="orderbook",
            endpoint=f"/book?token_id={token_id}",
            ok=has_liquidity,
            status_code=200,
            message=message,
            hint=hint,
        )

    async def fetch_positions(self) -> Optional[List[Dict[str, Any]]]:
        return None

    async def fetch_account_info(self) -> Optional[Dict[str, Any]]:
        return None

    async def fetch_income_history(self, *args, **kwargs) -> List[Dict[str, Any]]:
        return []

    async def fetch_user_trades(self, *args, **kwargs) -> List[Dict[str, Any]]:
        return []
