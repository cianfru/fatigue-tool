"""
Daytime recovery nap behaviour and the 24 h sleep budget.

The estimator used to grant a 3.5 h afternoon nap on every morning-arrival day,
capped on circadian grounds alone with no reference to sleep pressure. A pilot
awake seven hours after a truncated night received the full 3.5 h, putting
total sleep at 8.5 h per 24 h across consecutive 04:00 starts — against the
5.70 +/- 0.73 h that Flynn-Evans et al. (2018) measured by actigraphy in 44
short-haul pilots over five consecutive early shifts.

A nap is now drawn FROM the 24 h budget rather than added on top of it, which
is the architecture Darwent, Dawson & Roach (2012) validated at 85 % epoch
agreement against actigraphy.
"""
from datetime import datetime, timedelta

import pytest
import pytz

from core.fatigue_model import BorbelyFatigueModel, CircadianState
from core.parameters import ModelConfig
from models.data_models import Airport, Duty, FlightSegment, Roster

DOH = Airport(code='DOH', timezone='Asia/Qatar')
DXB = Airport(code='DXB', timezone='Asia/Dubai')
TZ = pytz.timezone('Asia/Qatar')

# Flynn-Evans et al. (2018) Sleep Health: 5.70 +/- 0.73 h per 24 h across five
# consecutive early shifts. One SD either side is the acceptance band.
EARLY_START_SLEEP_MIN = 4.97
EARLY_START_SLEEP_MAX = 6.43


def make_duty(day, report_hour):
    report = TZ.localize(datetime(2026, 3, day, report_hour, 0)).astimezone(pytz.utc)
    dep1 = report + timedelta(hours=1)
    arr1 = dep1 + timedelta(hours=1, minutes=10)
    dep2 = arr1 + timedelta(hours=1, minutes=30)
    arr2 = dep2 + timedelta(hours=1, minutes=10)
    return Duty(
        duty_id=f'D{day:02d}', date=datetime(2026, 3, day),
        report_time_utc=report, release_time_utc=arr2 + timedelta(minutes=30),
        segments=[FlightSegment('QR1', DOH, DXB, dep1, arr1),
                  FlightSegment('QR2', DXB, DOH, dep2, arr2)],
        home_base_timezone='Asia/Qatar')


def generated_sleep(duties):
    """Sleep blocks the model predicts for a roster, in chronological order."""
    roster = Roster(roster_id='R_NAP', pilot_id='P', month='2026-03',
                    duties=duties, home_base_timezone='Asia/Qatar')
    model = BorbelyFatigueModel()
    clock = CircadianState(
        current_phase_shift_hours=0.0,
        last_update_utc=duties[0].report_time_utc - timedelta(days=1),
        reference_timezone='Asia/Qatar')
    timeline = [(clock.last_update_utc, clock)]
    for duty in duties:
        clock = model.calculate_adaptation(
            duty.report_time_utc, clock, 'Asia/Qatar', 'Asia/Qatar')
        timeline.append((duty.report_time_utc, clock))
    blocks, _ = model._extract_sleep_from_roster(roster, timeline)
    return sorted(blocks, key=lambda b: b.start_utc)


def sleep_in_24h_before(blocks, report_utc):
    window_start = report_utc - timedelta(hours=24)
    return sum(b.duration_hours for b in blocks
               if b.start_utc >= window_start and b.end_utc <= report_utc)


@pytest.fixture(scope='module')
def early_block_sleep():
    duties = [make_duty(d, 4) for d in range(2, 8)]
    return duties, generated_sleep(duties)


@pytest.fixture(scope='module')
def normal_block_sleep():
    duties = [make_duty(d, 10) for d in range(2, 8)]
    return duties, generated_sleep(duties)


class TestTotalSleepBudget:
    def test_consecutive_early_starts_match_actigraphy(self, early_block_sleep):
        """The calibration target: Flynn-Evans (2018), 5.70 +/- 0.73 h/24 h."""
        duties, blocks = early_block_sleep
        # Skip the first duty, which has no preceding roster context.
        totals = [sleep_in_24h_before(blocks, d.report_time_utc) for d in duties[1:]]
        steady = sum(totals) / len(totals)
        assert EARLY_START_SLEEP_MIN <= steady <= EARLY_START_SLEEP_MAX, (
            f"consecutive 04:00 starts yield {steady:.2f} h/24h, outside the "
            f"{EARLY_START_SLEEP_MIN}-{EARLY_START_SLEEP_MAX} h actigraphy band"
        )

    def test_normal_duties_get_a_full_night(self, normal_block_sleep):
        """A 10:00 report should not be short of sleep, nor sleep nine hours."""
        duties, blocks = normal_block_sleep
        totals = [sleep_in_24h_before(blocks, d.report_time_utc) for d in duties[1:]]
        steady = sum(totals) / len(totals)
        assert 7.0 <= steady <= 8.5, (
            f"normal day duties yield {steady:.2f} h/24h"
        )

    def test_early_starts_sleep_less_than_normal_duties(
            self, early_block_sleep, normal_block_sleep):
        early_duties, early = early_block_sleep
        normal_duties, normal = normal_block_sleep
        early_avg = sum(sleep_in_24h_before(early, d.report_time_utc)
                        for d in early_duties[1:]) / 5
        normal_avg = sum(sleep_in_24h_before(normal, d.report_time_utc)
                         for d in normal_duties[1:]) / 5
        # Roach et al. (2012): ~15 min lost per hour of report-time advance.
        assert normal_avg - early_avg > 1.5, (
            f"only {normal_avg - early_avg:.2f} h separates 04:00 from 10:00 starts"
        )


class TestNapShape:
    @staticmethod
    def _naps(blocks):
        """Daytime blocks: short, and starting in daylight hours."""
        return [b for b in blocks
                if b.duration_hours <= 4.0
                and 8 <= b.start_utc.astimezone(TZ).hour < 20]

    def test_naps_respect_the_ninety_minute_ceiling(self, early_block_sleep):
        _, blocks = early_block_sleep
        ceiling = ModelConfig.default_easa_config().nap_params.nap_max_duration_hours
        for nap in self._naps(blocks):
            assert nap.duration_hours <= ceiling + 1e-9, (
                f"nap of {nap.duration_hours:.2f} h exceeds the {ceiling} h ceiling"
            )

    def test_no_nap_approaches_the_old_three_and_a_half_hours(self, early_block_sleep):
        """Direct guard against the defect this module exists to prevent."""
        _, blocks = early_block_sleep
        for nap in self._naps(blocks):
            assert nap.duration_hours < 2.0, (
                f"daytime block of {nap.duration_hours:.2f} h looks like the "
                f"old circadian-only cap"
            )

    def test_naps_fall_in_the_afternoon_propensity_window(self, early_block_sleep):
        """
        Sleep propensity has a secondary afternoon peak; the wake-maintenance
        zone closes the window from late afternoon (Lavie 1986; Strogatz 1986).
        """
        _, blocks = early_block_sleep
        params = ModelConfig.default_easa_config().nap_params
        for nap in self._naps(blocks):
            start_hour = nap.start_utc.astimezone(TZ).hour
            assert params.nap_window_start_hour <= start_hour <= params.nap_window_end_hour, (
                f"nap starts at {start_hour}:00, outside the "
                f"{params.nap_window_start_hour:.0f}-{params.nap_window_end_hour:.0f} window"
            )


class TestNapDurationRule:
    """The helper in isolation, away from roster-construction confounds."""

    @staticmethod
    def _nap_hours_for_report(report_hour):
        model = BorbelyFatigueModel()
        duty = make_duty(2, report_hour)
        return model.sleep_calculator._daytime_nap_duration(duty, TZ)

    def test_no_nap_when_the_prior_night_was_unbroken(self):
        """A pilot cannot recover sleep they are not short of."""
        assert self._nap_hours_for_report(10) == 0.0

    def test_early_report_produces_a_nap(self):
        assert self._nap_hours_for_report(4) > 0.0

    def test_nap_is_bounded_by_the_deficit(self):
        """
        Every predicted nap must be small. The bound that binds is napping
        behaviour, not the circadian ceiling.
        """
        params = ModelConfig.default_easa_config().nap_params
        for report_hour in (3, 4, 5, 6):
            hours = self._nap_hours_for_report(report_hour)
            assert hours <= params.nap_max_duration_hours
            assert hours <= params.expected_nap_hours + 1e-9

    def test_expected_value_is_the_product_of_prevalence_and_duration(self):
        params = ModelConfig.default_easa_config().nap_params
        assert params.expected_nap_hours == pytest.approx(
            params.nap_probability * params.nap_mean_duration_hours)

    def test_disabling_expected_value_models_the_napping_pilot(self):
        """
        The conservative alternative for an individual advocacy case: model the
        pilot who does nap rather than the population average.
        """
        params = ModelConfig.default_easa_config().nap_params
        params.use_expected_value = False
        assert params.expected_nap_hours == params.nap_mean_duration_hours
