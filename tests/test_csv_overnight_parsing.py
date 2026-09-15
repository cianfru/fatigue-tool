"""
Regression tests for CSV roster time reconstruction.

Roster columns carry station-local clock times with no date, so a flight
departing 23:00 and arriving 02:00 used to be reconstructed with the arrival
three hours *before* the departure, giving negative block and duty times that
propagated silently into the fatigue timeline.
"""
import textwrap

import pytest

from parsers.roster_parser import CSVRosterParser


@pytest.fixture
def parser():
    return CSVRosterParser(home_base='DOH', home_timezone='Asia/Qatar')


def write_csv(tmp_path, rows):
    path = tmp_path / 'roster.csv'
    header = 'Date,Flight,Departure,Arrival,STD,STA,Report,Release\n'
    path.write_text(header + textwrap.dedent(rows).strip() + '\n')
    return str(path)


def test_overnight_flight_arrives_after_departure(parser, tmp_path):
    csv = write_csv(tmp_path, """
        2026-03-05,QR100,DOH,DOH,23:00,02:00,22:00,02:30
    """)
    roster = parser.parse_csv(csv, pilot_id='P1', month='2026-03')
    segment = roster.duties[0].segments[0]

    assert segment.scheduled_arrival_utc > segment.scheduled_departure_utc
    block = (segment.scheduled_arrival_utc -
             segment.scheduled_departure_utc).total_seconds() / 3600
    assert block == pytest.approx(3.0)


def test_overnight_duty_has_positive_duration(parser, tmp_path):
    csv = write_csv(tmp_path, """
        2026-03-05,QR100,DOH,DOH,23:00,02:00,22:00,02:30
    """)
    roster = parser.parse_csv(csv, pilot_id='P1', month='2026-03')
    duty = roster.duties[0]

    assert duty.release_time_utc > duty.report_time_utc
    assert duty.duty_hours == pytest.approx(4.5)


def test_report_precedes_first_departure(parser, tmp_path):
    csv = write_csv(tmp_path, """
        2026-03-05,QR100,DOH,DOH,23:00,02:00,22:00,02:30
    """)
    roster = parser.parse_csv(csv, pilot_id='P1', month='2026-03')
    duty = roster.duties[0]

    assert duty.report_time_utc <= duty.segments[0].scheduled_departure_utc


def test_same_day_flight_is_unchanged(parser, tmp_path):
    """The rollover guard must not disturb ordinary daytime sectors."""
    csv = write_csv(tmp_path, """
        2026-03-05,QR200,DOH,DOH,08:00,11:00,07:00,11:30
    """)
    roster = parser.parse_csv(csv, pilot_id='P1', month='2026-03')
    duty = roster.duties[0]
    segment = duty.segments[0]

    block = (segment.scheduled_arrival_utc -
             segment.scheduled_departure_utc).total_seconds() / 3600
    assert block == pytest.approx(3.0)
    assert duty.duty_hours == pytest.approx(4.5)


def test_release_follows_last_arrival(parser, tmp_path):
    csv = write_csv(tmp_path, """
        2026-03-05,QR300,DOH,DOH,21:00,01:00,20:00,01:30
    """)
    roster = parser.parse_csv(csv, pilot_id='P1', month='2026-03')
    duty = roster.duties[0]

    assert duty.release_time_utc >= duty.segments[-1].scheduled_arrival_utc
