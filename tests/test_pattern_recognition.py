from app.services.pattern_recognition import ChartPatternAnalyzer


def test_hammer_requires_longer_lower_shadow_when_tolerance_increases():
    analyzer = ChartPatternAnalyzer()

    assert analyzer.is_hammer(100.0, 101.05, 97.0, 101.0, tolerance=0.2) is True
    assert analyzer.is_hammer(100.0, 101.05, 97.0, 101.0, tolerance=0.45) is False


def test_analyze_only_marks_engulfing_when_previous_candle_is_opposite_direction():
    analyzer = ChartPatternAnalyzer()
    klines = [
        [1710000000000, '100', '103', '99.5', '102', '1', 0, 0, 0, 0, 0, 0],
        [1710003600000, '99.5', '104', '99', '103.5', '1', 0, 0, 0, 0, 0, 0],
    ]

    patterns = analyzer.analyze(klines, tolerance=0.35)

    assert all('Engulfing' not in pattern.name for pattern in patterns)


def test_analyze_detects_hammer_with_stricter_valid_shape():
    analyzer = ChartPatternAnalyzer()
    klines = [
        [1710000000000, '103', '104', '101.5', '102.5', '1', 0, 0, 0, 0, 0, 0],
        [1710003600000, '100', '100.85', '96.9', '100.8', '1', 0, 0, 0, 0, 0, 0],
    ]

    patterns = analyzer.analyze(klines, tolerance=0.45)

    assert any(pattern.name.startswith('Hammer') for pattern in patterns)