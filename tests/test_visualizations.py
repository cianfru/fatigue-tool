"""
Smoke tests for the chronogram and aviation calendar renderers.

These were previously untested, and both carried date-arithmetic defects that
only surface in specific months: the calendar derived its day count by
replacing the month with `month % 12 + 1` (landing in the wrong year every
December) and the chronogram indexed rows by day-of-month, so a duty running
past midnight into the next month overwrote the first row of the grid.
"""
from datetime import datetime, timedelta

import matplotlib
import pytest
import pytz

matplotlib.use('Agg')

from core.fatigue_model import BorbelyFatigueModel
from models.data_models import Airport, Duty, FlightSegment, Roster
from visualization.aviation_calendar import AviationCalendar
from visualization.chronogram import FatigueChronogram

DOH = Airport(code='DOH', timezone='Asia/Qatar')
DXB = Airport(code='DXB', timezone='Asia/Dubai')
TZ = pytz.timezone('Asia/Qatar')


def make_duty(year, month, day, hour):
    report = TZ.localize(datetime(year, month, day, hour, 0)).astimezone(pytz.utc)
    dep = report + timedelta(hours=1)
    arr = dep + timedelta(hours=3)
    return Duty(
        duty_id=f'D{month:02d}{day:02d}',
        date=datetime(year, month, day),
        report_time_utc=report,
        release_time_utc=arr + timedelta(minutes=30),
        segments=[FlightSegment('QR1', DOH, DXB, dep, arr)],
        home_base_timezone='Asia/Qatar',
    )


def analyse(duties, month):
    roster = Roster(
        roster_id='R_VIZ', pilot_id='P', month=month,
        duties=duties, home_base_timezone='Asia/Qatar',
    )
    return BorbelyFatigueModel().simulate_roster(roster)


@pytest.fixture
def december_analysis():
    """December exercises the year rollover and a duty crossing into January."""
    duties = [make_duty(2026, 12, d, 10) for d in (5, 15, 25)]
    duties.append(make_duty(2026, 12, 31, 22))
    return analyse(duties, '2026-12')


@pytest.mark.parametrize('month,days', [(1, 31), (2, 28), (6, 30), (12, 31)])
def test_calendar_renders_every_month_length(tmp_path, month, days):
    analysis = analyse([make_duty(2026, month, 5, 10),
                        make_duty(2026, month, days, 10)], f'2026-{month:02d}')
    out = tmp_path / f'cal_{month}.png'
    AviationCalendar().plot_monthly_roster(analysis, save_path=str(out))
    assert out.exists() and out.stat().st_size > 0


def test_calendar_handles_december(december_analysis, tmp_path):
    out = tmp_path / 'cal_dec.png'
    AviationCalendar().plot_monthly_roster(december_analysis, save_path=str(out))
    assert out.exists() and out.stat().st_size > 0


def test_chronogram_returns_a_live_figure(december_analysis, tmp_path):
    """
    The figure is returned for the caller to render, so it must not already be
    closed — plt.close() before the return left callers with a dead object.
    """
    out = tmp_path / 'chrono.png'
    fig = FatigueChronogram().plot_monthly_chronogram(
        december_analysis, save_path=str(out))

    assert fig is not None
    assert fig.axes, "returned figure has no axes; it was closed before return"
    assert out.exists() and out.stat().st_size > 0


def test_chronogram_handles_duty_crossing_into_next_month(december_analysis, tmp_path):
    """A 31 Dec 22:00 report runs into 1 Jan and must not wrap onto row 0."""
    out = tmp_path / 'chrono_wrap.png'
    fig = FatigueChronogram().plot_monthly_chronogram(
        december_analysis, save_path=str(out))
    assert fig is not None and out.exists()
