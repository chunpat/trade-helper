from datetime import datetime
from types import SimpleNamespace

from app.models.market_anomaly import MarketMetricSnapshot
from app.schemas.market_insight import MarketNews
from app.services.anomaly_monitor_service import AnomalyMonitorService


def test_build_candidates_detects_price_and_volume_spike():
    service = AnomalyMonitorService(interval=300)
    service.top_n = 3
    service.candidate_limit = 3

    tickers = [
        {
            "rank": 1,
            "symbol": "TESTUSDT",
            "last_price": 11.2,
            "price_change_24h": 0.8,
            "price_change_percent_24h": 8.5,
            "volume_24h": 800000,
            "quote_volume_24h": 16000000,
            "high_24h": 11.8,
            "low_24h": 9.9,
            "raw_payload": {},
        },
        {
            "rank": 2,
            "symbol": "BTCUSDT",
            "last_price": 60000,
            "price_change_24h": 100,
            "price_change_percent_24h": 1.2,
            "volume_24h": 5000,
            "quote_volume_24h": 14000000,
            "high_24h": 61000,
            "low_24h": 59000,
            "raw_payload": {},
        },
        {
            "rank": 3,
            "symbol": "ETHUSDT",
            "last_price": 3000,
            "price_change_24h": 15,
            "price_change_percent_24h": 0.9,
            "volume_24h": 6000,
            "quote_volume_24h": 10000000,
            "high_24h": 3050,
            "low_24h": 2950,
            "raw_payload": {},
        },
    ]
    previous_snapshots = {
        "TESTUSDT": MarketMetricSnapshot(
            symbol="TESTUSDT",
            last_price=10.1,
            price_change_percent_24h=2.0,
            quote_volume_24h=12000000,
            captured_at=datetime.utcnow(),
            rank_by_quote_volume=3,
        )
    }

    candidates = service._build_candidates(tickers, previous_snapshots)

    assert candidates
    assert candidates[0]["symbol"] == "TESTUSDT"
    assert candidates[0]["base_score"] >= 0.42
    assert any("24H涨跌幅达到" in reason for reason in candidates[0]["trigger_reasons"])


def test_sort_events_for_display_prioritizes_hotter_active_events_over_recency():
    service = AnomalyMonitorService(interval=300)
    recent_low_score = SimpleNamespace(
        symbol="SMALLUSDT",
        anomaly_score=0.30,
        quote_volume_24h=12000000,
        price_change_percent_24h=8.0,
        last_detected_at=datetime(2026, 3, 14, 10, 5, 0),
    )
    older_hot_event = SimpleNamespace(
        symbol="TRUMPUSDT",
        anomaly_score=0.4226,
        quote_volume_24h=1457652588.83699,
        price_change_percent_24h=37.271,
        last_detected_at=datetime(2026, 3, 14, 10, 0, 0),
    )

    ordered = service._sort_events_for_display([recent_low_score, older_hot_event], status="active")

    assert ordered[0].symbol == "TRUMPUSDT"


def test_to_jsonable_serializes_market_news_datetime_fields_for_json_columns():
    service = AnomalyMonitorService(interval=300)
    published_at = datetime(2026, 3, 14, 11, 22, 33)

    payload = service._to_jsonable(
        MarketNews(
            title="TRUMP token spikes after liquidity burst",
            source="CoinDesk",
            source_domain="reuters.com",
            url="https://www.reuters.com/example",
            summary="A liquidity-driven move attracted heavy derivatives attention.",
            published_at=published_at,
            symbols=["TRUMP"],
        )
    )

    assert payload["published_at"] == published_at.isoformat()
    assert payload["symbols"] == ["TRUMP"]


def test_get_last_scan_at_falls_back_to_latest_snapshot(monkeypatch):
    service = AnomalyMonitorService(interval=300)
    snapshot_time = datetime(2026, 3, 14, 12, 0, 0)

    monkeypatch.setattr(service, "_get_latest_snapshot_captured_at", lambda: snapshot_time)

    assert service.get_last_scan_at() == snapshot_time


def test_get_last_scan_at_returns_newer_in_memory_timestamp(monkeypatch):
    service = AnomalyMonitorService(interval=300)
    snapshot_time = datetime(2026, 3, 14, 12, 0, 0)
    service._last_scan_at = datetime(2026, 3, 14, 12, 5, 0)

    monkeypatch.setattr(service, "_get_latest_snapshot_captured_at", lambda: snapshot_time)

    assert service.get_last_scan_at() == service._last_scan_at
