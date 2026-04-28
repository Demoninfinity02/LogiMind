from __future__ import annotations

import random
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from ..models import Location, TrafficCongestion, TrafficSnapshot


def _traffic_score(congestion: str) -> float:
    return {
        TrafficCongestion.LOW: 0.2,
        TrafficCongestion.MEDIUM: 0.5,
        TrafficCongestion.HIGH: 0.8,
    }.get(congestion, 0.2)


def get_or_simulate_traffic(location: Location, *, force: bool = False) -> TrafficSnapshot:
    """Create/update a traffic snapshot for a location.

    We keep this intentionally lightweight: for hackathon/demo, traffic is simulated
    (no external API) and cached with a TTL like weather.
    """

    now = timezone.now()
    ttl_seconds = int(getattr(settings, "TRAFFIC_CACHE_TTL_SECONDS", 180))
    ttl = timedelta(seconds=ttl_seconds)

    snapshot = TrafficSnapshot.objects.filter(location=location).first()
    if snapshot and not force and snapshot.expires_at and snapshot.expires_at > now:
        return snapshot

    # Simulate congestion with a mild bias toward low/medium.
    congestion = random.choices(
        population=[TrafficCongestion.LOW, TrafficCongestion.MEDIUM, TrafficCongestion.HIGH],
        weights=[0.5, 0.35, 0.15],
        k=1,
    )[0]
    score = _traffic_score(congestion)

    if snapshot is None:
        snapshot = TrafficSnapshot(location=location)

    snapshot.congestion = congestion
    snapshot.score = score
    snapshot.raw_json = {"simulated": True}
    snapshot.fetched_at = now
    snapshot.expires_at = now + ttl

    if snapshot.pk:
        snapshot.save(update_fields=["congestion", "score", "raw_json", "fetched_at", "expires_at", "updated_at"])
    else:
        snapshot.save()

    return snapshot
