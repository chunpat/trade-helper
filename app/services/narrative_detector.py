import json
import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import httpx

from app.core.database import SessionLocal
from app.models.market_anomaly import NarrativeEvent
from app.schemas.market_insight import MarketNews

logger = logging.getLogger(__name__)


class NarrativeDetector:
    NARRATIVE_TYPES = {
        "product_launch": "产品/功能上线",
        "exchange_listing": "交易所上币",
        "partnership": "重大合作/投资",
        "regulation": "监管利好",
        "insider_leak": "内幕/传闻",
        "pure_speculation": "纯市场炒作",
        "macro_sentiment": "宏观情绪驱动",
        "other": "其他",
    }

    NARRATIVE_TRIGGER_MIN_SCORE = 0.58
    NARRATIVE_TRIGGER_MIN_CHANGE_PCT = 5.0

    def __init__(self):
        self.api_key = os.getenv("LLM_API_KEY", "").strip()
        self.base_url = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        self.model = os.getenv("LLM_MODEL", "gpt-4o-mini")
        self.timeout = float(os.getenv("LLM_TIMEOUT_SECONDS", "30"))
        self.enabled = bool(self.api_key)

    async def detect(
        self,
        anomaly: Dict[str, Any],
        news_items: List[MarketNews],
        anomaly_event_id: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        anomaly_score = float(anomaly.get("anomaly_score") or 0)
        price_change = float(anomaly.get("price_change_percent_24h") or 0)

        if anomaly_score < self.NARRATIVE_TRIGGER_MIN_SCORE:
            return None
        if abs(price_change) < self.NARRATIVE_TRIGGER_MIN_CHANGE_PCT:
            return None

        if self.enabled:
            try:
                result = await self._call_llm(anomaly, news_items)
            except Exception as exc:
                logger.warning("narrative-detector: llm call failed: %s", exc)
                result = None
        else:
            result = None

        if not result:
            result = self._heuristic(anomaly, news_items)

        self._save(anomaly, result, news_items, anomaly_event_id)
        return result

    async def _call_llm(self, anomaly: Dict[str, Any], news_items: List[MarketNews]) -> Optional[Dict[str, Any]]:
        evidence = [
            {
                "title": item.title,
                "source": item.source,
                "source_domain": item.source_domain,
                "url": item.url,
                "summary": item.summary,
            }
            for item in news_items[:8]
        ]

        prompt_payload = {
            "symbol": anomaly.get("symbol"),
            "last_price": anomaly.get("last_price"),
            "price_change_percent_24h": anomaly.get("price_change_percent_24h"),
            "quote_volume_24h": anomaly.get("quote_volume_24h"),
            "trigger_reasons": anomaly.get("trigger_reasons", []),
            "news_items": evidence,
        }

        system_prompt = (
            "你是加密货币市场叙事分析助手。根据给定的行情异动数据和关联新闻，"
            "分析推动这次价格异动的核心叙事是什么。"
            "请仅返回 JSON，不要输出额外解释。"
            "JSON 必须包含: "
            "narrative_type (可选值: product_launch, exchange_listing, partnership, regulation, insider_leak, pure_speculation, macro_sentiment, other), "
            "narrative_title (20字以内的叙事标题), "
            "narrative_summary (100字以内的叙事分析), "
            "confidence (0-100, 表示对该叙事判断的置信度), "
            "is_positive_catalyst (true/false, 是否为重大利好), "
            "catalyst_strength (0-100, 利好强度评分), "
            "suggested_action (建议操作方向: long, short, wait, reduce), "
            "risk_warning (风险提示). "
        )

        payload = {
            "model": self.model,
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(prompt_payload, ensure_ascii=False)},
            ],
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(f"{self.base_url}/chat/completions", headers=headers, json=payload)

        if response.status_code >= 400:
            raise RuntimeError(f"llm status={response.status_code} body={response.text[:400]}")

        data = response.json()
        content = data.get("choices", [{}])[0].get("message", {}).get("content")
        if not content:
            return None

        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            return None

        return {
            "narrative_type": parsed.get("narrative_type", "other"),
            "narrative_title": parsed.get("narrative_title", ""),
            "narrative_summary": parsed.get("narrative_summary", ""),
            "confidence": float(parsed.get("confidence", 50)),
            "is_positive_catalyst": bool(parsed.get("is_positive_catalyst", False)),
            "catalyst_strength": float(parsed.get("catalyst_strength", 0)),
            "suggested_action": parsed.get("suggested_action", "wait"),
            "risk_warning": parsed.get("risk_warning", ""),
            "llm_payload": data,
        }

    def _heuristic(self, anomaly: Dict[str, Any], news_items: List[MarketNews]) -> Dict[str, Any]:
        price_change = float(anomaly.get("price_change_percent_24h") or 0)
        news_count = len(news_items)

        if news_count >= 3:
            narrative_type = "pure_speculation"
            confidence = min(60, 30 + news_count * 5)
            narrative_title = "多消息驱动行情异动"
            narrative_summary = f"检测到 {news_count} 条相关新闻，需进一步人工研判叙事类型"
        elif news_count >= 1:
            narrative_type = "other"
            confidence = 40
            narrative_title = "少量消息伴随异动"
            narrative_summary = "新闻数量不足以判断叙事类型，建议关注后续动态"
        else:
            narrative_type = "pure_speculation"
            confidence = 30
            narrative_title = "纯资金驱动异动"
            narrative_summary = "未检测到相关新闻，当前异动更多来自资金面或技术面驱动"

        is_positive = price_change > 5
        return {
            "narrative_type": narrative_type,
            "narrative_title": narrative_title,
            "narrative_summary": narrative_summary,
            "confidence": float(confidence),
            "is_positive_catalyst": is_positive and news_count >= 1,
            "catalyst_strength": min(80, abs(price_change) + news_count * 10),
            "suggested_action": "long" if is_positive else ("short" if price_change < -5 else "wait"),
            "risk_warning": "纯规则判断可信度有限，建议结合更多信息源确认" if news_count < 2 else "",
            "llm_payload": None,
        }

    def _save(
        self,
        anomaly: Dict[str, Any],
        result: Dict[str, Any],
        news_items: List[MarketNews],
        anomaly_event_id: Optional[int],
    ) -> None:
        try:
            db = SessionLocal()
            try:
                news_sources = list({item.source_domain for item in news_items if item.source_domain})
                source_news_ids = [getattr(item, "id", None) for item in news_items if hasattr(item, "id")]
                source_news_ids = [i for i in source_news_ids if i is not None]

                event = NarrativeEvent(
                    symbol=anomaly.get("symbol", ""),
                    narrative_type=result.get("narrative_type", "other"),
                    narrative_title=result.get("narrative_title", ""),
                    narrative_summary=result.get("narrative_summary", ""),
                    confidence=float(result.get("confidence", 0)),
                    is_positive_catalyst="true" if result.get("is_positive_catalyst") else "false",
                    catalyst_strength=float(result.get("catalyst_strength", 0)),
                    suggested_action=result.get("suggested_action", "") or "",
                    risk_warning=result.get("risk_warning", "") or "",
                    price_change_percent_24h=float(anomaly.get("price_change_percent_24h") or 0),
                    anomaly_score=float(anomaly.get("anomaly_score") or 0),
                    anomaly_event_id=anomaly_event_id,
                    news_sources=news_sources,
                    source_news_ids=source_news_ids,
                    llm_payload=result.get("llm_payload"),
                    detected_at=datetime.utcnow(),
                    expires_at=datetime.utcnow() + timedelta(hours=72),
                )
                db.add(event)
                db.commit()
            finally:
                db.close()
        except Exception:
            logger.exception("narrative-detector: failed to save narrative event")


narrative_detector = NarrativeDetector()
