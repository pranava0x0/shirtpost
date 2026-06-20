"""Lightweight trend-scoring model.

    Hype Score = velocity of mentions * volume

Velocity is mentions gained per hour since the previous observation. A brand-new
trend (no prior observation) bootstraps its velocity to the current volume so a
fresh spike still surfaces instead of scoring zero on first sight.
"""

from __future__ import annotations

from datetime import datetime


def compute_velocity(
    prev_volume: int, current_volume: int, prev_seen: datetime, now: datetime
) -> float:
    """Mentions gained per hour. Both datetimes are naive UTC."""
    elapsed_hours = (now - prev_seen).total_seconds() / 3600.0
    if elapsed_hours <= 0:
        # First sight (or same-instant re-observation): bootstrap to volume.
        return float(current_volume)
    delta = max(current_volume - prev_volume, 0)
    return delta / elapsed_hours


def hype_score(velocity: float, volume: int) -> float:
    return round(velocity * float(volume), 4)
