from app.services.narrative_detector import NarrativeDetector


def test_narrative_detector_is_disabled_by_default_even_with_api_key(monkeypatch):
    monkeypatch.delenv("ANOMALY_LLM_PROVIDER", raising=False)
    monkeypatch.setenv("LLM_API_KEY", "test-key")

    detector = NarrativeDetector()

    assert detector.provider == detector.PROVIDER_DISABLED
    assert detector.enabled is False


def test_narrative_detector_requires_explicit_openai_compatible_provider(monkeypatch):
    monkeypatch.setenv("ANOMALY_LLM_PROVIDER", "openai-compatible")
    monkeypatch.setenv("LLM_API_KEY", "test-key")

    detector = NarrativeDetector()

    assert detector.provider == detector.PROVIDER_OPENAI_COMPATIBLE
    assert detector.enabled is True


def test_narrative_detector_rejects_legacy_auto_provider(monkeypatch):
    monkeypatch.setenv("ANOMALY_LLM_PROVIDER", "auto")
    monkeypatch.setenv("LLM_API_KEY", "test-key")

    detector = NarrativeDetector()

    assert detector.provider == detector.PROVIDER_DISABLED
    assert detector.enabled is False
