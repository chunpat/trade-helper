from datetime import datetime

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import relationship

from .base import Base, BaseMixin


class MarketMetricSnapshot(Base, BaseMixin):
    __tablename__ = "market_metric_snapshots"

    symbol = Column(String(20), nullable=False, index=True)
    last_price = Column(Float, nullable=False)
    price_change_percent_24h = Column(Float, nullable=False)
    volume_24h = Column(Float)
    quote_volume_24h = Column(Float, nullable=False)
    funding_rate = Column(Float)
    open_interest = Column(Float)
    long_short_ratio = Column(Float)
    rank_by_quote_volume = Column(Integer, nullable=False)
    captured_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    raw_payload = Column(JSON)


class AnomalyEvent(Base, BaseMixin):
    __tablename__ = "anomaly_events"

    symbol = Column(String(20), nullable=False, index=True)
    status = Column(String(20), nullable=False, default="active", index=True)
    event_type = Column(String(50), nullable=False)
    anomaly_score = Column(Float, nullable=False)
    anomaly_level = Column(String(20), nullable=False)
    trigger_reasons = Column(JSON)
    description = Column(Text)

    last_price = Column(Float)
    price_change_percent_24h = Column(Float)
    volume_24h = Column(Float)
    quote_volume_24h = Column(Float)
    funding_rate = Column(Float)
    open_interest = Column(Float)
    long_short_ratio = Column(Float)

    credibility_label = Column(String(30), nullable=False, default="待核实")
    credibility_score = Column(Float)
    evidence_summary = Column(Text)
    source_summary = Column(String(255))

    trade_bias = Column(String(20), nullable=False, default="neutral")
    trade_confidence = Column(Float)
    trade_recommendation = Column(Text)
    suggested_entry = Column(Float)
    suggested_stop_loss = Column(Float)
    suggested_take_profit = Column(Float)
    risk_note = Column(Text)

    raw_metrics = Column(JSON)
    llm_payload = Column(JSON)
    first_detected_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    last_detected_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    last_analyzed_at = Column(DateTime)
    expires_at = Column(DateTime)
    occurrence_count = Column(Integer, nullable=False, default=1)

    news_items = relationship(
        "AnomalyNews",
        back_populates="event",
        cascade="all, delete-orphan",
        order_by="AnomalyNews.published_at.desc()"
    )


class AnomalyNews(Base, BaseMixin):
    __tablename__ = "anomaly_news"

    event_id = Column(Integer, ForeignKey("anomaly_events.id"), nullable=False, index=True)
    symbol = Column(String(20), nullable=False, index=True)
    title = Column(String(500), nullable=False)
    source = Column(String(120), nullable=False)
    source_domain = Column(String(255))
    url = Column(String(1000))
    published_at = Column(DateTime, nullable=False, index=True)
    sentiment = Column(String(20))
    summary = Column(Text)
    raw_payload = Column(JSON)

    event = relationship("AnomalyEvent", back_populates="news_items")


class NarrativeEvent(Base, BaseMixin):
    __tablename__ = "narrative_events"

    symbol = Column(String(20), nullable=False, index=True)
    narrative_type = Column(String(30), nullable=False, index=True)
    narrative_title = Column(String(200), nullable=False)
    narrative_summary = Column(Text)
    confidence = Column(Float, nullable=False)
    is_positive_catalyst = Column(Text, nullable=False, default="false")
    catalyst_strength = Column(Float, default=0)
    suggested_action = Column(String(20))
    risk_warning = Column(Text)
    price_change_percent_24h = Column(Float)
    anomaly_score = Column(Float)
    anomaly_event_id = Column(Integer, ForeignKey("anomaly_events.id"), index=True)
    news_sources = Column(JSON)
    source_news_ids = Column(JSON)
    llm_payload = Column(JSON)
    detected_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    expires_at = Column(DateTime)


class NewsArchive(Base, BaseMixin):
    __tablename__ = "news_archive"

    dedupe_key = Column(String(64), nullable=False, unique=True, index=True)
    title = Column(String(500), nullable=False)
    source = Column(String(120), nullable=False, index=True)
    source_domain = Column(String(255), index=True)
    url = Column(String(1000))
    published_at = Column(DateTime, nullable=False, index=True)
    sentiment = Column(String(20))
    summary = Column(Text)
    symbols = Column(JSON)
    symbols_text = Column(String(500), index=True)
    first_seen_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    last_seen_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    raw_payload = Column(JSON)