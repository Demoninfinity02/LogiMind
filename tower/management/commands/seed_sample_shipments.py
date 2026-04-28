from __future__ import annotations

import random
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from tower.models import (
    Company,
    CostLevel,
    Location,
    Mode,
    RiskLevel,
    Shipment,
    ShipmentPriority,
    ShipmentStatus,
    UserRole,
    ensure_user_profile,
)


class Command(BaseCommand):
    help = "Add realistic sample shipments without deleting existing data."

    def add_arguments(self, parser):
        parser.add_argument(
            "--username",
            type=str,
            default="demon",
            help="Username to assign seeded shipments to.",
        )
        parser.add_argument(
            "--count",
            type=int,
            default=10,
            help="Number of random demo shipments to generate.",
        )

    def handle(self, *args, **options):
        now = timezone.now()
        count = max(0, int(options.get("count") or 10))
        username = str(options.get("username") or "demon").strip()
        locations = [
            ("Shanghai", "CN", 31.2304, 121.4737),
            ("Hamburg", "DE", 53.5511, 9.9937),
            ("New York", "US", 40.7128, -74.0060),
            ("Singapore", "SG", 1.3521, 103.8198),
            ("Dubai", "AE", 25.2048, 55.2708),
            ("Rotterdam", "NL", 51.9244, 4.4777),
            ("Los Angeles", "US", 34.0522, -118.2437),
            ("Mumbai", "IN", 19.0760, 72.8777),
            ("Busan", "KR", 35.1796, 129.0756),
            ("Santos", "BR", -23.9608, -46.3336),
            ("Antwerp", "BE", 51.2194, 4.4025),
            ("Tokyo", "JP", 35.6762, 139.6503),
        ]

        location_objs: dict[str, Location] = {}
        for name, cc, lat, lon in locations:
            loc, _ = Location.objects.get_or_create(
                name=name,
                defaults={"country_code": cc, "latitude": lat, "longitude": lon},
            )
            location_objs[name] = loc

        user = None
        company = None
        if username:
            User = get_user_model()
            user = User.objects.filter(username=username).first()
            if user:
                company, _ = Company.objects.get_or_create(name="Demon Logistics")
                profile = ensure_user_profile(user)
                changed_profile_fields = []
                if profile.company_id != company.id:
                    profile.company = company
                    changed_profile_fields.append("company")
                if profile.role != UserRole.EMPLOYEE:
                    profile.role = UserRole.EMPLOYEE
                    changed_profile_fields.append("role")
                if changed_profile_fields:
                    profile.save(update_fields=changed_profile_fields)

        # Real-world style routes and transit times.
        samples = [
            ("MAEU-2026-001", "Shanghai", "Hamburg", Mode.SEA, 480, ShipmentPriority.HIGH),
            ("CMA-2026-114", "Singapore", "Rotterdam", Mode.SEA, 360, ShipmentPriority.MEDIUM),
            ("DHL-AIR-778", "Dubai", "New York", Mode.AIR, 18, ShipmentPriority.CRITICAL),
            ("UPS-ROAD-332", "Hamburg", "Rotterdam", Mode.ROAD, 10, ShipmentPriority.LOW),
        ]
        # Permanent base demo pack (stable references) used in the screenshots.
        samples.extend(
            [
                ("SH0001", "Mumbai", "Singapore", Mode.SEA, 48, ShipmentPriority.MEDIUM),
                ("SH0002", "Dubai", "Rotterdam", Mode.SEA, 72, ShipmentPriority.LOW),
                ("SH0003", "Los Angeles", "Dubai", Mode.AIR, 18, ShipmentPriority.LOW),
                ("SH0004", "Singapore", "Los Angeles", Mode.SEA, 96, ShipmentPriority.LOW),
                ("SH0005", "Rotterdam", "Mumbai", Mode.ROAD, 60, ShipmentPriority.LOW),
                ("SH0006", "Dubai", "Mumbai", Mode.ROAD, 12, ShipmentPriority.MEDIUM),
            ]
        )

        route_pool = [
            ("Shanghai", "Rotterdam", Mode.SEA, (420, 520)),
            ("Busan", "Los Angeles", Mode.SEA, (300, 420)),
            ("Santos", "Antwerp", Mode.SEA, (320, 460)),
            ("Singapore", "Hamburg", Mode.SEA, (360, 460)),
            ("Dubai", "Mumbai", Mode.AIR, (4, 8)),
            ("Tokyo", "Los Angeles", Mode.AIR, (10, 16)),
            ("Singapore", "New York", Mode.AIR, (16, 24)),
            ("Mumbai", "Dubai", Mode.AIR, (4, 8)),
            ("Antwerp", "Rotterdam", Mode.ROAD, (4, 10)),
            ("Hamburg", "Antwerp", Mode.ROAD, (8, 14)),
            ("Los Angeles", "New York", Mode.ROAD, (58, 84)),
            ("Rotterdam", "Hamburg", Mode.ROAD, (8, 16)),
        ]
        priorities = [
            ShipmentPriority.LOW,
            ShipmentPriority.MEDIUM,
            ShipmentPriority.MEDIUM,
            ShipmentPriority.HIGH,
            ShipmentPriority.CRITICAL,
        ]
        carriers = {
            Mode.SEA: ["MAEU", "MSC", "CMA", "HPL"],
            Mode.AIR: ["DHL", "FDX", "UPS", "EK"],
            Mode.ROAD: ["XPO", "DHLR", "UPSR", "DBS"],
        }
        year = now.year
        used_refs = set(Shipment.objects.values_list("reference", flat=True))
        for _ in range(count):
            origin_name, destination_name, mode, hour_range = random.choice(route_pool)
            if origin_name == destination_name:
                continue
            hours = random.randint(hour_range[0], hour_range[1])
            priority = random.choice(priorities)
            serial = random.randint(100, 999)
            carrier = random.choice(carriers[mode])
            ref = f"{carrier}-{year}-{serial}"
            while ref in used_refs:
                serial = random.randint(100, 999)
                ref = f"{carrier}-{year}-{serial}"
            used_refs.add(ref)
            samples.append((ref, origin_name, destination_name, mode, hours, priority))

        created = 0
        for ref, origin_name, destination_name, mode, hours, priority in samples:
            base_eta = now + timedelta(hours=hours)
            cost_level = {
                Mode.SEA: CostLevel.LOW,
                Mode.ROAD: CostLevel.MEDIUM,
                Mode.AIR: CostLevel.HIGH,
            }.get(mode, CostLevel.MEDIUM)
            shipment, was_created = Shipment.objects.get_or_create(
                reference=ref,
                defaults={
                    "origin": location_objs[origin_name],
                    "destination": location_objs[destination_name],
                    "created_by": user,
                    "company": company,
                    "mode": mode,
                    "priority": priority,
                    "status": ShipmentStatus.IN_TRANSIT,
                    "base_eta": base_eta,
                    "base_transit_hours": float(hours),
                    "cost_level": cost_level,
                    "budget_usd": 5000 if mode != Mode.AIR else 12000,
                    "expected_profit_usd": 3500 if mode != Mode.AIR else 9000,
                    "eta": base_eta,
                    "delay_minutes": 0,
                    "risk_level": RiskLevel.LOW,
                    "risk_score": 0,
                    "risk_value": 0.0,
                    "recommendation": "",
                },
            )
            if was_created:
                created += 1
            else:
                shipment.created_by = user
                shipment.company = company
                shipment.priority = priority
                shipment.save(update_fields=["created_by", "company", "priority", "updated_at"])

        if username and not user:
            self.stdout.write(
                self.style.WARNING(
                    f"User '{username}' not found. Shipments were seeded but not assigned to a user/company."
                )
            )
        self.stdout.write(
            self.style.SUCCESS(
                f"Sample shipments ready for '{username}'. Added {created} new shipment(s)."
            )
        )
