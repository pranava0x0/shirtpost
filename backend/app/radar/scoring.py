"""Lightweight trend-scoring model.

    Hype Score = volume * (1 + clamp(velocity / volume, 0, BOOST_CAP))

The spec defined this as ``velocity * volume``, but that is degenerate for a
polling radar: velocity is mentions-gained-per-hour, so any trend whose volume is
flat between sweeps scores zero, and the whole board collapses to 0 on the second
identical sweep (caught by running it). The refined model keeps **volume** as the
stable base — a big steady trend stays high — and treats **velocity** as a capped
multiplicative boost, so an accelerating trend ranks above a flat one of equal
size without a fast spike running away. Nothing ever collapses to zero.

Velocity is mentions gained per hour since the previous observation. A brand-new
trend (no prior observation) bootstraps its velocity to the current volume, which
lands as a clean ~2x first-sight boost.
"""

from __future__ import annotations

from datetime import datetime

# Max additional multiple a fast riser can add on top of its volume base.
HYPE_VELOCITY_BOOST_CAP = 2.0


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
    """Volume base with a capped velocity boost. A flat trend keeps its volume."""
    if volume <= 0:
        return 0.0
    boost = min(max(velocity / volume, 0.0), HYPE_VELOCITY_BOOST_CAP)
    return round(volume * (1.0 + boost), 4)
