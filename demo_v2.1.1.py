#!/usr/bin/env python3
"""
V2.1.1 Feature Demonstration
=============================

Showcases the operational enhancements added in version 2.1.1:
- Airport distance & timezone calculations
- Inflight rest support for ULH flights
- Roster helper methods
- Enhanced PerformancePoint properties
"""

from datetime import datetime
import pytz

from config import ModelConfig
from data_models import Airport, FlightSegment, Duty, Roster
from core_model import BorbelyFatigueModel
from easa_utils import FatigueRiskScorer

print("=" * 70)
print("V2.1.1 FEATURE DEMONSTRATION")
print("=" * 70)
print()

# ============================================================================
# FEATURE 1: Airport Distance & Timezone Calculations
# ============================================================================

print("─" * 70)
print("FEATURE 1: Airport Distance & Timezone Calculations")
print("─" * 70)
print()

doh = Airport("DOH", "Asia/Qatar", 25.273056, 51.608056)
lhr = Airport("LHR", "Europe/London", 51.4700, -0.4543)
jfk = Airport("JFK", "America/New_York", 40.6413, -73.7781)
sin = Airport("SIN", "Asia/Singapore", 1.3644, 103.9915)

# Distance calculations
distance_doh_lhr = doh.great_circle_distance(lhr)
distance_lhr_jfk = lhr.great_circle_distance(jfk)
distance_lhr_sin = lhr.great_circle_distance(sin)

print(f"DOH → LHR: {distance_doh_lhr:,.0f} km")
print(f"LHR → JFK: {distance_lhr_jfk:,.0f} km")
print(f"LHR → SIN: {distance_lhr_sin:,.0f} km (Ultra-Long-Haul)")
print()

# Timezone differences
ref_time = datetime(2024, 1, 15, 12, 0, tzinfo=pytz.utc)
tz_diff_doh_lhr = doh.timezone_difference_hours(lhr, ref_time)
tz_diff_lhr_jfk = lhr.timezone_difference_hours(jfk, ref_time)

print(f"DOH → LHR: {tz_diff_doh_lhr:+.0f}h timezone shift")
print(f"LHR → JFK: {tz_diff_lhr_jfk:+.0f}h timezone shift")
print()

# ============================================================================
# FEATURE 2: ULH Flight Detection & Inflight Rest
# ============================================================================

print("─" * 70)
print("FEATURE 2: ULH Flight Detection & Inflight Rest")
print("─" * 70)
print()

# Create a ULH flight (LHR → SIN, ~13 hours)
ulh_departure = datetime(2024, 1, 20, 22, 0, tzinfo=pytz.utc)
ulh_arrival = datetime(2024, 1, 21, 14, 0, tzinfo=pytz.utc)

ulh_segment = FlightSegment(
    flight_number="BA12",
    departure_airport=lhr,
    arrival_airport=sin,
    scheduled_departure_utc=ulh_departure,
    scheduled_arrival_utc=ulh_arrival
)

# Check if ULH
is_ulh = FatigueRiskScorer.is_ulh_flight(ulh_segment)
block_time = (ulh_arrival - ulh_departure).total_seconds() / 3600

print(f"Flight BA12 (LHR → SIN)")
print(f"  Block time: {block_time:.1f} hours")
print(f"  Ultra-Long-Haul: {'YES ✈️' if is_ulh else 'No'}")
print()

# Estimate inflight rest opportunity
rest_window = FatigueRiskScorer.estimate_inflight_rest_opportunity(
    ulh_segment,
    crew_complement="augmented"
)

if rest_window:
    rest_start, rest_end = rest_window
    rest_duration = (rest_end - rest_start).total_seconds() / 3600
    effective_recovery = rest_duration * 0.65  # Inflight rest ~65% effective
    
    print(f"Inflight Rest Opportunity (Augmented Crew):")
    print(f"  Window: {rest_start.strftime('%H:%M')} - {rest_end.strftime('%H:%M')} UTC")
    print(f"  Duration: {rest_duration:.1f} hours")
    print(f"  Effective recovery: ~{effective_recovery:.1f}h (65% quality)")
print()

# ============================================================================
# FEATURE 3: Roster Helper Methods
# ============================================================================

print("─" * 70)
print("FEATURE 3: Roster Helper Methods")
print("─" * 70)
print()

# Create a sample roster with multiple duties
duty1 = Duty(
    duty_id="D001",
    date=datetime(2024, 1, 15),
    report_time_utc=datetime(2024, 1, 15, 1, 30, tzinfo=pytz.utc),
    release_time_utc=datetime(2024, 1, 15, 10, 0, tzinfo=pytz.utc),
    segments=[FlightSegment(
        flight_number="QR001",
        departure_airport=doh,
        arrival_airport=lhr,
        scheduled_departure_utc=datetime(2024, 1, 15, 2, 30, tzinfo=pytz.utc),
        scheduled_arrival_utc=datetime(2024, 1, 15, 9, 0, tzinfo=pytz.utc)
    )],
    home_base_timezone="Asia/Qatar"
)

duty2 = Duty(
    duty_id="D002",
    date=datetime(2024, 1, 16),
    report_time_utc=datetime(2024, 1, 16, 13, 0, tzinfo=pytz.utc),  # 27h rest
    release_time_utc=datetime(2024, 1, 16, 20, 30, tzinfo=pytz.utc),
    segments=[FlightSegment(
        flight_number="QR002",
        departure_airport=lhr,
        arrival_airport=doh,
        scheduled_departure_utc=datetime(2024, 1, 16, 14, 0, tzinfo=pytz.utc),
        scheduled_arrival_utc=datetime(2024, 1, 16, 19, 30, tzinfo=pytz.utc)
    )],
    home_base_timezone="Asia/Qatar"
)

roster = Roster(
    roster_id="JAN2024",
    pilot_id="P12345",
    month="2024-01",
    duties=[duty1, duty2],
    home_base_timezone="Asia/Qatar"
)

# Test duty lookup
found_duty = roster.get_duty_by_id("D002")
print(f"Found duty: {found_duty.duty_id if found_duty else 'None'}")
print()

# Test rest period calculation
rest_before_d2 = roster.get_rest_period_before("D002")
if rest_before_d2:
    rest_hours = rest_before_d2.total_seconds() / 3600
    print(f"Rest before D002: {rest_hours:.1f} hours")
    
    if rest_hours < 12:
        print(f"  ⚠️  Below minimum (12h)")
    elif rest_hours < 24:
        print(f"  ⚠️  Limited recovery opportunity")
    else:
        print(f"  ✓ Adequate rest")
print()

# Get summary statistics
stats = roster.get_summary_statistics()
print("Roster Summary:")
print(f"  Total duties: {stats['total_duties']}")
print(f"  Total sectors: {stats['total_sectors']}")
print(f"  Total block hours: {stats['total_block_hours']:.1f}h")
print(f"  Total duty hours: {stats['total_duty_hours']:.1f}h")
print(f"  Disruptive duties: {stats['disruptive_duties']}")
print()

# ============================================================================
# FEATURE 4: Enhanced PerformancePoint Properties
# ============================================================================

print("─" * 70)
print("FEATURE 4: Enhanced PerformancePoint Properties")
print("─" * 70)
print()

# Run analysis to get performance points
model = BorbelyFatigueModel()
analysis = model.simulate_roster(roster)
timeline = analysis.duty_timelines[0]

# Get a sample performance point (at minimum performance)
min_point = None
for point in timeline.timeline:
    if point.raw_performance == timeline.min_performance:
        min_point = point
        break

if min_point:
    print("Performance Point at Minimum (worst state):")
    print(f"  Time: {min_point.timestamp_utc.strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"  Raw performance: {min_point.raw_performance:.1f}/100")
    print()
    
    # NEW: Convenience properties
    print("  Component Breakdown:")
    print(f"    Circadian alertness: {min_point.circadian_alertness:.1f}%")
    print(f"    Sleep pressure: {min_point.sleep_pressure_percentage:.1f}%")
    print(f"    Sleep inertia: {min_point.sleep_inertia_percentage:.1f}%")
    print(f"    Total impairment: {min_point.total_impairment:.2f}")
    print()
    
    # NEW: Component breakdown dict (useful for export)
    breakdown = min_point.get_component_breakdown()
    print("  Full Breakdown (for CSV export):")
    for key, value in breakdown.items():
        if key not in ['timestamp_utc', 'timestamp_local']:
            print(f"    {key}: {value}")

print()
print("=" * 70)
print("V2.1.1 Features Demonstrated Successfully! ✓")
print("=" * 70)
print()
print("These enhancements make the tool more operationally relevant:")
print("  • Route classification by distance")
print("  • ULH flight support with inflight rest")
print("  • Easy roster analysis with helper methods")
print("  • Better data export capabilities")
