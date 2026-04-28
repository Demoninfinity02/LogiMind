from __future__ import annotations

from collections import defaultdict
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import redirect, render
from django.utils import timezone

from .forms import ShipmentForm, SignUpForm
from .models import (
    Company,
    CostLevel,
    ExternalEvent,
    Location,
    Mode,
    RiskLevel,
    Shipment,
    ShipmentPriority,
    ShipmentStatus,
    TrafficSnapshot,
    UserRole,
    WeatherSnapshot,
    ensure_user_profile,
    user_company,
    user_role,
)
from .services.risk import compute_live_state


def signup(request):
    if request.user.is_authenticated:
        return redirect("dashboard")

    form = SignUpForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        return redirect("dashboard")
    return render(request, "registration/signup.html", {"form": form})


def _ensure_demo_shipments_for_demon(user) -> None:
    if not user.is_authenticated or user.username != "demon":
        return

    company, _ = Company.objects.get_or_create(name="Demon Logistics")
    profile = ensure_user_profile(user)
    changed = []
    if profile.company_id != company.id:
        profile.company = company
        changed.append("company")
    if profile.role != UserRole.EMPLOYEE:
        profile.role = UserRole.EMPLOYEE
        changed.append("role")
    if changed:
        profile.save(update_fields=changed)

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
        location_objs[name] = loc

    baseline = [
        ("SH0001", "Mumbai", "Singapore", Mode.SEA, 48, ShipmentPriority.MEDIUM),
        ("SH0002", "Dubai", "Rotterdam", Mode.SEA, 72, ShipmentPriority.LOW),
        ("SH0003", "Los Angeles", "Dubai", Mode.AIR, 18, ShipmentPriority.LOW),
        ("SH0004", "Singapore", "Los Angeles", Mode.SEA, 96, ShipmentPriority.LOW),
        ("SH0005", "Rotterdam", "Mumbai", Mode.ROAD, 60, ShipmentPriority.LOW),
        ("SH0006", "Dubai", "Mumbai", Mode.ROAD, 12, ShipmentPriority.MEDIUM),
    ]
    for ref, origin_name, destination_name, mode, hours, priority in baseline:
        base_eta = now + timedelta(hours=hours)
        cost_level = {
            Mode.SEA: CostLevel.LOW,
            Mode.ROAD: CostLevel.MEDIUM,
            Mode.AIR: CostLevel.HIGH,
        }.get(mode, CostLevel.MEDIUM)
        shipment, created = Shipment.objects.get_or_create(
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
        if not created:
            shipment.created_by = user
            shipment.company = company
            shipment.priority = priority
            shipment.save(update_fields=["created_by", "company", "priority", "updated_at"])


def _shipments_for_user(request):
    role = user_role(request.user)
    company = user_company(request.user)
    qs = Shipment.objects.select_related("origin", "destination", "company", "created_by")
    if role == UserRole.ADMIN:
        return qs
    if role == UserRole.EMPLOYEE:
        return qs.filter(company=company) if company else qs.none()
    return qs.filter(created_by=request.user)


@login_required
def dashboard(request):
    _ensure_demo_shipments_for_demon(request.user)
    return render(
        request,
        "tower/dashboard.html",
        {
            "poll_seconds": settings.LIVE_UPDATES_POLL_SECONDS,
            "shipment_form": ShipmentForm(),
        },
    )


@login_required
def create_shipment(request):
    role = user_role(request.user)
    if role not in {UserRole.EMPLOYEE, UserRole.ADMIN, UserRole.CUSTOMER}:
        return HttpResponseForbidden("You are not allowed to create shipments.")

    if request.method == "POST":
        form = ShipmentForm(request.POST)
        if form.is_valid():
            shipment = form.save(commit=False)
            shipment.created_by = request.user
            shipment.company = user_company(request.user)
            shipment.eta = shipment.base_eta
            shipment.delay_minutes = 0
            shipment.save()
            return redirect("dashboard")
        # Form invalid — re-render dashboard with validation errors visible.
        _ensure_demo_shipments_for_demon(request.user)
        return render(
            request,
            "tower/dashboard.html",
            {
                "poll_seconds": settings.LIVE_UPDATES_POLL_SECONDS,
                "shipment_form": form,
            },
        )
    return redirect("dashboard")


@login_required
def live_updates(request):
    _ensure_demo_shipments_for_demon(request.user)
    now = timezone.now()
    poll_seconds = settings.LIVE_UPDATES_POLL_SECONDS

    shipments = _shipments_for_user(request).order_by("created_at")[: settings.MAX_DASHBOARD_SHIPMENTS]

    location_ids: set[int] = set()
    for s in shipments:
        location_ids.add(s.origin_id)
        location_ids.add(s.destination_id)

    locations = list(Location.objects.filter(id__in=location_ids).order_by("name"))
    weather_by_location = {
        ws.location_id: ws
        for ws in WeatherSnapshot.objects.select_related("location").filter(location_id__in=location_ids)
    }

    traffic_by_location = {
        ts.location_id: ts
        for ts in TrafficSnapshot.objects.select_related("location").filter(location_id__in=location_ids)
    }

    active_events = list(
        ExternalEvent.objects.active()
        .filter(location_id__in=location_ids)
        .select_related("location")
        .order_by("-created_at")
    )
    events_by_location = defaultdict(list)
    for e in active_events:
        events_by_location[e.location_id].append(e)

    shipment_rows = []
    for s in shipments:
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
        shipment_rows.append(
            {
                "shipment": s,
                "live": live,
                "origin_weather": origin_weather,
                "origin_traffic": origin_traffic,
                "disruption_count": len(relevant_events),
            }
        )

    location_cards = []
    for loc in locations:
        ws = weather_by_location.get(loc.id)
        ts = traffic_by_location.get(loc.id)
        location_cards.append({"location": loc, "weather": ws, "traffic": ts})

    return render(
        request,
        "tower/partials/live_updates.html",
        {
            "now": now,
            "poll_seconds": poll_seconds,
            "shipment_rows": shipment_rows,
            "location_cards": location_cards,
            "active_events": active_events,
            "current_role": user_role(request.user),
        },
    )
