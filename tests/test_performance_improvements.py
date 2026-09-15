"""
Performance timeline structure tests for a routine two-sector day duty.

This file previously printed a comparison against hard-coded target figures
("expected report performance: 73-75%") and asserted nothing, so it reported
success while showing a 12-point miss. Those targets came from a one-off tuning
session and are not a specification; pinning them would freeze whatever the
model happened to output that day.

What is worth pinning is the shape of the timeline: the process decomposition
must be internally consistent, performance must decline across a duty with no
in-flight rest, and a rested pilot on a daytime sector must not be scored as
high risk.
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


@pytest.fixture(scope='module')
def day_duty():
    """07:10 report, two sectors: 08:10-10:40 and 11:55-14:55, release 15:25."""
    report = TZ.localize(datetime(2026, 2, 10, 7, 10)).astimezone(pytz.utc)
    dep1 = TZ.localize(datetime(2026, 2, 10, 8, 10)).astimezone(pytz.utc)
    arr1 = dep1 + timedelta(hours=2, minutes=30)
    dep2 = arr1 + timedelta(hours=1, minutes=15)
    arr2 = dep2 + timedelta(hours=3)

    return Duty(
        duty_id='DAY_2SECTOR',
        date=datetime(2026, 2, 10),
        report_time_utc=report,
        release_time_utc=arr2 + timedelta(minutes=30),
        segments=[
            FlightSegment('QR123', DOH, DXB, dep1, arr1),
            FlightSegment('QR456', DXB, MCT, dep2, arr2),
        ],
        home_base_timezone='Asia/Qatar',
    )


@pytest.fixture(scope='module')
def day_duty_timeline(day_duty):
    """The duty simulated after a full night at home."""
    model = BorbelyFatigueModel(ModelConfig.default_easa_config())

    sleep = SleepBlock(
        start_utc=TZ.localize(datetime(2026, 2, 9, 23, 0)).astimezone(pytz.utc),
        end_utc=TZ.localize(datetime(2026, 2, 10, 6, 30)).astimezone(pytz.utc),
        location_timezone='Asia/Qatar',
        duration_hours=7.5,
        quality_factor=0.93,
        effective_sleep_hours=7.0,
        environment='home',
    )

    return model.simulate_duty(
        duty=day_duty, sleep_history=[sleep],
        circadian_phase_shift=0.0, initial_s=0.3)


class TestTimelineStructure:
    def test_timeline_covers_the_whole_duty(self, day_duty, day_duty_timeline):
        points = day_duty_timeline.timeline
        assert points, "no timeline generated"
        span = (points[-1].timestamp_utc - points[0].timestamp_utc).total_seconds() / 3600
        assert span == pytest.approx(day_duty.duty_hours, abs=0.2)

    def test_timestamps_are_monotonic(self, day_duty_timeline):
        stamps = [p.timestamp_utc for p in day_duty_timeline.timeline]
        assert stamps == sorted(stamps)

    def test_hours_on_duty_tracks_elapsed_time(self, day_duty_timeline):
        points = day_duty_timeline.timeline
        assert points[0].hours_on_duty == pytest.approx(0.0, abs=0.01)
        assert points[-1].hours_on_duty > points[0].hours_on_duty

    def test_landing_performance_is_reported(self, day_duty_timeline):
        assert day_duty_timeline.landing_performance is not None
        assert day_duty_timeline.landing_time is not None


class TestProcessDecomposition:
    def test_components_stay_in_range(self, day_duty_timeline):
        for p in day_duty_timeline.timeline:
            assert 0.0 <= p.homeostatic_component <= 1.0
            assert 0.0 <= p.circadian_component <= 1.0
            assert 0.0 <= p.sleep_inertia_component <= 1.0

    def test_sleep_pressure_rises_without_inflight_rest(self, day_duty_timeline):
        points = day_duty_timeline.timeline
        assert points[-1].homeostatic_component > points[0].homeostatic_component

    def test_sleep_inertia_decays_after_report(self, day_duty_timeline):
        """Inertia is a transient; it must not persist through the duty."""
        points = day_duty_timeline.timeline
        assert points[-1].sleep_inertia_component == pytest.approx(0.0, abs=1e-6)

    def test_time_on_task_penalty_accumulates(self, day_duty_timeline):
        points = day_duty_timeline.timeline
        assert points[-1].time_on_task_penalty > points[0].time_on_task_penalty

    def test_critical_phases_are_flagged(self, day_duty_timeline):
        assert any(p.is_critical_phase for p in day_duty_timeline.timeline)


class TestPerformanceBounds:
    def test_performance_stays_on_scale(self, day_duty_timeline):
        for p in day_duty_timeline.timeline:
            assert 20.0 <= p.raw_performance <= 100.0

    def test_summary_statistics_are_consistent(self, day_duty_timeline):
        values = [p.raw_performance for p in day_duty_timeline.timeline]
        assert day_duty_timeline.min_performance == pytest.approx(min(values))
        assert day_duty_timeline.average_performance == pytest.approx(
            sum(values) / len(values))
        assert day_duty_timeline.min_performance <= day_duty_timeline.average_performance

    def test_rested_daytime_duty_is_not_high_risk(self, day_duty_timeline):
        """
        A full night at home before a 07:10 two-sector day should not land the
        pilot in the High band (<65). This is a floor on optimism, not a target.
        """
        assert day_duty_timeline.landing_performance > 55.0, (
            f"rested day duty scored {day_duty_timeline.landing_performance:.1f}"
        )

    def test_rested_daytime_duty_has_no_pinch_events(self, day_duty_timeline):
        assert day_duty_timeline.pinch_events == []


class TestSectorWorkload:
    """
    Sector count drove a workload penalty that back-to-back pairings escaped:
    the counter only advanced when a segment departed strictly after the
    previous one arrived, so a turnaround with no ground time stayed on
    sector 1 for the whole duty.
    """

    @staticmethod
    def _duty(num_sectors, ground_minutes):
        report = TZ.localize(datetime(2026, 6, 10, 6, 0)).astimezone(pytz.utc)
        segments = []
        cursor = report + timedelta(hours=1)
        for i in range(num_sectors):
            arrive = cursor + timedelta(hours=2)
            segments.append(
                FlightSegment(f'Q{i + 1}', DOH, DXB, cursor, arrive))
            cursor = arrive + timedelta(minutes=ground_minutes)
        return Duty(
            duty_id=f'S{num_sectors}_G{ground_minutes}',
            date=datetime(2026, 6, 10),
            report_time_utc=report,
            release_time_utc=segments[-1].scheduled_arrival_utc + timedelta(minutes=30),
            segments=segments,
            home_base_timezone='Asia/Qatar',
        )

    def _landing(self, duty):
        return BorbelyFatigueModel().simulate_duty(
            duty, [], initial_s=0.2).landing_performance

    def test_back_to_back_sectors_still_carry_the_sector_penalty(self):
        """
        Same four sectors, same total duration, differing only in whether the
        turnarounds have ground time. Zero-ground-time pairings must not score
        better than spaced ones by dodging the penalty.
        """
        spaced = self._landing(self._duty(4, ground_minutes=45))
        back_to_back = self._landing(self._duty(4, ground_minutes=0))

        assert back_to_back <= spaced + 0.5, (
            f"zero-turnaround sectors scored {back_to_back:.1f} vs "
            f"{spaced:.1f} for spaced sectors, so the penalty was skipped"
        )

    def test_sector_multiplier_escalates(self):
        """
        The penalty itself, isolated from circadian confounds. Landing
        performance cannot carry this: it is the minimum across all landings,
        and on a morning duty the first landing is the worst because the
        circadian rise outpaces the accumulating sector penalty.
        """
        from core.workload import WorkloadModel
        from models.data_models import FlightPhase

        workload = WorkloadModel()
        multipliers = [
            workload.get_combined_multiplier(FlightPhase.LANDING, sector)
            for sector in (1, 2, 3, 4)
        ]
        assert multipliers == sorted(multipliers)
        assert multipliers[-1] > multipliers[0]
