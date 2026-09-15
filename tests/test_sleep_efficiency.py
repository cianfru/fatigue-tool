"""
Sleep efficiency behaviour tests.

This file previously printed a narrative comparison against hard-coded "old
model" figures and asserted nothing, so it passed regardless of what the model
did. It now pins the invariants that matter: the ordering of environments,
that quality genuinely discounts raw duration, and that circadian alignment and
time pressure move efficiency in the expected direction.

Base efficiencies follow Signal et al. (2013) J Sleep Res — hotel PSG 88 %,
crew rest bunk 70 %.
"""
from datetime import datetime

import pytest
import pytz

from core import BorbelyFatigueModel, ModelConfig

TZ = pytz.timezone('Asia/Qatar')


@pytest.fixture(scope='module')
def calculator():
    return BorbelyFatigueModel(ModelConfig.default_easa_config()).sleep_calculator


def quality_for(calculator, location, start, end, next_event=None):
    return calculator.calculate_sleep_quality(
        sleep_start=start,
        sleep_end=end,
        location=location,
        previous_duty_end=None,
        next_event=next_event or end.replace(hour=min(end.hour + 2, 23)),
        location_timezone='Asia/Qatar',
    )


@pytest.fixture
def overnight():
    """A well-timed 23:00-07:00 night."""
    return (
        TZ.localize(datetime(2026, 2, 10, 23, 0)),
        TZ.localize(datetime(2026, 2, 11, 7, 0)),
        TZ.localize(datetime(2026, 2, 11, 9, 0)),
    )


class TestEnvironmentOrdering:
    def test_home_beats_hotel_beats_crew_rest(self, calculator, overnight):
        start, end, nxt = overnight
        home = quality_for(calculator, 'home', start, end, nxt)
        hotel = quality_for(calculator, 'hotel', start, end, nxt)
        bunk = quality_for(calculator, 'crew_rest', start, end, nxt)

        assert home.sleep_efficiency > hotel.sleep_efficiency > bunk.sleep_efficiency

    def test_airport_hotel_sits_between_hotel_and_bunk(self, calculator, overnight):
        start, end, nxt = overnight
        hotel = quality_for(calculator, 'hotel', start, end, nxt)
        airport = quality_for(calculator, 'airport_hotel', start, end, nxt)
        bunk = quality_for(calculator, 'crew_rest', start, end, nxt)

        assert bunk.sleep_efficiency < airport.sleep_efficiency < hotel.sleep_efficiency


class TestEffectiveHours:
    def test_effective_never_exceeds_duration(self, calculator, overnight):
        start, end, nxt = overnight
        for location in ('home', 'hotel', 'crew_rest', 'airport_hotel'):
            q = quality_for(calculator, location, start, end, nxt)
            assert q.effective_sleep_hours <= q.actual_sleep_hours + 1e-9, location

    def test_well_timed_home_night_is_highly_efficient(self, calculator, overnight):
        """A circadian-aligned 8 h night at home should lose little to quality."""
        start, end, nxt = overnight
        q = quality_for(calculator, 'home', start, end, nxt)

        assert q.actual_sleep_hours == pytest.approx(8.0, abs=0.1)
        assert q.sleep_efficiency > 0.85
        assert q.effective_sleep_hours > 7.0

    def test_efficiency_stays_within_model_bounds(self, calculator, overnight):
        """Combined efficiency is clamped to [0.70, 1.0]."""
        start, end, nxt = overnight
        for location in ('home', 'hotel', 'crew_rest', 'airport_hotel'):
            q = quality_for(calculator, location, start, end, nxt)
            assert 0.70 <= q.sleep_efficiency <= 1.0, location


class TestTimePressure:
    def test_imminent_report_reduces_efficiency(self, calculator):
        """
        Sleep ending 90 minutes before report is worse than the same block with
        a comfortable margin, even though the duration is identical.
        """
        start = TZ.localize(datetime(2026, 2, 10, 22, 0))
        end = TZ.localize(datetime(2026, 2, 11, 5, 0))

        pressured = quality_for(
            calculator, 'home', start, end,
            TZ.localize(datetime(2026, 2, 11, 6, 30)))
        relaxed = quality_for(
            calculator, 'home', start, end,
            TZ.localize(datetime(2026, 2, 11, 14, 0)))

        assert pressured.sleep_efficiency <= relaxed.sleep_efficiency
        assert pressured.actual_sleep_hours == pytest.approx(
            relaxed.actual_sleep_hours)


class TestCircadianAlignment:
    def test_night_sleep_beats_daytime_sleep_of_equal_length(self, calculator):
        """An 8 h block starting at 10:00 fights the circadian drive to wake."""
        night = quality_for(
            calculator, 'home',
            TZ.localize(datetime(2026, 2, 10, 23, 0)),
            TZ.localize(datetime(2026, 2, 11, 7, 0)),
            TZ.localize(datetime(2026, 2, 11, 12, 0)))
        day = quality_for(
            calculator, 'home',
            TZ.localize(datetime(2026, 2, 11, 10, 0)),
            TZ.localize(datetime(2026, 2, 11, 18, 0)),
            TZ.localize(datetime(2026, 2, 11, 23, 0)))

        assert night.sleep_efficiency > day.sleep_efficiency

    def test_night_sleep_records_wocl_overlap(self, calculator, overnight):
        start, end, nxt = overnight
        q = quality_for(calculator, 'home', start, end, nxt)
        assert q.wocl_overlap_hours > 0
