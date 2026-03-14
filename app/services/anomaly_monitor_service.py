import asyncio
import logging
import os
from datetime import date, datetime, timedelta
from statistics import median
from typing import Any, Dict, List, Optional

import httpx
from pydantic import BaseModel

from app.core.database import SessionLocal
from app.models.market_anomaly import AnomalyEvent, AnomalyNews, MarketMetricSnapshot
from app.schemas.market_insight import (
    AnomalyEventDetail,
    AnomalyEventSummary,
    AnomalyTradingAdvice,
    MarketNews,
)
from app.services.news_archive_service import news_archive_service
from app.services.news_analysis_service import news_analysis_service

logger = logging.getLogger(__name__)


class AnomalyMonitorService:
    BINANCE_FAPI = "https://fapi.binance.com/fapi/v1"
    BINANCE_FUTURES_DATA = "https://fapi.binance.com/futures/data"

    def __init__(self, interval: Optional[int] = None):
        self.interval = interval or int(os.getenv("ANOMALY_SCAN_INTERVAL", "300"))
        self.top_n = int(os.getenv("ANOMALY_TOP_N", "100"))
        self.candidate_limit = int(os.getenv("ANOMALY_CANDIDATE_LIMIT", "12"))
        self.alert_threshold = float(os.getenv("ANOMALY_ALERT_THRESHOLD", "0.58"))
        self.cooldown_minutes = int(os.getenv("ANOMALY_COOLDOWN_MINUTES", "30"))
        self.news_limit = int(os.getenv("ANOMALY_NEWS_LIMIT", "6"))
        self._task = None
        self._running = False
        self._last_scan_at: Optional[datetime] = None

    async def scan_once(self) -> List[Dict[str, Any]]:
        self._close_stale_events()

        async with httpx.AsyncClient(timeout=12.0) as client:
            tickers = await self._fetch_top_tickers(client)
            if not tickers:
                logger.warning("anomaly-monitor: no tickers fetched from Binance")
                return []

            previous_snapshots = self._load_latest_snapshots([ticker["symbol"] for ticker in tickers])
            candidates = self._build_candidates(tickers, previous_snapshots)
            self._persist_snapshots(tickers)
            await self._refresh_news_archive_if_needed()

            if not candidates:
                self._last_scan_at = datetime.utcnow()
                return []

            tasks = [self._enrich_candidate(client, candidate) for candidate in candidates]
            enriched_candidates = await asyncio.gather(*tasks, return_exceptions=True)

        recorded_events: List[Dict[str, Any]] = []
        for result in enriched_candidates:
            if isinstance(result, Exception):
                logger.warning("anomaly-monitor: candidate enrichment failed: %s", result)
                continue
            if result["anomaly_score"] < self.alert_threshold:
                continue

            news_items = await news_archive_service.ensure_symbol_news(result["symbol"], self.news_limit)
            analysis = await news_analysis_service.analyze_anomaly(result, news_items)
            stored = self._upsert_event(result, analysis, news_items)
            if stored:
                recorded_events.append(stored)

        self._last_scan_at = datetime.utcnow()
        logger.info("anomaly-monitor: scan completed top_n=%s events=%s", self.top_n, len(recorded_events))
        return recorded_events

    async def poller(self):
        self._running = True
        logger.info("anomaly-monitor: poller started interval=%s", self.interval)
        while self._running:
            try:
                await self.scan_once()
            except Exception:
                logger.exception("anomaly-monitor: poller iteration failed")
            await asyncio.sleep(self.interval)

    def start(self):
        if self._task is not None:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.get_event_loop()
        self._task = loop.create_task(self.poller())
        loop.create_task(self.scan_once())

    def stop(self):
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()

    async def list_active_anomalies(self, limit: int = 10) -> List[AnomalyEventSummary]:
        return await self.list_anomalies(limit=limit, status="active")

    async def list_anomalies(self, limit: int = 20, status: Optional[str] = None) -> List[AnomalyEventSummary]:
        db = SessionLocal()
        try:
            query = db.query(AnomalyEvent)
            if status:
                query = query.filter(AnomalyEvent.status == status)
            events = self._sort_events_for_display(query.all(), status)
            return [self._to_event_summary(event) for event in events[:limit]]
        finally:
            db.close()

    def _sort_events_for_display(self, events: List[AnomalyEvent], status: Optional[str] = None) -> List[AnomalyEvent]:
        if status == "active":
            return sorted(
                events,
                key=lambda event: (
                    float(event.anomaly_score or 0.0),
                    float(event.quote_volume_24h or 0.0),
                    abs(float(event.price_change_percent_24h or 0.0)),
                    event.last_detected_at or datetime.min,
                ),
                reverse=True,
            )

        return sorted(
            events,
            key=lambda event: event.last_detected_at or datetime.min,
            reverse=True,
        )

    async def get_anomaly_detail(self, event_id: int) -> Optional[AnomalyEventDetail]:
        db = SessionLocal()
        try:
            event = db.query(AnomalyEvent).filter(AnomalyEvent.id == event_id).first()
            if not event:
                return None
            return self._to_event_detail(event)
        finally:
            db.close()

    def get_last_scan_at(self) -> Optional[datetime]:
        latest_snapshot_at = self._get_latest_snapshot_captured_at()
        if latest_snapshot_at and self._last_scan_at:
            return max(self._last_scan_at, latest_snapshot_at)
        return latest_snapshot_at or self._last_scan_at

    def _get_latest_snapshot_captured_at(self) -> Optional[datetime]:
        db = SessionLocal()
        try:
            row = (
                db.query(MarketMetricSnapshot.captured_at)
                .order_by(MarketMetricSnapshot.captured_at.desc())
                .first()
            )
            return row[0] if row else None
        finally:
            db.close()

    async def _refresh_news_archive_if_needed(self):
        try:
            await news_archive_service.refresh_general_news_if_stale()
        except Exception:
            logger.exception("anomaly-monitor: failed to refresh general news archive")

    async def _fetch_top_tickers(self, client: httpx.AsyncClient) -> List[Dict[str, Any]]:
        response = await client.get(f"{self.BINANCE_FAPI}/ticker/24hr")
        response.raise_for_status()
        tickers = response.json()
        usdt_pairs = [item for item in tickers if item.get("symbol", "").endswith("USDT")]
        sorted_pairs = sorted(usdt_pairs, key=lambda item: float(item.get("quoteVolume", 0)), reverse=True)
        return [self._normalize_ticker(rank, ticker) for rank, ticker in enumerate(sorted_pairs[: self.top_n], start=1)]

    def _normalize_ticker(self, rank: int, ticker: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "rank": rank,
            "symbol": ticker.get("symbol", ""),
            "last_price": float(ticker.get("lastPrice", 0) or 0),
            "price_change_24h": float(ticker.get("priceChange", 0) or 0),
            "price_change_percent_24h": float(ticker.get("priceChangePercent", 0) or 0),
            "volume_24h": float(ticker.get("volume", 0) or 0),
            "quote_volume_24h": float(ticker.get("quoteVolume", 0) or 0),
            "high_24h": float(ticker.get("highPrice", 0) or 0),
            "low_24h": float(ticker.get("lowPrice", 0) or 0),
            "raw_payload": ticker,
        }

    def _load_latest_snapshots(self, symbols: List[str]) -> Dict[str, MarketMetricSnapshot]:
        if not symbols:
            return {}
        db = SessionLocal()
        try:
            rows = (
                db.query(MarketMetricSnapshot)
                .filter(MarketMetricSnapshot.symbol.in_(symbols))
                .filter(MarketMetricSnapshot.captured_at >= datetime.utcnow() - timedelta(hours=12))
                .order_by(MarketMetricSnapshot.symbol.asc(), MarketMetricSnapshot.captured_at.desc())
                .all()
            )
            latest: Dict[str, MarketMetricSnapshot] = {}
            for row in rows:
                if row.symbol not in latest:
                    latest[row.symbol] = row
            return latest
        finally:
            db.close()

    def _build_candidates(
        self,
        tickers: List[Dict[str, Any]],
        previous_snapshots: Dict[str, MarketMetricSnapshot],
    ) -> List[Dict[str, Any]]:
        if not tickers:
            return []

        median_quote_volume = median([item["quote_volume_24h"] for item in tickers if item["quote_volume_24h"] > 0] or [1.0])
        candidates: List[Dict[str, Any]] = []

        for item in tickers:
            symbol = item["symbol"]
            previous = previous_snapshots.get(symbol)
            rank_score = max(0.0, 1.0 - ((item["rank"] - 1) / max(self.top_n - 1, 1)))
            size_score = min(item["quote_volume_24h"] / max(median_quote_volume, 1.0), 3.0) / 3.0
            price_score = min(abs(item["price_change_percent_24h"]) / 8.0, 1.0)

            volume_delta_ratio = 0.0
            delta_price_score = 0.0
            volume_accel_score = 0.0
            if previous:
                previous_quote = float(previous.quote_volume_24h or 0)
                previous_price = float(previous.price_change_percent_24h or 0)
                if previous_quote > 0:
                    volume_delta_ratio = (item["quote_volume_24h"] - previous_quote) / previous_quote
                    volume_accel_score = min(max(volume_delta_ratio, 0.0) / 0.05, 1.0)
                delta_price_score = min(abs(item["price_change_percent_24h"] - previous_price) / 3.0, 1.0)

            base_score = min(
                1.0,
                (0.28 * price_score)
                + (0.18 * delta_price_score)
                + (0.22 * volume_accel_score)
                + (0.18 * rank_score)
                + (0.14 * size_score),
            )

            trigger_reasons = []
            if abs(item["price_change_percent_24h"]) >= 5:
                trigger_reasons.append(f"24H涨跌幅达到 {item['price_change_percent_24h']:.2f}%")
            if volume_delta_ratio >= 0.02:
                trigger_reasons.append(f"近一轮成交额抬升 {volume_delta_ratio * 100:.2f}%")
            if item["rank"] <= 10:
                trigger_reasons.append("成交额位于全市场前10")

            should_alert = base_score >= 0.42 or abs(item["price_change_percent_24h"]) >= 6 or volume_delta_ratio >= 0.05
            if should_alert:
                candidate = dict(item)
                candidate.update(
                    {
                        "base_score": round(base_score, 4),
                        "volume_delta_ratio": round(volume_delta_ratio, 4),
                        "trigger_reasons": trigger_reasons,
                    }
                )
                candidates.append(candidate)

        candidates.sort(key=lambda item: item["base_score"], reverse=True)
        return candidates[: self.candidate_limit]

    async def _enrich_candidate(self, client: httpx.AsyncClient, candidate: Dict[str, Any]) -> Dict[str, Any]:
        symbol = candidate["symbol"]
        funding_data, open_interest_data, ratio_data, klines = await asyncio.gather(
            self._safe_get(client, f"{self.BINANCE_FAPI}/premiumIndex", {"symbol": symbol}),
            self._safe_get(client, f"{self.BINANCE_FAPI}/openInterest", {"symbol": symbol}),
            self._safe_get(client, f"{self.BINANCE_FUTURES_DATA}/topLongShortAccountRatio", {"symbol": symbol, "period": "5m", "limit": 1}),
            self._safe_get(client, f"{self.BINANCE_FAPI}/klines", {"symbol": symbol, "interval": "5m", "limit": 12}),
        )

        funding_rate = None
        if isinstance(funding_data, dict):
            funding_rate = self._safe_float(funding_data.get("lastFundingRate"))

        open_interest = None
        if isinstance(open_interest_data, dict):
            open_interest = self._safe_float(open_interest_data.get("openInterest"))

        long_short_ratio = None
        if isinstance(ratio_data, list) and ratio_data:
            long_short_ratio = self._safe_float(ratio_data[0].get("longShortRatio"))

        candle_metrics = self._analyze_klines(klines if isinstance(klines, list) else [])
        funding_score = min(abs(funding_rate or 0.0) / 0.001, 1.0)
        ratio_score = min(abs((long_short_ratio or 1.0) - 1.0) / 0.6, 1.0)
        short_term_volume_score = min(max(candle_metrics["recent_volume_ratio"] - 1.0, 0.0) / 1.5, 1.0)
        volatility_score = min(max(abs(candle_metrics["momentum_1h"]) / 4.0, candle_metrics["range_pct"] / 0.04), 1.0)

        anomaly_score = min(
            1.0,
            (candidate["base_score"] * 0.55)
            + (short_term_volume_score * 0.18)
            + (funding_score * 0.12)
            + (ratio_score * 0.08)
            + (volatility_score * 0.07),
        )

        trigger_reasons = list(candidate.get("trigger_reasons", []))
        if candle_metrics["recent_volume_ratio"] >= 1.8:
            trigger_reasons.append(f"近5分钟成交额放大 {candle_metrics['recent_volume_ratio']:.2f} 倍")
        if abs(candle_metrics["momentum_1h"]) >= 3:
            trigger_reasons.append(f"1小时动量达到 {candle_metrics['momentum_1h']:.2f}%")
        if funding_rate is not None and abs(funding_rate) >= 0.0006:
            trigger_reasons.append(f"资金费率偏离 {funding_rate * 100:.4f}%")
        if long_short_ratio is not None and (long_short_ratio >= 1.8 or long_short_ratio <= 0.6):
            trigger_reasons.append(f"多空比失衡 {long_short_ratio:.2f}")

        event_type = self._select_event_type(candidate, candle_metrics, funding_rate, long_short_ratio)
        anomaly_level = self._score_to_level(anomaly_score)
        description = self._build_description(symbol, event_type, trigger_reasons)

        enriched = dict(candidate)
        enriched.update(
            {
                "event_type": event_type,
                "anomaly_level": anomaly_level,
                "anomaly_score": round(anomaly_score, 4),
                "funding_rate": funding_rate,
                "open_interest": open_interest,
                "long_short_ratio": long_short_ratio,
                "trigger_reasons": trigger_reasons,
                "description": description,
                "raw_metrics": {
                    **candidate,
                    "funding_rate": funding_rate,
                    "open_interest": open_interest,
                    "long_short_ratio": long_short_ratio,
                    "candle_metrics": candle_metrics,
                },
            }
        )
        return enriched

    def _analyze_klines(self, klines: List[List[Any]]) -> Dict[str, float]:
        if not klines:
            return {"range_pct": 0.0, "momentum_1h": 0.0, "recent_volume_ratio": 1.0}

        highs = [float(item[2]) for item in klines]
        lows = [float(item[3]) for item in klines]
        closes = [float(item[4]) for item in klines]
        quote_volumes = [float(item[7]) for item in klines if len(item) > 7]

        last_close = closes[-1] if closes else 0.0
        range_pct = ((max(highs) - min(lows)) / last_close) if last_close else 0.0
        momentum_1h = (((closes[-1] - closes[0]) / closes[0]) * 100) if len(closes) >= 2 and closes[0] else 0.0

        recent_volume_ratio = 1.0
        if len(quote_volumes) >= 2:
            average_previous = sum(quote_volumes[:-1]) / max(len(quote_volumes) - 1, 1)
            if average_previous > 0:
                recent_volume_ratio = quote_volumes[-1] / average_previous

        return {
            "range_pct": round(range_pct, 6),
            "momentum_1h": round(momentum_1h, 6),
            "recent_volume_ratio": round(recent_volume_ratio, 6),
        }

    def _select_event_type(
        self,
        candidate: Dict[str, Any],
        candle_metrics: Dict[str, float],
        funding_rate: Optional[float],
        long_short_ratio: Optional[float],
    ) -> str:
        if candle_metrics["recent_volume_ratio"] >= 1.8:
            return "volume_spike"
        if abs(candle_metrics["momentum_1h"]) >= 3 or abs(candidate["price_change_percent_24h"]) >= 8:
            return "price_dislocation"
        if (funding_rate is not None and abs(funding_rate) >= 0.0008) or (
            long_short_ratio is not None and (long_short_ratio >= 1.8 or long_short_ratio <= 0.6)
        ):
            return "derivatives_crowding"
        return "multi_factor_anomaly"

    def _score_to_level(self, score: float) -> str:
        if score >= 0.82:
            return "critical"
        if score >= 0.68:
            return "high"
        if score >= 0.55:
            return "medium"
        return "low"

    def _build_description(self, symbol: str, event_type: str, trigger_reasons: List[str]) -> str:
        if trigger_reasons:
            return f"{symbol} 触发 {event_type}，原因包括：" + "；".join(trigger_reasons[:4])
        return f"{symbol} 触发 {event_type}，等待更多信号补充。"

    async def _safe_get(self, client: httpx.AsyncClient, url: str, params: Dict[str, Any]) -> Any:
        try:
            response = await client.get(url, params=params)
            if response.status_code != 200:
                logger.debug("anomaly-monitor: request failed url=%s status=%s", url, response.status_code)
                return None
            return response.json()
        except Exception as exc:
            logger.debug("anomaly-monitor: request error url=%s error=%s", url, exc)
            return None

    def _persist_snapshots(self, tickers: List[Dict[str, Any]]):
        db = SessionLocal()
        try:
            snapshots = [
                MarketMetricSnapshot(
                    symbol=item["symbol"],
                    last_price=item["last_price"],
                    price_change_percent_24h=item["price_change_percent_24h"],
                    volume_24h=item["volume_24h"],
                    quote_volume_24h=item["quote_volume_24h"],
                    rank_by_quote_volume=item["rank"],
                    raw_payload=item["raw_payload"],
                    captured_at=datetime.utcnow(),
                )
                for item in tickers
            ]
            db.add_all(snapshots)
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("anomaly-monitor: failed to persist snapshots")
        finally:
            db.close()

    def _close_stale_events(self):
        cutoff = datetime.utcnow() - timedelta(minutes=self.cooldown_minutes)
        db = SessionLocal()
        try:
            stale_events = (
                db.query(AnomalyEvent)
                .filter(AnomalyEvent.status == "active")
                .filter(AnomalyEvent.last_detected_at < cutoff)
                .all()
            )
            for event in stale_events:
                event.status = "resolved"
                event.expires_at = datetime.utcnow()
            if stale_events:
                db.commit()
        except Exception:
            db.rollback()
            logger.exception("anomaly-monitor: failed to close stale events")
        finally:
            db.close()

    def _upsert_event(
        self,
        anomaly: Dict[str, Any],
        analysis: Dict[str, Any],
        news_items: List[MarketNews],
    ) -> Optional[Dict[str, Any]]:
        db = SessionLocal()
        now = datetime.utcnow()
        active_after = now - timedelta(minutes=self.cooldown_minutes)
        try:
            event = (
                db.query(AnomalyEvent)
                .filter(AnomalyEvent.symbol == anomaly["symbol"])
                .filter(AnomalyEvent.status == "active")
                .filter(AnomalyEvent.last_detected_at >= active_after)
                .order_by(AnomalyEvent.last_detected_at.desc())
                .first()
            )

            is_new = event is None
            if not event:
                event = AnomalyEvent(symbol=anomaly["symbol"], first_detected_at=now)
                db.add(event)

            event.status = "active"
            event.event_type = anomaly["event_type"]
            event.anomaly_score = anomaly["anomaly_score"]
            event.anomaly_level = anomaly["anomaly_level"]
            event.trigger_reasons = self._to_jsonable(anomaly.get("trigger_reasons", []))
            event.description = anomaly.get("description")
            event.last_price = anomaly.get("last_price")
            event.price_change_percent_24h = anomaly.get("price_change_percent_24h")
            event.volume_24h = anomaly.get("volume_24h")
            event.quote_volume_24h = anomaly.get("quote_volume_24h")
            event.funding_rate = anomaly.get("funding_rate")
            event.open_interest = anomaly.get("open_interest")
            event.long_short_ratio = anomaly.get("long_short_ratio")
            event.credibility_label = analysis.get("credibility_label", "待核实")
            event.credibility_score = analysis.get("credibility_score")
            event.evidence_summary = analysis.get("evidence_summary")
            event.source_summary = analysis.get("source_summary")
            event.trade_bias = analysis.get("trade_bias", "neutral")
            event.trade_confidence = analysis.get("trade_confidence")
            event.trade_recommendation = analysis.get("trade_recommendation")
            event.suggested_entry = analysis.get("suggested_entry")
            event.suggested_stop_loss = analysis.get("suggested_stop_loss")
            event.suggested_take_profit = analysis.get("suggested_take_profit")
            event.risk_note = analysis.get("risk_note")
            event.raw_metrics = self._to_jsonable(anomaly.get("raw_metrics"))
            event.llm_payload = self._to_jsonable(analysis.get("llm_payload"))
            event.last_detected_at = now
            event.last_analyzed_at = now
            event.expires_at = now + timedelta(minutes=self.cooldown_minutes)
            event.occurrence_count = 1 if is_new else (event.occurrence_count or 1) + 1

            event.news_items.clear()
            for item in news_items:
                event.news_items.append(
                    AnomalyNews(
                        symbol=anomaly["symbol"],
                        title=item.title,
                        source=item.source,
                        source_domain=item.source_domain,
                        url=item.url,
                        published_at=item.published_at,
                        sentiment=item.sentiment,
                        summary=item.summary,
                        raw_payload=self._to_jsonable(item),
                    )
                )

            db.commit()
            db.refresh(event)
            return {"id": event.id, "symbol": event.symbol, "anomaly_score": event.anomaly_score}
        except Exception:
            db.rollback()
            logger.exception("anomaly-monitor: failed to upsert anomaly event for %s", anomaly.get("symbol"))
            return None
        finally:
            db.close()

    def _to_event_summary(self, event: AnomalyEvent) -> AnomalyEventSummary:
        return AnomalyEventSummary(
            id=event.id,
            symbol=event.symbol,
            event_type=event.event_type,
            anomaly_score=event.anomaly_score,
            anomaly_level=event.anomaly_level,
            trigger_reasons=event.trigger_reasons or [],
            last_price=event.last_price,
            price_change_percent_24h=event.price_change_percent_24h,
            quote_volume_24h=event.quote_volume_24h,
            funding_rate=event.funding_rate,
            open_interest=event.open_interest,
            long_short_ratio=event.long_short_ratio,
            credibility_label=event.credibility_label,
            credibility_score=event.credibility_score,
            source_summary=event.source_summary,
            trade_bias=event.trade_bias,
            trade_confidence=event.trade_confidence,
            trade_recommendation=event.trade_recommendation,
            news_count=len(event.news_items or []),
            first_detected_at=event.first_detected_at,
            last_detected_at=event.last_detected_at,
        )

    def _to_event_detail(self, event: AnomalyEvent) -> AnomalyEventDetail:
        advice = AnomalyTradingAdvice(
            bias=event.trade_bias,
            confidence=event.trade_confidence or 0.0,
            recommendation=event.trade_recommendation or "建议等待更多确认。",
            suggested_entry=event.suggested_entry,
            suggested_stop_loss=event.suggested_stop_loss,
            suggested_take_profit=event.suggested_take_profit,
            risk_note=event.risk_note,
        )
        news = [
            MarketNews(
                id=item.id,
                title=item.title,
                source=item.source,
                source_domain=item.source_domain,
                sentiment=item.sentiment,
                url=item.url,
                summary=item.summary,
                published_at=item.published_at,
                symbols=[item.symbol],
            )
            for item in sorted(event.news_items or [], key=lambda news_item: news_item.published_at, reverse=True)
        ]
        summary = self._to_event_summary(event)
        return AnomalyEventDetail(
            **summary.dict(),
            description=event.description,
            evidence_summary=event.evidence_summary,
            raw_metrics=event.raw_metrics,
            advice=advice,
            news=news,
        )

    def _safe_float(self, value: Any) -> Optional[float]:
        if value is None or value == "":
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _to_jsonable(self, value: Any) -> Any:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        if isinstance(value, BaseModel):
            return value.model_dump(mode="json")
        if isinstance(value, dict):
            return {str(key): self._to_jsonable(item) for key, item in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [self._to_jsonable(item) for item in value]
        return str(value)


def get_anomaly_monitor_from_env() -> AnomalyMonitorService:
    return AnomalyMonitorService(interval=int(os.getenv("ANOMALY_SCAN_INTERVAL", "300")))


anomaly_monitor_service = get_anomaly_monitor_from_env()