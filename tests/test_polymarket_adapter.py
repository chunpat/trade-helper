import asyncio
import base64

from app.services.exchange.polymarket_adapter import PolymarketAdapter


def _api_creds_settings():
    return {
        "polymarket_signature_type": 3,
        "polymarket_funder_address": "0x1234567890abcdef1234567890abcdef12345678",
        "polymarket_clob_api_key": "relayer-key",
        "polymarket_clob_api_secret": base64.urlsafe_b64encode(b"secret-for-tests").decode(),
        "polymarket_clob_api_passphrase": "relayer-passphrase",
        "polymarket_relayer_api_key": "019e122f-5aa5-775f-ac4b-f96c304bfbee",
        "polymarket_relayer_api_key_address": "0xe107d231debec406298f5e6fb2e5c4bd4fc3ff7f",
    }


def test_polymarket_adapter_connectivity_supports_cached_api_creds_without_signer(monkeypatch):
    adapter = PolymarketAdapter(
        wallet_address="0x1234567890abcdef1234567890abcdef12345678",
        private_key="not-a-real-evm-key",
        settings=_api_creds_settings(),
    )

    async def fake_l2_request_async(*, method, endpoint, body=None, serialized_body=None):
        assert method == "GET"
        assert endpoint == "/auth/api-keys"
        return {"apiKeys": [{"apiKey": "relayer-key"}]}

    async def fake_relayer_request_async(endpoint):
        assert endpoint == "/relayer/api/keys"
        return [{"apiKey": "019e122f-5aa5-775f-ac4b-f96c304bfbee"}]

    monkeypatch.setattr(adapter, "_l2_request_async", fake_l2_request_async)
    monkeypatch.setattr(adapter, "_relayer_request_async", fake_relayer_request_async)

    result = asyncio.run(adapter.test_connectivity())

    assert result["key_masked"] == "0x1234...5678"
    assert any(check["scope"] == "relayer" and check["ok"] for check in result["checks"])
    assert any(check["scope"] == "clob_l2" and check["ok"] for check in result["checks"])
    assert any(check["scope"] == "signer" and check["ok"] is False for check in result["checks"])
    assert "不能真实下单" in result["overall_hint"]


def test_polymarket_adapter_uses_legacy_raw_secret_as_relayer_key(monkeypatch):
    adapter = PolymarketAdapter(
        wallet_address="0x1234567890abcdef1234567890abcdef12345678",
        private_key="019e122f-5aa5-775f-ac4b-f96c304bfbee",
        settings={
            "polymarket_signature_type": 3,
            "polymarket_funder_address": "0x1234567890abcdef1234567890abcdef12345678",
            "polymarket_relayer_api_key_address": "0xe107d231debec406298f5e6fb2e5c4bd4fc3ff7f",
            "polymarket_clob_api_key": "clob-key",
            "polymarket_clob_api_secret": base64.urlsafe_b64encode(b"secret-for-tests").decode(),
            "polymarket_clob_api_passphrase": "passphrase",
        },
    )

    async def fake_relayer_request_async(endpoint):
        assert endpoint == "/relayer/api/keys"
        return [{"apiKey": "019e122f-5aa5-775f-ac4b-f96c304bfbee"}]

    async def fake_l2_request_async(*, method, endpoint, body=None, serialized_body=None):
        return {"apiKeys": [{"apiKey": "clob-key"}]}

    monkeypatch.setattr(adapter, "_relayer_request_async", fake_relayer_request_async)
    monkeypatch.setattr(adapter, "_l2_request_async", fake_l2_request_async)

    result = asyncio.run(adapter.test_connectivity())

    assert any(check["scope"] == "relayer" and check["ok"] for check in result["checks"])


def test_polymarket_adapter_flags_poly1271_funder_mismatch(monkeypatch):
    adapter = PolymarketAdapter(
        wallet_address="0x1234567890abcdef1234567890abcdef12345678",
        private_key="019e122f-5aa5-775f-ac4b-f96c304bfbee",
        settings={
            "polymarket_signature_type": 3,
            "polymarket_funder_address": "not-a-wallet",
            "polymarket_relayer_api_key": "019e122f-5aa5-775f-ac4b-f96c304bfbee",
            "polymarket_relayer_api_key_address": "0xe107d231debec406298f5e6fb2e5c4bd4fc3ff7f",
            "polymarket_clob_api_key": "clob-key",
            "polymarket_clob_api_secret": base64.urlsafe_b64encode(b"secret-for-tests").decode(),
            "polymarket_clob_api_passphrase": "passphrase",
        },
    )

    async def fake_relayer_request_async(endpoint):
        return [{"apiKey": "019e122f-5aa5-775f-ac4b-f96c304bfbee"}]

    async def fake_l2_request_async(*, method, endpoint, body=None, serialized_body=None):
        return {"apiKeys": [{"apiKey": "clob-key"}]}

    monkeypatch.setattr(adapter, "_relayer_request_async", fake_relayer_request_async)
    monkeypatch.setattr(adapter, "_l2_request_async", fake_l2_request_async)

    result = asyncio.run(adapter.test_connectivity())

    assert any(check["scope"] == "funder" and check["ok"] is False for check in result["checks"])
    assert "funder 地址" in result["overall_hint"]


def test_polymarket_adapter_allows_distinct_poly1271_signer_and_funder(monkeypatch):
    adapter = PolymarketAdapter(
        wallet_address="0xcaf3f08a9d477b2869450d45094a2f02fa898084",
        private_key="0x" + "1" * 64,
        settings={
            "polymarket_signature_type": 3,
            "polymarket_funder_address": "0x6446e5039008f19dc1f10ca60d0830fa459e2329",
            "polymarket_relayer_api_key": "019e122f-5aa5-775f-ac4b-f96c304bfbee",
            "polymarket_relayer_api_key_address": "0xcaf3f08a9d477b2869450d45094a2f02fa898084",
            "polymarket_clob_api_key": "clob-key",
            "polymarket_clob_api_secret": base64.urlsafe_b64encode(b"secret-for-tests").decode(),
            "polymarket_clob_api_passphrase": "passphrase",
        },
    )

    async def fake_relayer_request_async(endpoint):
        return [{"apiKey": "019e122f-5aa5-775f-ac4b-f96c304bfbee"}]

    async def fake_l2_request_async(*, method, endpoint, body=None, serialized_body=None):
        return {"apiKeys": [{"apiKey": "clob-key"}]}

    monkeypatch.setattr(adapter, "_relayer_request_async", fake_relayer_request_async)
    monkeypatch.setattr(adapter, "_l2_request_async", fake_l2_request_async)

    result = asyncio.run(adapter.test_connectivity())

    assert any(check["scope"] == "funder" and check["ok"] for check in result["checks"])


def test_polymarket_adapter_place_order_requires_valid_signer_key_even_with_api_creds():
    adapter = PolymarketAdapter(
        wallet_address="0x1234567890abcdef1234567890abcdef12345678",
        private_key="not-a-real-evm-key",
        settings=_api_creds_settings(),
    )

    try:
        adapter.place_order(token_id="123", side="BUY", price=0.5, size=10)
        assert False, "expected RuntimeError"
    except RuntimeError as exc:
        assert "缺少有效的 EVM signer 私钥" in str(exc)


def test_polymarket_adapter_blocks_poly1271_live_orders_even_with_valid_signer():
    adapter = PolymarketAdapter(
        wallet_address="0xcaf3f08a9d477b2869450d45094a2f02fa898084",
        private_key="0x" + "1" * 64,
        settings={
            "polymarket_signature_type": 3,
            "polymarket_funder_address": "0x6446e5039008f19dc1f10ca60d0830fa459e2329",
        },
    )

    try:
        adapter.place_order(token_id="123", side="BUY", price=0.5, size=10)
        assert False, "expected RuntimeError"
    except RuntimeError as exc:
        assert "已知上游问题" in str(exc)


def test_polymarket_adapter_connectivity_reports_poly1271_order_submission_blocker(monkeypatch):
    adapter = PolymarketAdapter(
        wallet_address="0xcaf3f08a9d477b2869450d45094a2f02fa898084",
        private_key="0x" + "1" * 64,
        settings={
            "polymarket_signature_type": 3,
            "polymarket_funder_address": "0x6446e5039008f19dc1f10ca60d0830fa459e2329",
            "polymarket_relayer_api_key": "019e122f-5aa5-775f-ac4b-f96c304bfbee",
            "polymarket_relayer_api_key_address": "0xcaf3f08a9d477b2869450d45094a2f02fa898084",
            "polymarket_clob_api_key": "clob-key",
            "polymarket_clob_api_secret": base64.urlsafe_b64encode(b"secret-for-tests").decode(),
            "polymarket_clob_api_passphrase": "passphrase",
        },
    )

    async def fake_relayer_request_async(endpoint):
        return [{"apiKey": "019e122f-5aa5-775f-ac4b-f96c304bfbee"}]

    async def fake_l2_request_async(*, method, endpoint, body=None, serialized_body=None):
        return {"apiKeys": [{"apiKey": "clob-key"}]}

    monkeypatch.setattr(adapter, "_relayer_request_async", fake_relayer_request_async)
    monkeypatch.setattr(adapter, "_l2_request_async", fake_l2_request_async)

    result = asyncio.run(adapter.test_connectivity())

    assert any(check["scope"] == "order_submission" and check["ok"] is False for check in result["checks"])
    assert "已知上游问题" in result["overall_hint"]


def test_polymarket_adapter_cancel_order_supports_api_creds_without_signer(monkeypatch):
    adapter = PolymarketAdapter(
        wallet_address="0x1234567890abcdef1234567890abcdef12345678",
        private_key="not-a-real-evm-key",
        settings=_api_creds_settings(),
    )

    def fake_l2_request_sync(*, method, endpoint, body=None, serialized_body=None):
        assert method == "DELETE"
        assert endpoint == "/order"
        assert body == {"orderID": "order-123"}
        assert serialized_body == '{"orderID":"order-123"}'
        return {"status": "canceled", "orderID": "order-123"}

    monkeypatch.setattr(adapter, "_l2_request_sync", fake_l2_request_sync)

    result = adapter.cancel_order("order-123")

    assert result["order_id"] == "order-123"
    assert result["status"] == "canceled"


def test_polymarket_adapter_preflight_collateral_balance_blocks_zero_balance(monkeypatch):
    adapter = PolymarketAdapter(
        wallet_address="0x1234567890abcdef1234567890abcdef12345678",
        private_key="0x" + "1" * 64,
        settings=_api_creds_settings(),
    )

    class FakeClient:
        @staticmethod
        def get_balance_allowance(params):
            return {"balance": "0", "allowances": {}}

    monkeypatch.setattr(adapter, "_build_authed_client", lambda: FakeClient())

    result = asyncio.run(adapter.preflight_collateral_balance("BUY"))

    assert result["scope"] == "collateral_balance"
    assert result["ok"] is False
    assert result["status_code"] == 409
    assert "余额为 0" in result["message"]