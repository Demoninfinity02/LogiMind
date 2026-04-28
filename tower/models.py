from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone


class RiskLevel(models.TextChoices):
    LOW = "low", "Low"
    MEDIUM = "medium", "Medium"
    HIGH = "high", "High"


class WeatherCondition(models.TextChoices):
    CLEAR = "clear", "Clear"
    RAIN = "rain", "Rain"
    STORM = "storm", "Storm"
    FOG = "fog", "Fog"
    UNKNOWN = "unknown", "Unknown"


class WeatherSource(models.TextChoices):
    OPENWEATHER = "openweather", "OpenWeatherMap"
    OPEN_METEO = "open_meteo", "Open-Meteo"


class EventType(models.TextChoices):
    GEOPOLITICAL = "geopolitical", "Geopolitical"
    CONGESTION = "congestion", "Congestion"
    STRIKE = "strike", "Strike"


class Severity(models.TextChoices):
    LOW = "low", "Low"
    MEDIUM = "medium", "Medium"
    HIGH = "high", "High"


class CostLevel(models.TextChoices):
    LOW = "low", "Low"
    MEDIUM = "medium", "Medium"
    HIGH = "high", "High"


class TrafficCongestion(models.TextChoices):
    LOW = "low", "Low"
    MEDIUM = "medium", "Medium"
    HIGH = "high", "High"
    UNKNOWN = "unknown", "Unknown"


class Mode(models.TextChoices):
    SEA = "sea", "Sea"
    AIR = "air", "Air"
    ROAD = "road", "Road"


class ShipmentStatus(models.TextChoices):
    IN_TRANSIT = "in_transit", "In transit"
    DELAYED = "delayed", "Delayed"
    DELIVERED = "delivered", "Delivered"


class UserRole(models.TextChoices):
    CUSTOMER = "customer", "Customer"
    EMPLOYEE = "employee", "Employee"
    ADMIN = "admin", "Admin"


class ShipmentPriority(models.TextChoices):
    LOW = "low", "Low"
    MEDIUM = "medium", "Medium"
    HIGH = "high", "High"
    CRITICAL = "critical", "Critical"


class Location(models.Model):
    name = models.CharField(max_length=120, unique=True)
    country_code = models.CharField(max_length=2, blank=True)
    latitude = models.FloatField()
    longitude = models.FloatField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return self.name


class WeatherSnapshot(models.Model):
    location = models.OneToOneField(Location, on_delete=models.CASCADE, related_name="weather")
    source = models.CharField(max_length=20, choices=WeatherSource.choices)
    condition = models.CharField(max_length=20, choices=WeatherCondition.choices)
    risk_level = models.CharField(max_length=10, choices=RiskLevel.choices)
    temperature_c = models.FloatField(null=True, blank=True)
    raw_json = models.JSONField(null=True, blank=True)
    fetched_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def is_fresh(self) -> bool:
        if not self.expires_at:
            return False
        return self.expires_at > timezone.now()

    def __str__(self) -> str:
        return f"{self.location.name} ({self.get_condition_display()})"


class TrafficSnapshot(models.Model):
    location = models.OneToOneField(Location, on_delete=models.CASCADE, related_name="traffic")
    congestion = models.CharField(max_length=20, choices=TrafficCongestion.choices)
    score = models.FloatField(default=0.2)
    raw_json = models.JSONField(null=True, blank=True)
    fetched_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def is_fresh(self) -> bool:
        if not self.expires_at:
            return False
        return self.expires_at > timezone.now()

    def __str__(self) -> str:
        return f"{self.location.name} ({self.get_congestion_display()})"


class ExternalEventQuerySet(models.QuerySet):
    def active(self) -> "ExternalEventQuerySet":
        now = timezone.now()
        return (
            self.filter(active=True)
            .filter(starts_at__lte=now)
            .filter(models.Q(ends_at__isnull=True) | models.Q(ends_at__gte=now))
        )


class ExternalEvent(models.Model):
    event_type = models.CharField(max_length=20, choices=EventType.choices)
    location = models.ForeignKey(Location, on_delete=models.CASCADE, related_name="external_events")
    severity = models.CharField(max_length=10, choices=Severity.choices)
    description = models.CharField(max_length=255, blank=True)
    active = models.BooleanField(default=True)
    starts_at = models.DateTimeField(default=timezone.now)
    ends_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = ExternalEventQuerySet.as_manager()

    def __str__(self) -> str:
        return f"{self.get_event_type_display()} @ {self.location.name} ({self.get_severity_display()})"


class Shipment(models.Model):
    reference = models.CharField(max_length=40, unique=True)
    origin = models.ForeignKey(Location, on_delete=models.PROTECT, related_name="origin_shipments")
    destination = models.ForeignKey(Location, on_delete=models.PROTECT, related_name="destination_shipments")
    mode = models.CharField(max_length=10, choices=Mode.choices)
    status = models.CharField(max_length=20, choices=ShipmentStatus.choices, default=ShipmentStatus.IN_TRANSIT)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="shipments_created",
    )
    company = models.ForeignKey(
        "Company",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="shipments",
    )
    priority = models.CharField(max_length=20, choices=ShipmentPriority.choices, default=ShipmentPriority.MEDIUM)

    # Baseline route data
    base_eta = models.DateTimeField()
    base_transit_hours = models.FloatField(default=24.0)
    cost_level = models.CharField(max_length=10, choices=CostLevel.choices, default=CostLevel.MEDIUM)

    # Financial constraints (demo): budget cap and profit headroom.
    budget_usd = models.PositiveIntegerField(default=2500)
    expected_profit_usd = models.PositiveIntegerField(default=2000)

    eta = models.DateTimeField()
    delay_minutes = models.PositiveIntegerField(default=0)

    risk_level = models.CharField(max_length=10, choices=RiskLevel.choices, default=RiskLevel.LOW)
    risk_score = models.PositiveIntegerField(default=0)
    risk_value = models.FloatField(default=0.0)
    recommendation = models.TextField(blank=True)
    ai_explanation = models.TextField(null=True, blank=True)
    ai_explained_at = models.DateTimeField(null=True, blank=True)

    last_risk_recalc_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return self.reference


class Company(models.Model):
    name = models.CharField(max_length=120, unique=True)

    def __str__(self) -> str:
        return self.name


class UserProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    role = models.CharField(max_length=20, choices=UserRole.choices, default=UserRole.CUSTOMER)
    company = models.ForeignKey(
        Company,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="users",
    )

    def __str__(self) -> str:
        return f"{self.user} ({self.get_role_display()})"


def ensure_user_profile(user):
    profile = getattr(user, "profile", None)
    if profile:
        return profile
    return UserProfile.objects.create(user=user)


def user_role(user) -> str:
    if not user or not user.is_authenticated:
        return UserRole.CUSTOMER
    return ensure_user_profile(user).role


def user_company(user):
    if not user or not user.is_authenticated:
        return None
    return ensure_user_profile(user).company
