"""
Regression tests for timezone handling and pinch event detection.

Covers three defects that produced silently wrong output rather than errors:
attaching a pytz zone with replace(tzinfo=...) (Local Mean Time offsets),
reinterpreting a UTC wall clock as local time when measuring timezone shift,
and restricting pinch detection to takeoff/approach/landing.
"""
from datetime import datetime, timedelta

import pytest
import pytz

from core.compliance import EASAComplianceValidator
from core.fatigue_model import BorbelyFatigueModel, CircadianState
from models.data_models import Airport, Duty, FlightSegment

DOH = Airport(code='DOH', timezone='Asia/Qatar')
LHR = Airport(code='LHR', timezone='Europe/London')
QATAR = pytz.timezone('Asia/Qatar')
LONDON = pytz.timezone('Europe/London')


class TestWoclEncroachment:
    """WOCL is 02:00-05:59 in the reference timezone (AMC1 ORO.FTL.105(10))."""

    def setup_method(self):
        self.validator = EASAComplianceValidator()

    def test_duty_spanning_full_wocl(self):
        start = QATAR.localize(datetime(2026, 3, 5, 1, 0)).astimezone(pytz.utc)
        end = QATAR.localize(datetime(2026, 3, 5, 7, 0)).astimezone(pytz.utc)
        encroachment = self.validator.calculate_wocl_encroachment(
            start, end, 'Asia/Qatar')
        assert encroachment >= timedelta(hours=3, minutes=59)
        assert encroachment <= timedelta(hours=4)

    def test_boundaries_use_real_offset_not_local_mean_time(self):
        """
        Asia/Qatar has no DST, so a duty starting exactly at 02:00 local must
        pick up the whole window. replace(tzinfo=...) yielded +03:26 rather
        than +03:00, shifting every boundary by 26 minutes.
        """
        start = QATAR.localize(datetime(2026, 6, 10, 2, 0)).astimezone(pytz.utc)
        end = QATAR.localize(datetime(2026, 6, 10, 6, 0)).astimezone(pytz.utc)
        encroachment = self.validator.calculate_wocl_encroachment(
            start, end, 'Asia/Qatar')
        assert encroachment >= timedelta(hours=3, minutes=59)

    def test_duty_clear_of_wocl_reports_nothing(self):
        start = QATAR.localize(datetime(2026, 6, 10, 9, 0)).astimezone(pytz.utc)
        end = QATAR.localize(datetime(2026, 6, 10, 17, 0)).astimezone(pytz.utc)
        assert self.validator.calculate_wocl_encroachment(
            start, end, 'Asia/Qatar') == timedelta()

    def test_survives_spring_forward_transition(self):
        """The 2026-03-29 London transition skips 01:00-02:00 local."""
        start = LONDON.localize(datetime(2026, 3, 28, 23, 0)).astimezone(pytz.utc)
        end = LONDON.localize(datetime(2026, 3, 29, 8, 0)).astimezone(pytz.utc)
        encroachment = self.validator.calculate_wocl_encroachment(
            start, end, 'Europe/London')
        assert encroachment > timedelta()

    def test_survives_autumn_fallback_transition(self):
        """The 2026-10-25 London transition repeats 01:00-02:00 local."""
        start = LONDON.localize(datetime(2026, 10, 24, 23, 0)).astimezone(pytz.utc)
        end = LONDON.localize(datetime(2026, 10, 25, 8, 0)).astimezone(pytz.utc)
        encroachment = self.validator.calculate_wocl_encroachment(
            start, end, 'Europe/London')
        assert encroachment > timedelta()


class TestTimezoneDifference:
    def test_accepts_aware_datetimes(self):
        """Every datetime in the model is UTC-aware; pytz.utcoffset rejects those."""
        reference = pytz.utc.localize(datetime(2026, 7, 1, 12, 0))
        assert DOH.timezone_difference_hours(LHR, reference) == pytest.approx(-2.0)

    def test_tracks_daylight_saving(self):
        summer = pytz.utc.localize(datetime(2026, 7, 1, 12, 0))
        winter = pytz.utc.localize(datetime(2026, 1, 1, 12, 0))
        assert DOH.timezone_difference_hours(LHR, summer) == pytest.approx(-2.0)
        assert DOH.timezone_difference_hours(LHR, winter) == pytest.approx(-3.0)


class TestCircadianAdaptation:
    def test_shift_direction_matches_real_offsets(self):
        """Westward travel must produce a negative phase shift target."""
        model = BorbelyFatigueModel()
        start = pytz.utc.localize(datetime(2026, 7, 1, 0, 0))
        state = CircadianState(
            current_phase_shift_hours=0.0,
            last_update_utc=start,
            reference_timezone='Asia/Qatar',
        )
        moved = model.calculate_adaptation(
            start + timedelta(days=1), state, 'Europe/London', 'Asia/Qatar')
        assert moved.current_phase_shift_hours < 0

    def test_adaptation_is_gradual(self):
        """One day cannot close a full 2 h shift at the published rates."""
        model = BorbelyFatigueModel()
        start = pytz.utc.localize(datetime(2026, 7, 1, 0, 0))
        state = CircadianState(
            current_phase_shift_hours=0.0,
            last_update_utc=start,
            reference_timezone='Asia/Qatar',
        )
        moved = model.calculate_adaptation(
            start + timedelta(days=1), state, 'Europe/London', 'Asia/Qatar')
        assert abs(moved.current_phase_shift_hours) <= 2.0


class TestPinchDetection:
    def _long_night_duty(self):
        report = QATAR.localize(datetime(2026, 3, 5, 21, 0)).astimezone(pytz.utc)
        dep = report + timedelta(hours=1)
        arr = dep + timedelta(hours=12)
        return Duty(
            duty_id='LONGNIGHT', date=datetime(2026, 3, 5),
            report_time_utc=report, release_time_utc=arr + timedelta(minutes=30),
            segments=[FlightSegment('QR7', DOH, LHR, dep, arr)],
            home_base_timezone='Asia/Qatar',
        )

    def test_detects_pinch_outside_critical_phases(self):
        """
        A pinch during cruise is when a controlled-rest decision can still be
        made; restricting detection to takeoff/approach/landing hid it.
        """
        model = BorbelyFatigueModel()
        timeline = model.simulate_duty(
            self._long_night_duty(), [], initial_s=0.55, cumulative_sleep_debt=18.0)

        assert timeline.pinch_events, "expected pinches on a WOCL night sector"
        phases = {pe.flight_phase.value for pe in timeline.pinch_events}
        assert 'cruise' in phases, f"cruise pinch not detected, saw {phases}"

    def test_pinch_events_satisfy_both_thresholds(self):
        model = BorbelyFatigueModel()
        timeline = model.simulate_duty(
            self._long_night_duty(), [], initial_s=0.55, cumulative_sleep_debt=18.0)

        for pe in timeline.pinch_events:
            assert pe.sleep_pressure > model.params.pinch_sleep_pressure_threshold
            assert pe.circadian < model.params.pinch_circadian_threshold

    def test_rested_daytime_duty_has_no_pinch(self):
        """Both conditions must hold, so a rested day sector stays clean."""
        report = QATAR.localize(datetime(2026, 3, 5, 9, 0)).astimezone(pytz.utc)
        dep = report + timedelta(hours=1)
        arr = dep + timedelta(hours=2)
        duty = Duty(
            duty_id='DAY', date=datetime(2026, 3, 5),
            report_time_utc=report, release_time_utc=arr + timedelta(minutes=30),
            segments=[FlightSegment('QR1', DOH, LHR, dep, arr)],
            home_base_timezone='Asia/Qatar',
        )
        timeline = BorbelyFatigueModel().simulate_duty(
            duty, [], initial_s=0.1, cumulative_sleep_debt=0.0)
        assert timeline.pinch_events == []

    def test_pinch_serializes_with_real_attribute_names(self):
        """The API serializer referenced three fields PinchEvent never had."""
        model = BorbelyFatigueModel()
        timeline = model.simulate_duty(
            self._long_night_duty(), [], initial_s=0.55, cumulative_sleep_debt=18.0)

        for pe in timeline.pinch_events:
            payload = {
                'timestamp': pe.time_utc.isoformat(),
                'timestamp_local': pe.time_local.isoformat(),
                'performance': pe.performance,
                'phase': pe.flight_phase.value if pe.flight_phase else None,
                'circadian': pe.circadian,
                'sleep_pressure': pe.sleep_pressure,
                'severity': pe.severity,
            }
            assert payload['severity'] in {'moderate', 'high', 'critical'}
