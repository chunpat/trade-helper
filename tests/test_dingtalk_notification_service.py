from urllib.parse import parse_qs, urlparse

import pytest

from app.services.dingtalk_notification_service import DingTalkNotificationService


def test_validate_dingtalk_webhook_rejects_non_dingtalk_url():
    with pytest.raises(ValueError):
        DingTalkNotificationService.validate_webhook_url(
            "https://example.com/robot/send?access_token=secret"
        )


def test_signed_url_keeps_token_and_adds_signature(monkeypatch):
    monkeypatch.setattr("app.services.dingtalk_notification_service.time.time", lambda: 1700000000)
    url = DingTalkNotificationService._signed_url(
        "https://oapi.dingtalk.com/robot/send?access_token=test-token",
        "SEC-test",
    )
    query = parse_qs(urlparse(url).query)

    assert query["access_token"] == ["test-token"]
    assert query["timestamp"] == ["1700000000000"]
    assert query["sign"][0]
