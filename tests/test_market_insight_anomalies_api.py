from datetime import datetime
import importlib.util
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.schemas.market_insight import AnomalyEventDetail, AnomalyEventSummary, AnomalyTradingAdvice, MarketNews


MODULE_PATH = Path(__file__).resolve().parents[1] / "app" / "api" / "v1" / "market_insight.py"
SPEC = importlib.util.spec_from_file_location("market_insight_api_module", MODULE_PATH)
market_insight_api = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(market_insight_api)
router = market_insight_api.router


def create_test_app():
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    return app


def test_get_anomalies_endpoint(monkeypatch):
    async def fake_list_anomalies(limit: int, status: str):
        return [
            AnomalyEventSummary(
                id=1,
                symbol="TESTUSDT",
                event_type="volume_spike",
                anomaly_score=0.76,
                anomaly_level="high",
                trigger_reasons=["24H涨跌幅达到 8.50%"],
                last_price=11.2,
                price_change_percent_24h=8.5,
                quote_volume_24h=16000000,
                credibility_label="待核实",
                credibility_score=60,
                source_summary="coindesk.com",
                trade_bias="neutral",
                trade_confidence=45,
                trade_recommendation="等待更多确认",
                news_count=2,
                first_detected_at=datetime.utcnow(),
                last_detected_at=datetime.utcnow(),
            )
        ]

    monkeypatch.setattr(market_insight_api.anomaly_monitor_service, "list_anomalies", fake_list_anomalies)

    client = TestClient(create_test_app())
    response = client.get("/api/v1/market-insight/anomalies", params={"limit": 10, "status": "active"})

    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["symbol"] == "TESTUSDT"
    assert payload[0]["credibility_label"] == "待核实"


def test_get_anomaly_detail_endpoint(monkeypatch):
    async def fake_get_anomaly_detail(event_id: int):
        return AnomalyEventDetail(
            id=event_id,
            symbol="TESTUSDT",
            event_type="volume_spike",
            anomaly_score=0.76,
            anomaly_level="high",
            trigger_reasons=["24H涨跌幅达到 8.50%"],
            last_price=11.2,
            price_change_percent_24h=8.5,
            quote_volume_24h=16000000,
            credibility_label="可信",
            credibility_score=82,
            source_summary="coindesk.com, cointelegraph.com",
            trade_bias="long",
            trade_confidence=78,
            trade_recommendation="轻仓顺势做多",
            news_count=2,
            first_detected_at=datetime.utcnow(),
            last_detected_at=datetime.utcnow(),
            description="TESTUSDT 出现量价异常",
            evidence_summary="多家主流媒体交叉验证",
            raw_metrics={"last_price": 11.2},
            advice=AnomalyTradingAdvice(
                bias="long",
                confidence=78,
                recommendation="轻仓顺势做多",
                suggested_entry=11.15,
                suggested_stop_loss=10.86,
                suggested_take_profit=11.87,
                risk_note="防止追高",
            ),
            news=[
                MarketNews(
                    title="Test asset rallies on product launch",
                    source="CoinDesk",
                    source_domain="coindesk.com",
                    published_at=datetime.utcnow(),
                    url="https://www.coindesk.com/story",
                    symbols=["TEST"],
                )
            ],
        )

    monkeypatch.setattr(market_insight_api.anomaly_monitor_service, "get_anomaly_detail", fake_get_anomaly_detail)

    client = TestClient(create_test_app())
    response = client.get("/api/v1/market-insight/anomalies/1")

    assert response.status_code == 200
    payload = response.json()
    assert payload["symbol"] == "TESTUSDT"
    assert payload["advice"]["bias"] == "long"