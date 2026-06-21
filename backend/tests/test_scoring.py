from datetime import datetime, timedelta

from app.radar import scoring


def test_velocity_bootstraps_on_first_sight():
    now = datetime(2026, 6, 19, 12, 0, 0)
    # No elapsed time -> velocity bootstraps to current volume.
    assert scoring.compute_velocity(0, 500, now, now) == 500.0


def test_velocity_is_mentions_gained_per_hour():
    start = datetime(2026, 6, 19, 12, 0, 0)
    later = start + timedelta(hours=2)
    # gained 200 mentions over 2h -> 100/hour
    assert scoring.compute_velocity(100, 300, start, later) == 100.0


def test_velocity_never_negative():
    start = datetime(2026, 6, 19, 12, 0, 0)
    later = start + timedelta(hours=1)
    assert scoring.compute_velocity(300, 100, start, later) == 0.0


def test_steady_trend_keeps_volume_as_hype():
    # Regression: a flat trend (zero velocity) must NOT collapse to 0 — that was
    # the bug found by running the app and re-sweeping.
    assert scoring.hype_score(0.0, 50_000) == 50_000.0


def test_velocity_boosts_score_above_volume():
    # ratio 0.5 -> 1.5x the volume base
    assert scoring.hype_score(25_000.0, 50_000) == 75_000.0
    assert scoring.hype_score(25_000.0, 50_000) > 50_000.0


def test_velocity_boost_is_capped():
    capped = scoring.hype_score(10_000_000.0, 50_000)
    assert capped == 50_000.0 * (1.0 + scoring.HYPE_VELOCITY_BOOST_CAP)


def test_zero_volume_scores_zero():
    assert scoring.hype_score(123.0, 0) == 0.0
