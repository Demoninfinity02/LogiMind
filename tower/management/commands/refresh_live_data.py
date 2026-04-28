from __future__ import annotations

import time
from collections import defaultdict

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from tower.models import ExternalEvent, Location, Shipment, TrafficSnapshot, WeatherSnapshot
from tower.services.risk import compute_live_state
from tower.services.traffic import get_or_simulate_traffic
from tower.services.weather import get_or_fetch_weather


class Command(BaseCommand):
    help = "Fetch weather snapshots and update shipment risk/ETA (cron-friendly; no Celery)."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true", help="Run one refresh cycle and exit.")
        parser.add_argument("--loop", action="store_true", help="Run continuously (useful for local demo).")
        parser.add_argument(
            "--interval",
            type=int,
            default=180,
            help="Loop interval in seconds (only used with --loop).",
        )
        parser.add_argument(
            "--force-weather",
            action="store_true",
            help="Bypass weather TTL and fetch immediately.",
        )

    def handle(self, *args, **options):
        run_once = options.get("once")
        loop = options.get("loop")
        interval = options.get("interval")
        force_weather = options.get("force_weather")

        if not run_once and not loop:
            run_once = True

        try:
            while True:
                self._refresh(force_weather=force_weather)
                if run_once:
                    return
                time.sleep(interval)
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING("Stopped refresh loop."))
            return

    def _refresh(self, *, force_weather: bool) -> None:
        now = timezone.now()
        shipments = (
            Shipment.objects.select_related("origin", "destination")
            .order_by("created_at")[: settings.MAX_DASHBOARD_SHIPMENTS]
        )

        location_ids: set[int] = set()
        for s in shipments:
            location_ids.add(s.origin_id)
            location_ids.add(s.destination_id)

        locations = list(Location.objects.filter(id__in=location_ids))
        for loc in locations:
            get_or_fetch_weather(loc, force=force_weather)
            get_or_simulate_traffic(loc, force=False)

        weather_by_location = {
            ws.location_id: ws
            for ws in WeatherSnapshot.objects.filter(location_id__in=location_ids)
        }

        traffic_by_location = {
            ts.location_id: ts
            for ts in TrafficSnapshot.objects.filter(location_id__in=location_ids)
        }

        active_events = list(ExternalEvent.objects.active().filter(location_id__in=location_ids))
        events_by_location = defaultdict(list)
        for e in active_events:
            events_by_location[e.location_id].append(e)

        updated = 0
        with transaction.atomic():
            for s in shipments:
                old_risk_score = s.risk_score
                old_delay_minutes = s.delay_minutes
                relevant_events = events_by_location.get(s.origin_id, []) + events_by_location.get(s.destination_id, [])
                origin_weather = weather_by_location.get(s.origin_id)
                origin_traffic = traffic_by_location.get(s.origin_id)
                live = compute_live_state(
                    shipment=s,
                    weather=origin_weather,
                    traffic=origin_traffic,
                    active_events=relevant_events,
                    now=now,
                )

                changed_fields = []
                if s.status != live.status:
                    s.status = live.status
                    changed_fields.append("status")
                if s.risk_level != live.risk_level:
                    s.risk_level = live.risk_level
                    changed_fields.append("risk_level")
                if s.risk_score != live.risk_score:
                    s.risk_score = live.risk_score
                    changed_fields.append("risk_score")
                if abs((s.risk_value or 0.0) - live.risk_value) > 1e-6:
                    s.risk_value = live.risk_value
                    changed_fields.append("risk_value")
                if s.delay_minutes != live.delay_minutes:
                    s.delay_minutes = live.delay_minutes
                    changed_fields.append("delay_minutes")
                if s.eta != live.eta:
                    s.eta = live.eta
                    changed_fields.append("eta")

                # Recompute recommendations when risk increases or delay crosses threshold
                delay_threshold = 30
                if (
                    live.risk_score > old_risk_score
                    or (old_delay_minutes < delay_threshold <= live.delay_minutes)
                    or s.recommendation != live.recommendation
                ):
                    s.recommendation = live.recommendation
                    changed_fields.append("recommendation")

                if changed_fields:
                    s.last_risk_recalc_at = now
                    changed_fields.append("last_risk_recalc_at")
                    changed_fields.append("updated_at")
                    s.save(update_fields=changed_fields)
                    updated += 1

        self.stdout.write(f"Refreshed at {now.isoformat()} — updated {updated} shipments")
