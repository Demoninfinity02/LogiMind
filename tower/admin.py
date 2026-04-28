from django.contrib import admin

from .models import Company, ExternalEvent, Location, Shipment, TrafficSnapshot, UserProfile, WeatherSnapshot


@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = ("name", "country_code", "latitude", "longitude", "updated_at")
    search_fields = ("name", "country_code")


@admin.register(WeatherSnapshot)
class WeatherSnapshotAdmin(admin.ModelAdmin):
    list_display = ("location", "source", "condition", "risk_level", "temperature_c", "fetched_at", "expires_at")
    list_filter = ("source", "condition", "risk_level")
    search_fields = ("location__name",)


@admin.register(TrafficSnapshot)
class TrafficSnapshotAdmin(admin.ModelAdmin):
    list_display = ("location", "congestion", "score", "fetched_at", "expires_at")
    list_filter = ("congestion",)
    search_fields = ("location__name",)


@admin.register(ExternalEvent)
class ExternalEventAdmin(admin.ModelAdmin):
    list_display = ("event_type", "location", "severity", "active", "starts_at", "ends_at")
    list_filter = ("event_type", "severity", "active")
    search_fields = ("location__name", "description")


@admin.register(Shipment)
class ShipmentAdmin(admin.ModelAdmin):
    list_display = (
        "reference",
        "origin",
        "destination",
        "mode",
        "priority",
        "company",
        "created_by",
        "cost_level",
        "budget_usd",
        "expected_profit_usd",
        "status",
        "risk_level",
        "risk_score",
        "delay_minutes",
        "eta",
        "updated_at",
    )
    list_filter = ("mode", "status", "risk_level")
    search_fields = ("reference", "origin__name", "destination__name")


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "company")
    list_filter = ("role", "company")
    search_fields = ("user__username", "user__email", "company__name")
