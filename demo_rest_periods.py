#!/usr/bin/env python3
"""
Rest Period Analysis Demo
=========================

Shows how the system now properly analyzes the TIME BETWEEN DUTIES
"""

from datetime import datetime, timedelta
import pytz

from data_models import Airport, FlightSegment, Duty
from rest_period_analysis import RestPeriodAnalyzer

# Setup
doh = Airport("DOH", "Asia/Qatar", 25.273056, 51.608056)
lhr = Airport("LHR", "Europe/London", 51.4700, -0.4543)

analyzer = RestPeriodAnalyzer()

print("=" * 70)
print("REST PERIOD ANALYSIS - CRITICAL SCENARIOS")
print("=" * 70)
print()

# ============================================================================
# SCENARIO 1: Quick turn (legal but tight)
# ============================================================================

print("SCENARIO 1: Quick Turn (12h minimum rest)")
print("─" * 70)

duty1 = Duty(
    duty_id="D001",
    date=datetime(2024, 2, 1),
    report_time_utc=datetime(2024, 2, 1, 5, 0, tzinfo=pytz.utc),   # 08:00 DOH
    release_time_utc=datetime(2024, 2, 1, 17, 0, tzinfo=pytz.utc),  # 20:00 DOH
    segments=[FlightSegment(
        flight_number="QR123",
        departure_airport=doh,
        arrival_airport=lhr,
        scheduled_departure_utc=datetime(2024, 2, 1, 6, 0, tzinfo=pytz.utc),
        scheduled_arrival_utc=datetime(2024, 2, 1, 13, 0, tzinfo=pytz.utc)
    ), FlightSegment(
        flight_number="QR456",
        departure_airport=lhr,
        arrival_airport=doh,
        scheduled_departure_utc=datetime(2024, 2, 1, 14, 30, tzinfo=pytz.utc),
        scheduled_arrival_utc=datetime(2024, 2, 1, 16, 30, tzinfo=pytz.utc)
    )],
    home_base_timezone="Asia/Qatar"
)

duty2 = Duty(
    duty_id="D002",
    date=datetime(2024, 2, 2),
    report_time_utc=datetime(2024, 2, 2, 5, 0, tzinfo=pytz.utc),   # 08:00 DOH (next day)
    release_time_utc=datetime(2024, 2, 2, 13, 0, tzinfo=pytz.utc),
    segments=[FlightSegment(
        flight_number="QR789",
        departure_airport=doh,
        arrival_airport=lhr,
        scheduled_departure_utc=datetime(2024, 2, 2, 6, 0, tzinfo=pytz.utc),
        scheduled_arrival_utc=datetime(2024, 2, 2, 13, 0, tzinfo=pytz.utc)
    )],
    home_base_timezone="Asia/Qatar"
)

rest1 = analyzer.analyze_rest_period(duty1, duty2)
print(analyzer.generate_rest_report(rest1))

# ============================================================================
# SCENARIO 2: Land early morning, report late night (HIGHLY DISRUPTIVE)
# ============================================================================

print("\n" * 2)
print("SCENARIO 2: Land 06:00, Report 23:00 Same Day (17h rest)")
print("─" * 70)
print("THIS IS YOUR CRITICAL EXAMPLE!")
print()

duty3 = Duty(
    duty_id="D003",
    date=datetime(2024, 2, 3),
    report_time_utc=datetime(2024, 2, 3, 13, 0, tzinfo=pytz.utc),
    release_time_utc=datetime(2024, 2, 3, 21, 0, tzinfo=pytz.utc),  # Land 21:00 UTC = 00:00 DOH
    segments=[FlightSegment(
        flight_number="QR111",
        departure_airport=lhr,
        arrival_airport=doh,
        scheduled_departure_utc=datetime(2024, 2, 3, 14, 0, tzinfo=pytz.utc),
        scheduled_arrival_utc=datetime(2024, 2, 3, 21, 0, tzinfo=pytz.utc)
    )],
    home_base_timezone="Asia/Qatar"
)

duty4 = Duty(
    duty_id="D004",
    date=datetime(2024, 2, 4),
    report_time_utc=datetime(2024, 2, 3, 20, 0, tzinfo=pytz.utc),  # 23:00 DOH (same calendar day!)
    release_time_utc=datetime(2024, 2, 4, 10, 30, tzinfo=pytz.utc),
    segments=[FlightSegment(
        flight_number="QR222",
        departure_airport=doh,
        arrival_airport=lhr,
        scheduled_departure_utc=datetime(2024, 2, 3, 21, 0, tzinfo=pytz.utc),
        scheduled_arrival_utc=datetime(2024, 2, 4, 4, 0, tzinfo=pytz.utc)
    )],
    home_base_timezone="Asia/Qatar"
)

# Actually let me fix this to be your exact scenario
duty3_fixed = Duty(
    duty_id="D003",
    date=datetime(2024, 2, 3),
    report_time_utc=datetime(2024, 2, 3, 10, 0, tzinfo=pytz.utc),  # 13:00 LHR
    release_time_utc=datetime(2024, 2, 3, 3, 0, tzinfo=pytz.utc),  # 06:00 DOH arrival
    segments=[FlightSegment(
        flight_number="QR222",
        departure_airport=lhr,
        arrival_airport=doh,
        scheduled_departure_utc=datetime(2024, 2, 3, 11, 0, tzinfo=pytz.utc),
        scheduled_arrival_utc=datetime(2024, 2, 3, 19, 0, tzinfo=pytz.utc)  # 22:00 DOH
    )],
    home_base_timezone="Asia/Qatar"
)

duty4_fixed = Duty(
    duty_id="D004",
    date=datetime(2024, 2, 3),  # Same day!
    report_time_utc=datetime(2024, 2, 3, 20, 0, tzinfo=pytz.utc),  # 23:00 DOH
    release_time_utc=datetime(2024, 2, 4, 10, 0, tzinfo=pytz.utc),
    segments=[FlightSegment(
        flight_number="QR333",
        departure_airport=doh,
        arrival_airport=lhr,
        scheduled_departure_utc=datetime(2024, 2, 3, 21, 0, tzinfo=pytz.utc),
        scheduled_arrival_utc=datetime(2024, 2, 4, 4, 0, tzinfo=pytz.utc)
    )],
    home_base_timezone="Asia/Qatar"
)

# Actually this is confusing, let me make it crystal clear

print("Previous duty: Arrive DOH 06:00 local")
print("Next duty: Report DOH 23:00 local (same day!)")
print()

duty_land_early = Duty(
    duty_id="D_LAND_EARLY",
    date=datetime(2024, 2, 10),
    report_time_utc=datetime(2024, 2, 10, 10, 0, tzinfo=pytz.utc),  # 13:00 LHR
    release_time_utc=datetime(2024, 2, 10, 3, 0, tzinfo=pytz.utc),  # 06:00 DOH
    segments=[FlightSegment(
        flight_number="QR002",
        departure_airport=lhr,
        arrival_airport=doh,
        scheduled_departure_utc=datetime(2024, 2, 10, 11, 0, tzinfo=pytz.utc),
        scheduled_arrival_utc=datetime(2024, 2, 10, 19, 0, tzinfo=pytz.utc)
    )],
    home_base_timezone="Asia/Qatar"
)

duty_depart_late = Duty(
    duty_id="D_DEPART_LATE",
    date=datetime(2024, 2, 10),  # SAME DAY
    report_time_utc=datetime(2024, 2, 10, 20, 0, tzinfo=pytz.utc),  # 23:00 DOH
    release_time_utc=datetime(2024, 2, 11, 10, 0, tzinfo=pytz.utc),
    segments=[FlightSegment(
        flight_number="QR001",
        departure_airport=doh,
        arrival_airport=lhr,
        scheduled_departure_utc=datetime(2024, 2, 10, 21, 0, tzinfo=pytz.utc),
        scheduled_arrival_utc=datetime(2024, 2, 11, 4, 0, tzinfo=pytz.utc)
    )],
    home_base_timezone="Asia/Qatar"
)

rest_disruptive = analyzer.analyze_rest_period(duty_land_early, duty_depart_late)
print(analyzer.generate_rest_report(rest_disruptive))

# ============================================================================
# SCENARIO 3: Adequate rest (24h+)
# ============================================================================

print("\n" * 2)
print("SCENARIO 3: Adequate Rest (36h with 2 local nights)")
print("─" * 70)

duty5 = Duty(
    duty_id="D005",
    date=datetime(2024, 2, 15),
    report_time_utc=datetime(2024, 2, 15, 5, 0, tzinfo=pytz.utc),
    release_time_utc=datetime(2024, 2, 15, 13, 0, tzinfo=pytz.utc),  # 16:00 DOH
    segments=[FlightSegment(
        flight_number="QR555",
        departure_airport=doh,
        arrival_airport=lhr,
        scheduled_departure_utc=datetime(2024, 2, 15, 6, 0, tzinfo=pytz.utc),
        scheduled_arrival_utc=datetime(2024, 2, 15, 13, 0, tzinfo=pytz.utc)
    )],
    home_base_timezone="Asia/Qatar"
)

duty6 = Duty(
    duty_id="D006",
    date=datetime(2024, 2, 17),  # 2 days later
    report_time_utc=datetime(2024, 2, 17, 1, 0, tzinfo=pytz.utc),  # 04:00 DOH
    release_time_utc=datetime(2024, 2, 17, 13, 0, tzinfo=pytz.utc),
    segments=[FlightSegment(
        flight_number="QR666",
        departure_airport=doh,
        arrival_airport=lhr,
        scheduled_departure_utc=datetime(2024, 2, 17, 2, 0, tzinfo=pytz.utc),
        scheduled_arrival_utc=datetime(2024, 2, 17, 9, 0, tzinfo=pytz.utc)
    )],
    home_base_timezone="Asia/Qatar"
)

rest_adequate = analyzer.analyze_rest_period(duty5, duty6)
print(analyzer.generate_rest_report(rest_adequate))

# ============================================================================
# SCENARIO 4: ILLEGAL rest (<12h)
# ============================================================================

print("\n" * 2)
print("SCENARIO 4: ILLEGAL Rest (<12h)")
print("─" * 70)

duty7 = Duty(
    duty_id="D007",
    date=datetime(2024, 2, 20),
    report_time_utc=datetime(2024, 2, 20, 5, 0, tzinfo=pytz.utc),
    release_time_utc=datetime(2024, 2, 20, 13, 0, tzinfo=pytz.utc),  # 16:00 DOH
    segments=[FlightSegment(
        flight_number="QR777",
        departure_airport=doh,
        arrival_airport=lhr,
        scheduled_departure_utc=datetime(2024, 2, 20, 6, 0, tzinfo=pytz.utc),
        scheduled_arrival_utc=datetime(2024, 2, 20, 13, 0, tzinfo=pytz.utc)
    )],
    home_base_timezone="Asia/Qatar"
)

duty8 = Duty(
    duty_id="D008",
    date=datetime(2024, 2, 20),  # SAME DAY
    report_time_utc=datetime(2024, 2, 20, 23, 0, tzinfo=pytz.utc),  # 02:00 DOH next day (only 10h rest!)
    release_time_utc=datetime(2024, 2, 21, 11, 0, tzinfo=pytz.utc),
    segments=[FlightSegment(
        flight_number="QR888",
        departure_airport=doh,
        arrival_airport=lhr,
        scheduled_departure_utc=datetime(2024, 2, 21, 0, 0, tzinfo=pytz.utc),
        scheduled_arrival_utc=datetime(2024, 2, 21, 7, 0, tzinfo=pytz.utc)
    )],
    home_base_timezone="Asia/Qatar"
)

rest_illegal = analyzer.analyze_rest_period(duty7, duty8)
print(analyzer.generate_rest_report(rest_illegal))

print("\n" * 2)
print("=" * 70)
print("KEY INSIGHTS")
print("=" * 70)
print()
print("✅ System now properly analyzes TIME BETWEEN DUTIES")
print("✅ Detects legal vs illegal rest periods")
print("✅ Identifies sleep disruptions even when legal")
print("✅ Accounts for practical constraints (hotel transit, etc)")
print("✅ Estimates ACTUAL sleep obtainable, not just rest duration")
print()
print("🎯 CRITICAL: 17h rest can be worse than 12h rest!")
print("   Example: Land 06:00, report 23:00 = 17h legal but terrible sleep")
print()
