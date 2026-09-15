"""
Regression tests for cumulative sleep debt feeding back into Process S.

Sleep debt used to be tracked and reported but never reached the model, so a
pilot carrying a week of short nights scored identically to a rested one. These
tests pin the behaviour that debt accumulates on disruptive patterns, degrades
predicted performance, and is repaid by days off.
"""
from datetime import datetime, timedelta

import pytest
import pytz

from core.fatigue_model import BorbelyFatigueModel
from models.data_models import Airport, Duty, FlightSegment, Roster

DOH = Airport(code='DOH', timezone='Asia/Qatar')
DXB = Airport(code='DXB', timezone='Asia/Dubai')
TZ = pytz.timezone('Asia/Qatar')


def make_duty(day: int, report_hour: int) -> Duty:
    """A DOH-DXB-DOH return trip reporting at the given home-base hour."""
    report = TZ.localize(datetime(2026, 3, day, report_hour, 0)).astimezone(pytz.utc)
    dep1 = report + timedelta(hours=1)
    arr1 = dep1 + timedelta(hours=1, minutes=10)
    dep2 = arr1 + timedelta(hours=1, minutes=30)
    arr2 = dep2 + timedelta(hours=1, minutes=10)
    return Duty(
        duty_id=f'D{day:02d}',
        date=datetime(2026, 3, day),
        report_time_utc=report,
        release_time_utc=arr2 + timedelta(minutes=30),
        segments=[
            FlightSegment('QR1', DOH, DXB, dep1, arr1),
            FlightSegment('QR2', DXB, DOH, dep2, arr2),
        ],
        home_base_timezone='Asia/Qatar',
    )


def analyse(duties):
    roster = Roster(
        roster_id='R_TEST', pilot_id='P_TEST', month='2026-03',
        duties=duties, home_base_timezone='Asia/Qatar',
    )
    return BorbelyFatigueModel().simulate_roster(roster)


@pytest.fixture(scope='module')
def normal_roster():
    return analyse([make_duty(d, 10) for d in range(2, 8)])


@pytest.fixture(scope='module')
def early_block():
    return analyse([make_duty(d, 4) for d in range(2, 8)])


@pytest.fixture(scope='module')
def block_then_rest():
    return analyse([make_duty(d, 4) for d in (2, 3, 4)] +
                   [make_duty(d, 4) for d in (10, 11)])


def test_normal_roster_stays_debt_free(normal_roster):
    """Circadian-aligned duties with full nights must not manufacture debt."""
    debts = [t.cumulative_sleep_debt for t in normal_roster.duty_timelines]
    assert max(debts) < 1.0, f"normal roster accrued debt: {debts}"


def test_consecutive_early_starts_accumulate_debt(early_block):
    """Back-to-back 04:00 reports truncate night sleep and must compound."""
    debts = [t.cumulative_sleep_debt for t in early_block.duty_timelines]
    assert debts[-1] > debts[1], f"debt did not accumulate: {debts}"


def test_accumulated_debt_degrades_performance(early_block):
    """Debt must reach the model, not just the report."""
    landings = [t.landing_performance for t in early_block.duty_timelines]
    assert landings[-1] < landings[1], f"performance did not degrade: {landings}"


def test_days_off_repay_debt(block_then_rest):
    """An extended break must pay the ledger down, not add to it."""
    debts = [t.cumulative_sleep_debt for t in block_then_rest.duty_timelines]
    before_break, after_break = debts[2], debts[3]
    assert after_break < before_break, (
        f"debt rose across days off: {before_break:.2f} -> {after_break:.2f}"
    )


def test_debt_offset_is_capped():
    """Debt alone must not be able to saturate the homeostat."""
    model = BorbelyFatigueModel()
    duty = make_duty(2, 10)
    rested = model.simulate_duty(duty, [], cumulative_sleep_debt=0.0)
    crushed = model.simulate_duty(duty, [], cumulative_sleep_debt=500.0)

    assert crushed.landing_performance < rested.landing_performance
    assert crushed.landing_performance > 20.0, "capped offset should not floor performance"


def test_rest_days_at_home_base_use_home_environment():
    """
    Rest days at base were silently treated as hotel stays because the optional
    pilot_base field is usually unset, costing ~1 h of effective sleep a night.
    """
    duties = [make_duty(2, 10), make_duty(8, 10)]
    roster = Roster(
        roster_id='R_ENV', pilot_id='P', month='2026-03',
        duties=duties, home_base_timezone='Asia/Qatar',
    )
    model = BorbelyFatigueModel()
    model.simulate_roster(roster)

    environments = [
        block['environment']
        for key, entry in model.sleep_strategies.items() if key.startswith('rest_')
        for block in entry['sleep_blocks']
    ]
    assert environments, "expected recovery sleep across the break"
    assert all(env == 'home' for env in environments), (
        f"rest days not at home: {environments}"
    )
