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


def test_hype_score_is_velocity_times_volume():
    assert scoring.hype_score(100.0, 300) == 30000.0
    assert scoring.hype_score(0.0, 999) == 0.0
