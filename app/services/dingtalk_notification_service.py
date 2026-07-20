import base64
import hashlib
import hmac
import time
from typing import Optional
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import httpx


class DingTalkNotificationService:
    @staticmethod
    def validate_webhook_url(webhook_url: str) -> str:
        normalized = str(webhook_url or "").strip()
        parsed = urlparse(normalized)
        hostname = (parsed.hostname or "").lower()
        if parsed.scheme != "https" or not hostname.endswith("dingtalk.com"):
            raise ValueError("钉钉 Webhook 必须使用 dingtalk.com 的 HTTPS 地址")
        if "/robot/send" not in parsed.path:
            raise ValueError("请输入钉钉自定义机器人 Webhook 地址")
        return normalized

    @staticmethod
    def _signed_url(webhook_url: str, secret: Optional[str]) -> str:
        if not secret:
            return webhook_url
        timestamp = str(int(time.time() * 1000))
        string_to_sign = f"{timestamp}\n{secret}"
        digest = hmac.new(
            secret.encode("utf-8"),
            string_to_sign.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).digest()
        sign = base64.b64encode(digest).decode("utf-8")
        parsed = urlparse(webhook_url)
        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        query.update({"timestamp": timestamp, "sign": sign})
        return urlunparse(parsed._replace(query=urlencode(query)))

    async def send_text(self, webhook_url: str, content: str, secret: Optional[str] = None) -> None:
        validated_url = self.validate_webhook_url(webhook_url)
        url = self._signed_url(validated_url, str(secret or "").strip() or None)
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                response = await client.post(
                    url,
                    json={"msgtype": "text", "text": {"content": content}},
                )
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            # 不把包含 access_token 的完整请求 URL 暴露给前端或日志。
            raise RuntimeError("钉钉机器人请求失败，请检查网络与 Webhook") from exc
        if int(payload.get("errcode", -1)) != 0:
            raise RuntimeError(str(payload.get("errmsg") or "钉钉机器人返回失败"))


dingtalk_notification_service = DingTalkNotificationService()
