from __future__ import annotations

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from tower.models import (
    CostLevel,
    EventType,
    ExternalEvent,
    Location,
    Mode,
    RiskLevel,
    Severity,
    Shipment,
    ShipmentStatus,
    TrafficCongestion,
    TrafficSnapshot,
    WeatherCondition,
    WeatherSnapshot,
    WeatherSource,
)


class Command(BaseCommand):
    help = "Seed a small demo dataset (5–10 shipments, locations, baseline weather, optional disruptions)."

    def handle(self, *args, **options):
        now = timezone.now()

        locations = [
            ("Singapore", "SG", 1.3521, 103.8198),
            ("Rotterdam", "NL", 51.9244, 4.4777),
            ("Los Angeles", "US", 34.0522, -118.2437),
            ("Mumbai", "IN", 19.0760, 72.8777),
            ("Dubai", "AE", 25.2048, 55.2708),
        ]

        location_objs = {}
        for name, cc, lat, lon in locations:
            loc, _ = Location.objects.get_or_create(
                name=name,
                defaults={"country_code": cc, "latitude": lat, "longitude": lon},
            )
            # Keep coordinates updated if the row existed
            if loc.latitude != lat or loc.longitude != lon or loc.country_code != cc:
                loc.latitude = lat
                loc.longitude = lon
                loc.country_code = cc
                loc.save(update_fields=["latitude", "longitude", "country_code", "updated_at"])
            location_objs[name] = loc

            WeatherSnapshot.objects.update_or_create(
                location=loc,
                defaults={
                    "source": WeatherSource.OPEN_METEO,
                    "condition": WeatherCondition.CLEAR,
                    "risk_level": RiskLevel.LOW,
                    "temperature_c": None,
                    "raw_json": None,
                    "fetched_at": now,
                    "expires_at": now + timedelta(minutes=1),
                },
            )

            TrafficSnapshot.objects.update_or_create(
                location=loc,
                defaults={
                    "congestion": TrafficCongestion.LOW,
                    "score": 0.2,
                    "raw_json": {"seed": True},
                    "fetched_at": now,
                    "expires_at": now + timedelta(minutes=1),
                },
            )

        Shipment.objects.all().delete()
        ExternalEvent.objects.all().delete()

        shipments_seed = [
            ("SH0001", "Mumbai", "Singapore", Mode.SEA, 48),
            ("SH0002", "Dubai", "Rotterdam", Mode.SEA, 72),
            ("SH0003", "Los Angeles", "Dubai", Mode.AIR, 18),
            ("SH0004", "Singapore", "Los Angeles", Mode.SEA, 96),
            ("SH0005", "Rotterdam", "Mumbai", Mode.ROAD, 60),
            ("SH0006", "Dubai", "Mumbai", Mode.ROAD, 12),
        ]

        for ref, origin_name, dest_name, mode, hours in shipments_seed:
            base_eta = now + timedelta(hours=hours)
            cost_level = {
                Mode.SEA: CostLevel.LOW,
                Mode.ROAD: CostLevel.MEDIUM,
                Mode.AIR: CostLevel.HIGH,
            }.get(mode, CostLevel.MEDIUM)

            # Simple financials for the demo (USD). Budgets/profits vary so you can see
            # route changes get blocked when the economics don't work.
            daily_cost = {
                Mode.SEA: 800,
                Mode.ROAD: 1200,
                Mode.AIR: 2500,
            }.get(mode, 1200)
            est_cost = int(round(daily_cost * (float(hours) / 24.0)))

            # Budget: tied to cost level; Profit: tied to budget with some variation.
            budget = {
                CostLevel.LOW: max(1500, int(est_cost * 1.1)),
                CostLevel.MEDIUM: max(2500, int(est_cost * 1.2)),
                CostLevel.HIGH: max(6000, int(est_cost * 1.3)),
            }[cost_level]

            profit = {
                "SH0001": int(budget * 0.20),
                "SH0002": int(budget * 0.15),
                "SH0003": int(budget * 0.60),
                "SH0004": int(budget * 0.10),
                "SH0005": int(budget * 0.25),
                "SH0006": int(budget * 0.40),
            }.get(ref, int(budget * 0.25))
            Shipment.objects.create(
                reference=ref,
                origin=location_objs[origin_name],
                destination=location_objs[dest_name],
                mode=mode,
                status=ShipmentStatus.IN_TRANSIT,
                base_eta=base_eta,
                base_transit_hours=float(hours),
                cost_level=cost_level,
                budget_usd=budget,
                expected_profit_usd=profit,
                eta=base_eta,
                delay_minutes=0,
                risk_level=RiskLevel.LOW,
                risk_score=0,
                risk_value=0.0,
                recommendation="",
            )

        # Seed one inactive disruption so it can be activated in /admin during the demo
        ExternalEvent.objects.create(
            event_type=EventType.GEOPOLITICAL,
            location=location_objs["Dubai"],
            severity=Severity.HIGH,
            description="Demo: activate to simulate geopolitical disruption",
            active=False,
            starts_at=now,
        )

        self.stdout.write(self.style.SUCCESS("Seeded demo locations, shipments, weather baseline, and one inactive event."))
