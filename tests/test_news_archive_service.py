import asyncio
from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.market_anomaly import NewsArchive
from app.schemas.market_insight import MarketNews
from app.services.news_archive_service import NewsArchiveService


def create_archive_service(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    NewsArchive.__table__.create(bind=engine)
    testing_session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    monkeypatch.setattr("app.services.news_archive_service.SessionLocal", testing_session_local)

    service = NewsArchiveService()
    service.enabled = True
    service.refresh_batch_size = 8
    service.stale_after_seconds = 900
    service.symbol_stale_after_seconds = 900
    return service, testing_session_local


def test_archive_news_items_dedupes_and_merges_symbols(monkeypatch):
    service, testing_session_local = create_archive_service(monkeypatch)
    published_at = datetime(2026, 3, 14, 12, 0, 0)

    archived_count = service.archive_news_items(
        [
            MarketNews(
                title="TRUMP token spikes after derivatives volume surge",
                source="CoinDesk",
                source_domain="coindesk.com",
                url="https://www.coindesk.com/markets/trump-token-spikes?ref=home",
                summary="Initial summary",
                published_at=published_at,
                symbols=["TRUMPUSDT"],
            ),
            MarketNews(
                title="TRUMP token spikes after derivatives volume surge",
                source="CoinDesk",
                source_domain="coindesk.com",
                url="https://www.coindesk.com/markets/trump-token-spikes",
                summary="Updated summary",
                published_at=published_at,
                symbols=["TRUMP", "BTCUSDT"],
            ),
        ]
    )

    session = testing_session_local()
    try:
        rows = session.query(NewsArchive).all()
        assert archived_count == 1
        assert len(rows) == 1
        assert rows[0].symbols == ["BTC", "TRUMP"]
        assert rows[0].symbols_text == "|BTC|TRUMP|"
        assert rows[0].summary == "Updated summary"
        assert rows[0].url == "https://www.coindesk.com/markets/trump-token-spikes"
    finally:
        session.close()


def test_list_news_filters_by_symbol_and_hours(monkeypatch):
    service, _ = create_archive_service(monkeypatch)
    now = datetime.utcnow()

    service.archive_news_items(
        [
            MarketNews(
                title="Recent BTC headline",
                source="CoinDesk",
                source_domain="coindesk.com",
                published_at=now - timedelta(hours=2),
                symbols=["BTCUSDT"],
            ),
            MarketNews(
                title="Older BTC headline",
                source="CoinDesk",
                source_domain="coindesk.com",
                published_at=now - timedelta(hours=30),
                symbols=["BTC"],
            ),
            MarketNews(
                title="Recent ETH headline",
                source="CoinDesk",
                source_domain="coindesk.com",
                published_at=now - timedelta(hours=1),
                symbols=["ETHUSDT"],
            ),
        ]
    )

    items = service.list_news(limit=10, symbol="BTCUSDT", hours=24)

    assert len(items) == 1
    assert items[0].title == "Recent BTC headline"
    assert items[0].symbols == ["BTC"]


def test_ensure_general_news_uses_fresh_archive_without_refetch(monkeypatch):
    service, _ = create_archive_service(monkeypatch)
    now = datetime.utcnow()
    service.archive_news_items(
        [
            MarketNews(
                title="Fresh archived headline",
                source="PANews",
                source_domain="panewslab.com",
                published_at=now - timedelta(minutes=5),
                symbols=["BTCUSDT"],
            )
        ]
    )

    async def fail_fetch(limit):
        raise AssertionError("fetch_general_news should not be called when archive is fresh")

    monkeypatch.setattr("app.services.news_archive_service.news_service.fetch_general_news", fail_fetch)

    items = asyncio.run(service.ensure_general_news(limit=5))

    assert len(items) == 1
    assert items[0].title == "Fresh archived headline"


def test_ensure_symbol_news_fetches_and_archives_when_missing(monkeypatch):
    service, testing_session_local = create_archive_service(monkeypatch)
    published_at = datetime(2026, 3, 14, 10, 0, 0)

    async def fake_fetch_symbol_news(symbol, limit):
        assert symbol == "TRUMPUSDT"
        return [
            MarketNews(
                title="TRUMP token rallies after exchange listing rumor",
                source="Cointelegraph",
                source_domain="cointelegraph.com",
                published_at=published_at,
                symbols=["TRUMP"],
            )
        ]

    monkeypatch.setattr("app.services.news_archive_service.news_service.fetch_symbol_news", fake_fetch_symbol_news)

    items = asyncio.run(service.ensure_symbol_news("TRUMPUSDT", limit=5))

    session = testing_session_local()
    try:
        rows = session.query(NewsArchive).all()
        assert len(items) == 1
        assert items[0].title.startswith("TRUMP token rallies")
        assert len(rows) == 1
        assert rows[0].symbols_text == "|TRUMP|"
    finally:
        session.close()