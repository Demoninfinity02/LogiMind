from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from django.utils import timezone

from ..models import (
    CostLevel,
    ExternalEvent,
    Mode,
    RiskLevel,
    Severity,
    Shipment,
    ShipmentPriority,
    ShipmentStatus,
    TrafficSnapshot,
    WeatherCondition,
    WeatherSnapshot,
)


def _weather_score(condition: str) -> float:
    return {
        WeatherCondition.CLEAR: 0.1,
        WeatherCondition.RAIN: 0.4,
        WeatherCondition.STORM: 0.8,
        WeatherCondition.FOG: 0.6,
    }.get(condition, 0.1)


def _event_score(active_events: list[ExternalEvent]) -> float:
    if not active_events:
        return 0.0
    # Map: minor/major
    has_major = any(e.severity == Severity.HIGH for e in active_events)
    return 0.9 if has_major else 0.5


def _risk_by_mode(mode: str, *, w: float, t: float, e: float) -> float:
    if mode == Mode.ROAD:
        return 0.3 * w + 0.5 * t + 0.2 * e
    if mode == Mode.AIR:
        return 0.7 * w + 0.0 * t + 0.3 * e
    # SEA (and default)
    return 0.6 * w + 0.1 * t + 0.3 * e


def _cost_numeric(cost_level: str) -> float:
    return {
        CostLevel.LOW: 1.0,
        CostLevel.MEDIUM: 2.0,
        CostLevel.HIGH: 3.0,
    }.get(cost_level, 2.0)


def _cost_rank(cost_level: str) -> int:
    return {
        CostLevel.LOW: 1,
        CostLevel.MEDIUM: 2,
        CostLevel.HIGH: 3,
    }.get(cost_level, 2)


def _mode_cost_level(mode: str) -> str:
    # Mode cost constraint (relative cost): SEA < ROAD < AIR
    return {
        Mode.SEA: CostLevel.LOW,
        Mode.ROAD: CostLevel.MEDIUM,
        Mode.AIR: CostLevel.HIGH,
    }.get(mode, CostLevel.MEDIUM)


def _mode_cost_usd(mode: str, *, base_time_hours: float) -> int:
    # Very rough estimate (demo): cost/day by mode, scaled by duration.
    daily = {
        Mode.SEA: 800,
        Mode.ROAD: 1200,
        Mode.AIR: 2500,
    }.get(mode, 1200)
    return int(round(daily * (max(base_time_hours, 1.0) / 24.0)))


def _priority_weight(priority: str) -> float:
    return {
        ShipmentPriority.LOW: 0.0,
        ShipmentPriority.MEDIUM: 5.0,
        ShipmentPriority.HIGH: 10.0,
        ShipmentPriority.CRITICAL: 20.0,
    }.get(priority, 0.0)


def _default_cost_for_mode(mode: str) -> float:
    # Simple relative ordering for demo.
    return _cost_numeric(_mode_cost_level(mode))


def _time_for_mode(base_time_hours: float, mode: str) -> float:
    # Heuristic baselines to support the decision score formula.
    return {
        Mode.ROAD: base_time_hours * 1.0,
        Mode.SEA: base_time_hours * 1.5,
        Mode.AIR: base_time_hours * 0.6,
    }.get(mode, base_time_hours)


@dataclass(frozen=True)
class ShipmentLiveState:
    status: str
    status_label: str
    status_reason: str
    risk_level: str
    risk_label: str
    risk_score: int
    risk_value: float
    delay_minutes: int
    eta: datetime
    delay_reason: str
    recommendation: str
    weather_score: float
    traffic_score: float
    event_score: float
    weather_label: str
    traffic_label: str
    disruptions_summary: str


def _severity_rank(severity: str) -> int:
    return {
        Severity.HIGH: 3,
        Severity.MEDIUM: 2,
        Severity.LOW: 1,
    }.get(severity, 0)


def _event_example(active_events: list[ExternalEvent]) -> str:
    if not active_events:
        return ""
    # Pick the most severe event as an example.
    e = sorted(active_events, key=lambda x: (_severity_rank(x.severity), x.created_at), reverse=True)[0]
    return f"{e.get_event_type_display()} — {e.get_severity_display()} @ {e.location.name}"


def _disruptions_summary(active_events: list[ExternalEvent]) -> str:
    if not active_events:
        return "None"
    example = _event_example(active_events)
    if len(active_events) == 1:
        return example
    return f"{len(active_events)} active (e.g., {example})"


def _severity_penalty(severity: str) -> int:
    return {
        Severity.LOW: 10,
        Severity.MEDIUM: 20,
        Severity.HIGH: 35,
    }.get(severity, 10)


def _severity_delay(severity: str, *, low: int, medium: int, high: int) -> int:
    return {
        Severity.LOW: low,
        Severity.MEDIUM: medium,
        Severity.HIGH: high,
    }.get(severity, low)


def _risk_level_from_score(score: int) -> str:
    if score >= 60:
        return RiskLevel.HIGH
    if score >= 25:
        return RiskLevel.MEDIUM
    return RiskLevel.LOW


def _recommendation_for(
    *,
    current_mode: str,
    base_time_hours: float,
    w: float,
    t: float,
    e: float,
    current_risk: float,
    delay_minutes: int,
    cost_constraint_level: str,
    budget_usd: int,
    expected_profit_usd: int,
    priority: str,
) -> str:
    if current_risk < 0.33 and delay_minutes < 15:
        return ""

    budget_rank = _cost_rank(cost_constraint_level)
    budget_label = CostLevel(cost_constraint_level).label if cost_constraint_level in CostLevel.values else str(cost_constraint_level)

    # Scoring (reworked) with explicit constraint weights.
    # Score = ExpectedTimeHours + (α·Risk) + (β·Cost_kUSD) + (γ·OverBudget_kUSD) + (φ·Unprofitable_kUSD)
    # - OverBudget_kUSD = max(0, CostUSD - BudgetUSD) / 1000
    # - Unprofitable_kUSD = max(0, (CostUSD - CurrentCostUSD) - ExpectedProfitUSD) / 1000
    alpha = 10.0
    beta = 0.5
    gamma = 25.0
    phi = 25.0
    priority_weight = _priority_weight(priority)


    all_candidates = []
    allowed_candidates = []
    current_cost_usd = _mode_cost_usd(current_mode, base_time_hours=base_time_hours)
    for mode in (Mode.ROAD, Mode.AIR, Mode.SEA):
        mode_cost_level = _mode_cost_level(mode)

        time_h = _time_for_mode(base_time_hours, mode)

        # Reworked formulation:
        # - compute per-candidate risk using the same signals but mode-specific weights
        # - predict expected time = base time + (risk * base time)
        cand_risk = max(0.0, min(1.0, _risk_by_mode(mode, w=w, t=t, e=e)))
        expected_time_h = time_h + (cand_risk * time_h)
        cost_usd = _mode_cost_usd(mode, base_time_hours=base_time_hours)
        cost_kusd = cost_usd / 1000.0
        over_budget_kusd = max(0.0, (cost_usd - int(budget_usd)) / 1000.0)

        incremental_cost_usd = cost_usd - current_cost_usd
        unprofitable_kusd = max(0.0, (incremental_cost_usd - int(expected_profit_usd)) / 1000.0)

        score = (
            expected_time_h
            + (alpha * cand_risk)
            + (beta * cost_kusd)
            + (gamma * over_budget_kusd)
            + (phi * unprofitable_kusd)
            - priority_weight
        )

        row = (
            score,
            mode,
            expected_time_h,
            cand_risk,
            cost_usd,
            mode_cost_level,
            over_budget_kusd,
            unprofitable_kusd,
            incremental_cost_usd,
        )
        all_candidates.append(row)

        # Hard constraints for actual route-change suggestions:
        # - mode must fit cost constraint level
        # - absolute cost must be within budget
        # - if switching to a more expensive mode, profit must cover the extra cost
        within_level = _cost_rank(mode_cost_level) <= budget_rank
        within_budget = cost_usd <= int(budget_usd)
        profit_covers = (incremental_cost_usd <= 0) or (incremental_cost_usd <= int(expected_profit_usd))
        if within_level and within_budget and profit_covers:
            allowed_candidates.append(row)

    if not allowed_candidates:
        return f"Decision: no modes fit the cost constraint ({budget_label}); continue monitoring."

    all_candidates.sort(key=lambda x: x[0])
    allowed_candidates.sort(key=lambda x: x[0])
    best_overall = all_candidates[0]
    best_allowed = allowed_candidates[0]

    current_row = next((r for r in all_candidates if r[1] == current_mode), None)
    if not current_row:
        current_row = best_allowed

    (
        best_score,
        best_mode,
        best_expected_time_h,
        best_risk,
        best_cost_usd,
        best_cost_level,
        best_over_budget_kusd,
        best_unprofitable_kusd,
        best_incremental_cost_usd,
    ) = best_allowed
    best_cost_label = CostLevel(best_cost_level).label if best_cost_level in CostLevel.values else str(best_cost_level)

    (
        current_score,
        _current_mode,
        current_expected_time_h,
        _current_risk_for_mode,
        current_cost_usd,
        current_cost_level,
        current_over_budget_kusd,
        current_unprofitable_kusd,
        current_incremental_cost_usd,
    ) = current_row

    (
        overall_score,
        overall_mode,
        overall_expected_time_h,
        overall_risk,
        overall_cost_usd,
        overall_cost_level,
        overall_over_budget_kusd,
        overall_unprofitable_kusd,
        overall_incremental_cost_usd,
    ) = best_overall
    overall_cost_label = CostLevel(overall_cost_level).label if overall_cost_level in CostLevel.values else str(overall_cost_level)

    # Messaging: keep "risk" consistent with the Risk column; call out delay as "impact" instead.
    if current_risk >= 0.66:
        headline = "high risk"
    elif delay_minutes >= 6 * 60:
        headline = "high impact (large delay)"
    elif delay_minutes >= 60:
        headline = "impact (delay)"
    else:
        headline = ""
    if overall_mode != best_mode:
        # A better option exists but is blocked by the cost constraint.
        overall_mode_name = Mode(overall_mode).label
        if headline:
            return (
                f"Decision: {headline} — notify stakeholders and prepare contingency. "
                f"Note: {overall_mode_name} scores best (score {overall_score:.1f}) but route change is blocked by budget/profit. "
                f"(Budget ${int(budget_usd):,}; profit ${int(expected_profit_usd):,}; cost constraint {budget_label}.)"
            )
        return (
            f"Decision: {overall_mode_name} would be best (score {overall_score:.1f}) but is blocked by cost constraint "
            f"({budget_label}). Best allowed is {Mode(best_mode).label} (score {best_score:.1f})."
        )

    if best_mode != current_mode and (current_score - best_score) >= 2.0:
        return (
            f"Decision: switch to {Mode(best_mode).label} (score {best_score:.1f} vs {current_score:.1f}). "
            f"Expected time {best_expected_time_h:.1f}h; risk {best_risk:.2f}; "
            f"cost ${best_cost_usd:,} (constraint {best_cost_label}; budget ${int(budget_usd):,}; profit ${int(expected_profit_usd):,})."
        )

    if headline:
        return f"Decision: {headline} — monitor closely; prepare contingency if signals worsen."
    return "Decision: monitor — keep watching signals and be ready to switch mode if risk rises."


def compute_live_state(
    *,
    shipment: Shipment,
    weather: WeatherSnapshot | None,
    traffic: TrafficSnapshot | None,
    active_events: list[ExternalEvent],
    now: datetime | None = None,
) -> ShipmentLiveState:
    now = now or timezone.now()

    condition = weather.condition if weather else WeatherCondition.UNKNOWN
    w = _weather_score(condition)
    t = float((traffic.score if traffic else 0.2) or 0.2)
    e = _event_score(active_events)

    risk = max(0.0, min(1.0, _risk_by_mode(shipment.mode, w=w, t=t, e=e)))

    base_time_hours = float(shipment.base_transit_hours or 24.0)
    delay_hours = risk * base_time_hours
    delay_minutes = int(round(delay_hours * 60))

    # Displayable risk score as percentage 0..100
    risk_score = int(round(risk * 100))
    risk_level = RiskLevel.HIGH if risk >= 0.66 else (RiskLevel.MEDIUM if risk >= 0.33 else RiskLevel.LOW)

    eta = shipment.base_eta + timedelta(minutes=delay_minutes)

    # Only classify as "Delayed" for material predicted delays (keeps the UI meaningful).
    delayed_threshold_minutes = 6 * 60
    if shipment.status == ShipmentStatus.DELIVERED:
        status = ShipmentStatus.DELIVERED
    else:
        status = ShipmentStatus.DELAYED if delay_minutes >= delayed_threshold_minutes else ShipmentStatus.IN_TRANSIT

    recommendation = _recommendation_for(
        current_mode=shipment.mode,
        base_time_hours=base_time_hours,
        w=w,
        t=t,
        e=e,
        current_risk=risk,
        delay_minutes=delay_minutes,
        cost_constraint_level=shipment.cost_level,
        budget_usd=int(getattr(shipment, "budget_usd", 0) or 0),
        expected_profit_usd=int(getattr(shipment, "expected_profit_usd", 0) or 0),
        priority=getattr(shipment, "priority", ShipmentPriority.MEDIUM),
    )

    status_label = ShipmentStatus(status).label if status in ShipmentStatus.values else status
    risk_label = RiskLevel(risk_level).label if risk_level in RiskLevel.values else risk_level

    weather_label = weather.get_condition_display() if weather else "Unknown"
    traffic_label = traffic.get_congestion_display() if traffic else "Unknown"
    disruptions_summary = _disruptions_summary(active_events)

    weights = {
        Mode.ROAD: (0.3, 0.5, 0.2),
        Mode.AIR: (0.7, 0.0, 0.3),
        Mode.SEA: (0.6, 0.1, 0.3),
    }.get(shipment.mode, (0.6, 0.1, 0.3))
    w_wt, t_wt, e_wt = weights

    weather_phrase = "" if condition in (WeatherCondition.CLEAR, WeatherCondition.UNKNOWN) else f"{weather_label.lower()} weather"
    traffic_phrase = ""
    if traffic and traffic.congestion not in ("low", "unknown"):
        traffic_phrase = f"{traffic_label.lower()} traffic congestion"
    event_phrase = ""
    if active_events:
        event_phrase = f"disruption: {_event_example(active_events)}"

    drivers: list[tuple[float, str]] = []
    if weather_phrase:
        drivers.append((w_wt * w, weather_phrase))
    if traffic_phrase:
        drivers.append((t_wt * t, traffic_phrase))
    if event_phrase:
        drivers.append((e_wt * e, event_phrase))
    drivers.sort(key=lambda x: x[0], reverse=True)
    top_drivers = [p for _, p in drivers[:2] if p]

    if status == ShipmentStatus.DELIVERED:
        status_reason = "Delivered (confirmed in the system)."
    elif status == ShipmentStatus.DELAYED:
        status_reason = "Delayed — predicted delay is material based on current signals."
    else:
        status_reason = "On track — predicted delay is within tolerance based on current signals."

    delay_reason = ""
    if status == ShipmentStatus.DELAYED:
        if top_drivers:
            delay_reason = " and ".join(top_drivers) + "."
        elif active_events:
            delay_reason = f"Disruption: {_event_example(active_events)}."
        else:
            delay_reason = "Low-severity conditions; monitoring for changes."

    return ShipmentLiveState(
        status=status,
        status_label=status_label,
        status_reason=status_reason,
        risk_level=risk_level,
        risk_label=risk_label,
        risk_score=risk_score,
        risk_value=risk,
        delay_minutes=delay_minutes,
        eta=eta,
        delay_reason=delay_reason,
        recommendation=recommendation,
        weather_score=w,
        traffic_score=t,
        event_score=e,
        weather_label=weather_label,
        traffic_label=traffic_label,
        disruptions_summary=disruptions_summary,
    )
