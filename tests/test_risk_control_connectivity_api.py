import importlib.util
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient


MODULE_PATH = Path(__file__).resolve().parents[1] / "app" / "api" / "v1" / "risk_control.py"
SPEC = importlib.util.spec_from_file_location("risk_control_api_module_connectivity", MODULE_PATH)
risk_control_api = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(risk_control_api)
router = risk_control_api.router


class FakeQuery:
    def __init__(self, account):
        self.account = account

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self.account


class FakeDB:
    def __init__(self, account):
        self.account = account

    def query(self, model):
        return FakeQuery(self.account)


class FakeAdapter:
    async def test_connectivity(self):
        return {
            "key_masked": "r9Vo****abcd",
            "spot_account": {
                "scope": "spot",
                "endpoint": "/api/v3/account",
                "ok": True,
                "status_code": 200,
                "code": None,
                "message": None,
                "hint": "接口访问正常。",
            },
            "futures_account": {
                "scope": "futures",
                "endpoint": "/fapi/v2/account",
                "ok": False,
                "status_code": 401,
                "code": -2015,
                "message": "Invalid API-key, IP, or permissions for action",
                "hint": "Binance 拒绝了这组 key 的合约账户访问。优先检查 API Key 是否开启了 Futures/永续合约权限，以及 IP 白名单是否包含当前服务出口 IP。仅切换统一账户/经典账户通常不会直接返回 -2015。",
            },
            "overall_hint": "现货接口正常，但合约接口被 Binance 拒绝。更像是 Futures 权限未开启、合约权限被关闭，或 IP 白名单未覆盖当前服务出口 IP，而不是代码兼容问题。",
            "account_mode_note": "如果你最近把 Binance 账户从统一账户切回经典多资金钱包，更常见的连带影响是 API 权限、IP 白名单或 API Key 重新配置；单纯账户模式切换通常不会直接映射成 -2015。",
        }


def create_test_app(fake_db):
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[risk_control_api.get_current_user] = lambda: {"id": 1}
    app.dependency_overrides[risk_control_api.get_db] = lambda: fake_db
    return app


def test_account_connectivity_endpoint_returns_actionable_hints(monkeypatch):
    account = SimpleNamespace(
        id=1,
        exchange="binance",
        name="binance",
        api_key="masked-key",
        api_secret="masked-secret",
    )
    fake_db = FakeDB(account)

    monkeypatch.setattr(
        "app.services.exchange.binance_adapter.create_adapter_for_account",
        lambda acct: FakeAdapter(),
    )

    client = TestClient(create_test_app(fake_db))
    response = client.get("/api/v1/risk-control/accounts/1/connectivity")

    assert response.status_code == 200
    payload = response.json()
    assert payload["account_id"] == 1
    assert payload["account_name"] == "binance"
    assert payload["spot_account"]["ok"] is True
    assert payload["futures_account"]["code"] == -2015
    assert "Futures 权限" in payload["overall_hint"]
    assert "统一账户" in payload["account_mode_note"]