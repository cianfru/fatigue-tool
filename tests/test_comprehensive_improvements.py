"""
Sleep-quantity to performance monotonicity tests.

This file previously ran a sweep of sleep scenarios and printed a table with no
assertions, so it reported success no matter what the model produced. The sweep
is still the right idea — it is the clearest statement of the core contract —
so it now asserts on it: more effective sleep must never predict worse
performance, and the whole sweep must stay on the 20-100 scale.
"""
from datetime import datetime, timedelta

import pytest
import pytz

from core import BorbelyFatigueModel, ModelConfig
from models.data_models import Airport, Duty, FlightSegment, SleepBlock

TZ = pytz.timezone('Asia/Qatar')
DOH = Airport(code='DOH', timezone='Asia/Qatar')
DXB = Airport(code='DXB', timezone='Asia/Dubai')
MCT = Airport(code='MCT', timezone='Asia/Muscat')

# (label, duration_hours, efficiency) ordered worst to best by effective sleep.
SCENARIOS = [
    ('insufficient', 5.0, 0.70),   # 3.50 h effective
    ('constrained', 6.0, 0.75),    # 4.50 h
    ('moderate', 7.0, 0.80),       # 5.60 h
    ('degraded', 8.0, 0.71),       # 5.68 h
    ('good', 8.0, 0.85),           # 6.80 h
    ('excellent', 8.0, 0.95),      # 7.60 h
]


def run_scenario(model, duration_hours, efficiency, report_hour=7):
    """Two-sector morning duty preceded by a sleep block of the given quality."""
    report = TZ.localize(
        datetime(2026, 2, 10, report_hour, 10)).astimezone(pytz.utc)
    dep1 = report + timedelta(hours=1)
    arr1 = dep1 + timedelta(hours=2, minutes=30)
    dep2 = arr1 + timedelta(hours=1, minutes=15)
    arr2 = dep2 + timedelta(hours=3)

    duty = Duty(
        duty_id=f'test_{duration_hours}_{efficiency}',
        date=datetime(2026, 2, 10),
        report_time_utc=report,
        release_time_utc=arr2 + timedelta(minutes=30),
        segments=[
            FlightSegment('QR123', DOH, DXB, dep1, arr1),
            FlightSegment('QR456', DXB, MCT, dep2, arr2),
        ],
        home_base_timezone='Asia/Qatar',
    )

    sleep = SleepBlock(
        start_utc=report - timedelta(hours=duration_hours + 2),
        end_utc=report - timedelta(hours=2),
        location_timezone='Asia/Qatar',
        duration_hours=duration_hours,
        quality_factor=efficiency,
        effective_sleep_hours=duration_hours * efficiency,
        environment='home',
    )

    return model.simulate_duty(
        duty=duty, sleep_history=[sleep],
        circadian_phase_shift=0.0, initial_s=0.3)


@pytest.fixture(scope='module')
def sweep():
    model = BorbelyFatigueModel(ModelConfig.default_easa_config())
    return [
        (label, duration * efficiency, run_scenario(model, duration, efficiency))
        for label, duration, efficiency in SCENARIOS
    ]


def test_scenarios_are_ordered_by_effective_sleep(sweep):
    """Guards the fixture itself, so a later edit cannot silently unsort it."""
    effective = [eff for _, eff, _ in sweep]
    assert effective == sorted(effective)


def test_more_sleep_never_predicts_worse_landing_performance(sweep):
    landings = [(label, t.landing_performance) for label, _, t in sweep]
    for (prev_label, prev), (label, current) in zip(landings, landings[1:]):
        assert current >= prev, (
            f"{label} slept more than {prev_label} but scored worse: "
            f"{current:.1f} < {prev:.1f}"
        )


def test_more_sleep_never_predicts_worse_minimum_performance(sweep):
    minima = [(label, t.min_performance) for label, _, t in sweep]
    for (prev_label, prev), (label, current) in zip(minima, minima[1:]):
        assert current >= prev, (
            f"{label} slept more than {prev_label} but bottomed out lower: "
            f"{current:.1f} < {prev:.1f}"
        )


def test_excellent_sleep_clearly_beats_insufficient_sleep(sweep):
    """The sweep must actually separate the extremes, not just avoid inverting."""
    worst = sweep[0][2].landing_performance
    best = sweep[-1][2].landing_performance
    assert best - worst > 5.0, (
        f"only {best - worst:.1f} points separate 3.5 h from 7.6 h of sleep"
    )


def test_all_predictions_stay_on_scale(sweep):
    for label, _, timeline in sweep:
        for point in timeline.timeline:
            assert 20.0 <= point.raw_performance <= 100.0, label


def test_homeostatic_pressure_rises_across_the_duty(sweep):
    """S must accumulate while awake on duty (Borbely 1982)."""
    for label, _, timeline in sweep:
        first = timeline.timeline[0].homeostatic_component
        last = timeline.timeline[-1].homeostatic_component
        assert last > first, f"{label}: S did not rise ({first:.3f} -> {last:.3f})"
