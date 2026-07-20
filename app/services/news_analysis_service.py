import json
import logging
import os
from typing import Any, Dict, List, Optional

import httpx

from app.schemas.market_insight import MarketNews
from app.services.llm_compat import parse_json_content, prepare_chat_payload

logger = logging.getLogger(__name__)


class NewsAnalysisService:
    PROVIDER_DISABLED = "disabled"
    PROVIDER_OPENAI_COMPATIBLE = "openai-compatible"

    TRUSTED_DOMAINS = {
        "binance.com",
        "coindesk.com",
        "cointelegraph.com",
        "theblock.co",
        "decrypt.co",
        "bloomberg.com",
        "reuters.com",
        "blockworks.co",
        "cryptoslate.com",
        "bitcoinmagazine.com",
        "news.bitcoin.com",
        "thedefiant.io",
        "coingape.com",
        "ambcrypto.com",
        "panewslab.com",
    }

    def __init__(self):
        self.api_key = os.getenv("LLM_API_KEY", "").strip()
        self.base_url = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        self.model = os.getenv("LLM_MODEL", "gpt-4o-mini")
        self.timeout = float(os.getenv("LLM_TIMEOUT_SECONDS", "30"))
        self.provider = self._resolve_provider()

    async def analyze_anomaly(self, anomaly: Dict[str, Any], news_items: List[MarketNews]) -> Dict[str, Any]:
        if self.provider == self.PROVIDER_OPENAI_COMPATIBLE and self.api_key:
            try:
                result = await self._call_llm(anomaly, news_items)
                if result:
                    return result
            except Exception as exc:
                logger.warning("news-analysis: llm call failed, using heuristic fallback: %s", exc)

        return self._heuristic_analysis(anomaly, news_items)

    def _resolve_provider(self) -> str:
        raw_provider = os.getenv("ANOMALY_LLM_PROVIDER", "").strip().lower()
        if raw_provider in {"disabled", "heuristic", "none", "off"}:
            return self.PROVIDER_DISABLED
        if raw_provider == "":
            return self.PROVIDER_DISABLED
        if raw_provider == "auto":
            return self.PROVIDER_OPENAI_COMPATIBLE if self.api_key else self.PROVIDER_DISABLED
        if raw_provider in {"openai", "openai-compatible", "compatible"}:
            return self.PROVIDER_OPENAI_COMPATIBLE

        logger.warning("news-analysis: unsupported ANOMALY_LLM_PROVIDER=%s, fallback to disabled", raw_provider)
        return self.PROVIDER_DISABLED

    async def _call_llm(self, anomaly: Dict[str, Any], news_items: List[MarketNews]) -> Optional[Dict[str, Any]]:
        evidence = [
            {
                "title": item.title,
                "source": item.source,
                "source_domain": item.source_domain,
                "published_at": item.published_at.isoformat(),
                "url": item.url,
                "summary": item.summary,
            }
            for item in news_items
        ]
        prompt_payload = {
            "symbol": anomaly.get("symbol"),
            "event_type": anomaly.get("event_type"),
            "anomaly_score": anomaly.get("anomaly_score"),
            "anomaly_level": anomaly.get("anomaly_level"),
            "last_price": anomaly.get("last_price"),
            "price_change_percent_24h": anomaly.get("price_change_percent_24h"),
            "quote_volume_24h": anomaly.get("quote_volume_24h"),
            "funding_rate": anomaly.get("funding_rate"),
            "open_interest": anomaly.get("open_interest"),
            "long_short_ratio": anomaly.get("long_short_ratio"),
            "trigger_reasons": anomaly.get("trigger_reasons", []),
            "news_items": evidence,
        }

        system_prompt = (
            "你是加密交易风控分析助手。"
            "请仅返回 JSON，不要输出额外解释。"
            "JSON 必须包含: credibility_label(可信|待核实|高风险谣言), credibility_score(0-100),"
            " evidence_summary, source_summary, trade_bias(long|short|neutral), trade_confidence(0-100),"
            " trade_recommendation, suggested_entry(number|null), suggested_stop_loss(number|null),"
            " suggested_take_profit(number|null), risk_note。"
            "如果新闻证据不足，credibility_label 必须是 待核实 或 高风险谣言，trade_bias 必须偏 neutral。"
        )

        payload = prepare_chat_payload({
            "model": self.model,
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(prompt_payload, ensure_ascii=False)},
            ],
        }, self.base_url, self.model)

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

        parsed = self._parse_json_content(content)
        if not parsed:
            return None

        normalized = self._normalize_result(parsed, anomaly, news_items)
        normalized["llm_payload"] = data
        return normalized

    def _heuristic_analysis(self, anomaly: Dict[str, Any], news_items: List[MarketNews]) -> Dict[str, Any]:
        last_price = float(anomaly.get("last_price") or 0)
        anomaly_score = float(anomaly.get("anomaly_score") or 0)
        price_change_percent = float(anomaly.get("price_change_percent_24h") or 0)
        funding_rate = anomaly.get("funding_rate")
        long_short_ratio = anomaly.get("long_short_ratio")

        domains = []
        trusted_hits = 0
        for item in news_items:
            domain = (item.source_domain or item.source or "").lower()
            domains.append(domain)
            if domain in self.TRUSTED_DOMAINS:
                trusted_hits += 1

        distinct_domains = sorted({domain for domain in domains if domain})
        source_summary = ", ".join(distinct_domains[:3]) if distinct_domains else "无可靠来源"

        if not news_items:
            credibility_label = "待核实"
            credibility_score = 35.0
            evidence_summary = "未检索到可交叉验证的新闻，当前更像纯资金驱动或短时情绪波动。"
        elif trusted_hits >= 2:
            credibility_label = "可信"
            credibility_score = 82.0 + min(10.0, (len(distinct_domains) - 2) * 4.0)
            evidence_summary = "存在多家主流来源交叉验证，消息可信度较高，但仍需结合盘口与波动控制仓位。"
        elif trusted_hits == 1 or len(distinct_domains) >= 2:
            credibility_label = "待核实"
            credibility_score = 60.0
            evidence_summary = "检测到有限来源或单一主流来源，建议等待更多官方或二次来源确认。"
        else:
            credibility_label = "高风险谣言"
            credibility_score = 22.0
            evidence_summary = "来源集中且缺少可信域名交叉验证，高概率为谣言、旧闻重炒或二次传播。"

        trade_bias = "neutral"
        trade_recommendation = "建议观望，等待更多来源确认后再决策。"
        trade_confidence = max(20.0, round(anomaly_score * credibility_score, 2))

        if credibility_label == "可信":
            if price_change_percent >= 5:
                trade_bias = "long"
                trade_recommendation = "若价格回踩关键支撑且量能未明显衰减，可考虑轻仓顺势做多。"
            elif price_change_percent <= -5:
                trade_bias = "short"
                trade_recommendation = "若反弹无力且消息偏负面，可考虑轻仓顺势做空。"
            else:
                trade_recommendation = "消息可信但价格未形成扩散，优先等待方向确认。"
            trade_confidence = round(min(92.0, anomaly_score * credibility_score + 18.0), 2)
        elif credibility_label == "高风险谣言":
            trade_recommendation = "不建议追涨杀跌，优先等待官方公告或多源确认。"
            trade_confidence = round(min(55.0, anomaly_score * 45.0), 2)

        levels = self._build_trade_levels(last_price, trade_bias)
        risk_note = self._build_risk_note(credibility_label, funding_rate, long_short_ratio)

        return {
            "credibility_label": credibility_label,
            "credibility_score": round(credibility_score, 2),
            "evidence_summary": evidence_summary,
            "source_summary": source_summary,
            "trade_bias": trade_bias,
            "trade_confidence": round(trade_confidence, 2),
            "trade_recommendation": trade_recommendation,
            "suggested_entry": levels["entry"],
            "suggested_stop_loss": levels["stop_loss"],
            "suggested_take_profit": levels["take_profit"],
            "risk_note": risk_note,
            "llm_payload": None,
        }

    def _normalize_result(
        self,
        result: Dict[str, Any],
        anomaly: Dict[str, Any],
        news_items: List[MarketNews],
    ) -> Dict[str, Any]:
        credibility_label = str(result.get("credibility_label") or "待核实").strip()
        if credibility_label not in {"可信", "待核实", "高风险谣言"}:
            credibility_label = {
                "trusted": "可信",
                "verify": "待核实",
                "caution": "待核实",
                "fake": "高风险谣言",
            }.get(credibility_label.lower(), "待核实")

        trade_bias = str(result.get("trade_bias") or "neutral").lower().strip()
        if trade_bias not in {"long", "short", "neutral"}:
            trade_bias = {
                "buy": "long",
                "bullish": "long",
                "sell": "short",
                "bearish": "short",
                "watch": "neutral",
            }.get(trade_bias, "neutral")

        source_summary = result.get("source_summary")
        if not source_summary:
            source_summary = ", ".join(
                sorted({(item.source_domain or item.source) for item in news_items if (item.source_domain or item.source)})[:3]
            ) or "无可靠来源"

        levels = self._build_trade_levels(float(anomaly.get("last_price") or 0), trade_bias)

        return {
            "credibility_label": credibility_label,
            "credibility_score": self._safe_float(result.get("credibility_score"), default=55.0),
            "evidence_summary": str(result.get("evidence_summary") or "模型未返回足够证据摘要。"),
            "source_summary": source_summary,
            "trade_bias": trade_bias,
            "trade_confidence": self._safe_float(result.get("trade_confidence"), default=50.0),
            "trade_recommendation": str(result.get("trade_recommendation") or "建议等待更多信号确认。"),
            "suggested_entry": self._safe_float(result.get("suggested_entry"), default=levels["entry"]),
            "suggested_stop_loss": self._safe_float(result.get("suggested_stop_loss"), default=levels["stop_loss"]),
            "suggested_take_profit": self._safe_float(result.get("suggested_take_profit"), default=levels["take_profit"]),
            "risk_note": str(result.get("risk_note") or self._build_risk_note(
                credibility_label,
                anomaly.get("funding_rate"),
                anomaly.get("long_short_ratio"),
            )),
        }

    def _build_trade_levels(self, last_price: float, bias: str) -> Dict[str, Optional[float]]:
        if not last_price or bias == "neutral":
            return {"entry": None, "stop_loss": None, "take_profit": None}
        if bias == "long":
            return {
                "entry": round(last_price * 0.995, 6),
                "stop_loss": round(last_price * 0.97, 6),
                "take_profit": round(last_price * 1.06, 6),
            }
        return {
            "entry": round(last_price * 1.005, 6),
            "stop_loss": round(last_price * 1.03, 6),
            "take_profit": round(last_price * 0.94, 6),
        }

    def _build_risk_note(self, credibility_label: str, funding_rate: Any, long_short_ratio: Any) -> str:
        notes = []
        if credibility_label != "可信":
            notes.append("消息可信度不足，避免在高波动阶段追单。")
        if funding_rate is not None and abs(float(funding_rate)) >= 0.001:
            notes.append("资金费率偏离较大，存在拥挤交易和反向清算风险。")
        if long_short_ratio is not None:
            ratio = float(long_short_ratio)
            if ratio >= 1.8 or ratio <= 0.6:
                notes.append("多空比失衡，需提防挤仓。")
        if not notes:
            notes.append("建议控制单笔风险，不要把新闻结论当作单独开仓依据。")
        return " ".join(notes)

    def _parse_json_content(self, content: str) -> Optional[Dict[str, Any]]:
        parsed = parse_json_content(content)
        if parsed is None:
            logger.debug("news-analysis: failed to parse llm json: %s", content[:400])
        return parsed

    def _safe_float(self, value: Any, default: Optional[float] = None) -> Optional[float]:
        if value is None or value == "":
            return default
        try:
            return round(float(value), 6)
        except (TypeError, ValueError):
            return default


news_analysis_service = NewsAnalysisService()
