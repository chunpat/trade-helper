import asyncio
from datetime import datetime

from app.schemas.market_insight import MarketNews
from app.services.news_analysis_service import NewsAnalysisService


def test_heuristic_analysis_marks_multi_source_news_as_trusted():
    service = NewsAnalysisService()
    anomaly = {
        "symbol": "TESTUSDT",
        "anomaly_score": 0.82,
        "last_price": 12.5,
        "price_change_percent_24h": 9.2,
        "funding_rate": 0.0004,
        "long_short_ratio": 1.3,
    }
    news_items = [
        MarketNews(
            title="Test asset rallies on product launch",
            source="CoinDesk",
            source_domain="coindesk.com",
            published_at=datetime.utcnow(),
            url="https://www.coindesk.com/story",
            symbols=["TEST"],
        ),
        MarketNews(
            title="Exchange confirms listing roadmap update",
            source="Cointelegraph",
            source_domain="cointelegraph.com",
            published_at=datetime.utcnow(),
            url="https://cointelegraph.com/story",
            symbols=["TEST"],
        ),
    ]

    result = service._heuristic_analysis(anomaly, news_items)

    assert result["credibility_label"] == "可信"
    assert result["trade_bias"] == "long"
    assert result["suggested_entry"] is not None
    assert "coindesk.com" in result["source_summary"]


def test_parse_json_content_handles_fenced_json():
    service = NewsAnalysisService()
    content = "```json\n{\"credibility_label\": \"待核实\", \"trade_bias\": \"neutral\"}\n```"

    parsed = service._parse_json_content(content)

    assert parsed == {"credibility_label": "待核实", "trade_bias": "neutral"}


def test_provider_defaults_to_disabled_without_explicit_opt_in(monkeypatch):
    monkeypatch.delenv("ANOMALY_LLM_PROVIDER", raising=False)
    monkeypatch.setenv("LLM_API_KEY", "test-key")

    service = NewsAnalysisService()

    assert service.provider == service.PROVIDER_DISABLED


def test_analyze_anomaly_skips_remote_llm_when_provider_disabled(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("ANOMALY_LLM_PROVIDER", "disabled")
    service = NewsAnalysisService()

    async def fail_call_llm(*args, **kwargs):
        raise AssertionError("remote llm should not be called")

    service._call_llm = fail_call_llm
    result = asyncio.run(
        service.analyze_anomaly(
            {
                "symbol": "TESTUSDT",
                "anomaly_score": 0.61,
                "last_price": 2.35,
                "price_change_percent_24h": 12.0,
            },
            [],
        )
    )

    assert result["credibility_label"] == "待核实"
    assert result["llm_payload"] is None