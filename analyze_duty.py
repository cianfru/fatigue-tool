#!/usr/bin/env python3
"""
Interactive Duty Analyzer - Command Line Interface
==================================================

Quick fatigue analysis for single duties via command line.
For full roster analysis, use the web interface (streamlit run fatigue_app.py)
"""

from datetime import datetime, timedelta
import pytz
import sys

from config import ModelConfig
from data_models import Airport, FlightSegment, Duty, Roster
from core_model import BorbelyFatigueModel
from easa_utils import FatigueRiskScorer

# Common airports database
AIRPORTS = {
    "DOH": Airport("DOH", "Asia/Qatar", 25.273056, 51.608056),
    "LHR": Airport("LHR", "Europe/London", 51.4700, -0.4543),
    "JFK": Airport("JFK", "America/New_York", 40.6413, -73.7781),
    "DXB": Airport("DXB", "Asia/Dubai", 25.2532, 55.3657),
    "SIN": Airport("SIN", "Asia/Singapore", 1.3644, 103.9915),
    "HKG": Airport("HKG", "Asia/Hong_Kong", 22.3080, 113.9185),
    "SYD": Airport("SYD", "Australia/Sydney", -33.9399, 151.1753),
    "LAX": Airport("LAX", "America/Los_Angeles", 33.9416, -118.4085),
    "FRA": Airport("FRA", "Europe/Berlin", 50.0379, 8.5622),
    "CDG": Airport("CDG", "Europe/Paris", 49.0097, 2.5479),
    "BKK": Airport("BKK", "Asia/Bangkok", 13.6900, 100.7501),
    "ICN": Airport("ICN", "Asia/Seoul", 37.4602, 126.4407),
    "NRT": Airport("NRT", "Asia/Tokyo", 35.7653, 140.3860),
    "PEK": Airport("PEK", "Asia/Shanghai", 40.0799, 116.6031),
    "ORD": Airport("ORD", "America/Chicago", 41.9742, -87.9073),
    "IAD": Airport("IAD", "America/New_York", 38.9531, -77.4565),
    "YYZ": Airport("YYZ", "America/Toronto", 43.6777, -79.6248),
    "MEL": Airport("MEL", "Australia/Melbourne", -37.6690, 144.8410),
}


def get_airport(prompt="Enter airport code (e.g., DOH, LHR): "):
    """Get airport from user input"""
    while True:
        code = input(prompt).strip().upper()
        if code in AIRPORTS:
            return AIRPORTS[code]
        else:
            print(f"❌ Unknown airport code: {code}")
            print(f"Available: {', '.join(sorted(AIRPORTS.keys()))}")


def get_datetime(prompt):
    """Get datetime from user input"""
    while True:
        try:
            print(f"\n{prompt}")
            date_str = input("  Date (YYYY-MM-DD): ").strip()
            time_str = input("  Time (HH:MM, UTC): ").strip()
            
            dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
            return pytz.utc.localize(dt)
        except ValueError as e:
            print(f"❌ Invalid date/time format. Please try again.")


def main():
    print("=" * 70)
    print("EASA Fatigue Analysis - Interactive Duty Analyzer")
    print("=" * 70)
    print()
    print("This tool analyzes a SINGLE duty for fatigue risk.")
    print("For monthly roster analysis, use: streamlit run fatigue_app.py")
    print()
    
    # Get home base
    print("─" * 70)
    print("STEP 1: Home Base")
    print("─" * 70)
    home_base = get_airport("Enter your home base airport: ")
    print(f"✓ Home base: {home_base.code} ({home_base.timezone})")
    print()
    
    # Get flight details
    print("─" * 70)
    print("STEP 2: Flight Details")
    print("─" * 70)
    
    flight_number = input("Flight number (e.g., QR001): ").strip()
    
    print("\nDeparture:")
    dep_airport = get_airport("  Airport code: ")
    dep_time = get_datetime("  Departure time")
    
    print("\nArrival:")
    arr_airport = get_airport("  Airport code: ")
    arr_time = get_datetime("  Arrival time")
    
    # Calculate flight duration
    duration = (arr_time - dep_time).total_seconds() / 3600
    print(f"\n✓ Flight duration: {duration:.1f} hours")
    print()
    
    # Get duty times
    print("─" * 70)
    print("STEP 3: Duty Times")
    print("─" * 70)
    print("(Typically: report 1h before departure, release 1h after arrival)")
    print()
    
    use_default = input("Use default times (+/-1h)? [Y/n]: ").strip().lower()
    
    if use_default != 'n':
        report_time = dep_time - timedelta(hours=1)
        release_time = arr_time + timedelta(hours=1)
    else:
        report_time = get_datetime("Report time")
        release_time = get_datetime("Release time")
    
    duty_hours = (release_time - report_time).total_seconds() / 3600
    print(f"\n✓ Total duty time: {duty_hours:.1f} hours")
    print()
    
    # Model configuration
    print("─" * 70)
    print("STEP 4: Model Configuration")
    print("─" * 70)
    print("1. Default (recommended - balanced EASA approach)")
    print("2. Conservative (stricter - better for safety advocacy)")
    print("3. Liberal (lenient - mirrors airline assumptions)")
    print()
    
    config_choice = input("Select configuration [1-3, default=1]: ").strip()
    
    if config_choice == "2":
        config = ModelConfig.conservative_config()
        config_name = "Conservative"
    elif config_choice == "3":
        config = ModelConfig.liberal_config()
        config_name = "Liberal"
    else:
        config = ModelConfig.default_easa_config()
        config_name = "Default EASA"
    
    print(f"✓ Using {config_name} configuration")
    print()
    
    # Build duty
    print("─" * 70)
    print("Running Analysis...")
    print("─" * 70)
    
    segment = FlightSegment(
        flight_number=flight_number,
        departure_airport=dep_airport,
        arrival_airport=arr_airport,
        scheduled_departure_utc=dep_time,
        scheduled_arrival_utc=arr_time
    )
    
    duty = Duty(
        duty_id="D001",
        date=dep_time.date(),
        report_time_utc=report_time,
        release_time_utc=release_time,
        segments=[segment],
        home_base_timezone=home_base.timezone
    )
    
    roster = Roster(
        roster_id="R001",
        pilot_id="PILOT",
        month=dep_time.strftime("%Y-%m"),
        duties=[duty],
        home_base_timezone=home_base.timezone
    )
    
    # Run analysis
    model = BorbelyFatigueModel(config=config)
    analysis = model.simulate_roster(roster)
    timeline = analysis.duty_timelines[0]
    
    print("✓ Analysis complete")
    print()
    
    # Display results
    print("=" * 70)
    print("RESULTS")
    print("=" * 70)
    print()
    
    # Flight summary
    print("Flight Summary:")
    print(f"  {flight_number}: {dep_airport.code} → {arr_airport.code}")
    print(f"  Departure: {dep_time.strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"  Arrival:   {arr_time.strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"  Duration:  {duration:.1f}h flight, {duty_hours:.1f}h duty")
    print()
    
    # Performance metrics
    print("Performance Metrics:")
    print(f"  Landing Performance:     {timeline.landing_performance:>5.1f}/100")
    print(f"  Minimum Performance:     {timeline.min_performance:>5.1f}/100")
    print(f"  Average Performance:     {timeline.average_performance:>5.1f}/100")
    print(f"  Cumulative Sleep Debt:   {timeline.cumulative_sleep_debt:>5.1f}h")
    print(f"  WOCL Encroachment:       {timeline.wocl_encroachment_hours:>5.1f}h")
    print()
    
    # Risk assessment
    scorer = FatigueRiskScorer()
    risk = scorer.score_duty_timeline(timeline)
    
    risk_emoji = {
        'low': '✅',
        'moderate': '⚠️ ',
        'high': '⛔',
        'critical': '🚨',
        'extreme': '🔴'
    }
    
    emoji = risk_emoji.get(risk['overall_risk'], '❓')
    
    print("Risk Assessment:")
    print(f"  Overall Risk:      {emoji} {risk['overall_risk'].upper()}")
    print(f"  Recommended:       {risk['recommended_action']}")
    if risk['easa_reference']:
        print(f"  EASA Reference:    {risk['easa_reference']}")
    print(f"  SMS Reportable:    {'YES ⚠️ ' if risk['is_reportable'] else 'No'}")
    print()
    
    if risk['additional_warnings']:
        print("⚠️  Additional Warnings:")
        for warning in risk['additional_warnings']:
            print(f"  • {warning}")
        print()
    
    if timeline.pinch_events:
        print("⚠️  Pinch Events Detected:")
        for event in timeline.pinch_events[:5]:  # Show first 5
            print(f"  • {str(event)}")
        if len(timeline.pinch_events) > 5:
            print(f"  ... and {len(timeline.pinch_events) - 5} more")
        print()
    
    # Summary
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print()
    print(f"{emoji}  This duty has {risk['overall_risk'].upper()} fatigue risk")
    print(f"    Landing performance predicted at {timeline.landing_performance:.1f}/100")
    print()
    
    if risk['is_reportable']:
        print("⚠️  RECOMMENDED ACTIONS:")
        print("  1. File proactive SMS fatigue report")
        print("  2. Request roster modification if possible")
        print("  3. Discuss mitigation with crew scheduling")
        print("  4. Consider controlled rest during cruise")
    else:
        print("✓ No immediate action required")
        print("  • Monitor your actual fatigue levels during duty")
        print("  • Use controlled rest if needed")
    
    print()
    print("─" * 70)
    print("For detailed visualizations and full roster analysis:")
    print("  streamlit run fatigue_app.py")
    print("=" * 70)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nAnalysis cancelled by user.")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
