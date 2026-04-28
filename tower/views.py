from __future__ import annotations

from collections import defaultdict

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import redirect, render
from django.utils import timezone

from .forms import ShipmentForm
from .models import ExternalEvent, Location, Shipment, TrafficSnapshot, UserRole, WeatherSnapshot, user_company, user_role
from .services.risk import compute_live_state


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


@login_required
def live_updates(request):
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
