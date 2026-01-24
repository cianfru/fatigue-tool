#!/usr/bin/env python3
"""
Simple Example - Test Your Fatigue Analysis System
===================================================

This script demonstrates basic functionality with a simple duty.
Use this to verify the system works before trying complex rosters.
"""

from datetime import datetime, timedelta
import pytz

# Import your modules
from config import ModelConfig
from data_models import Airport, FlightSegment, Duty, Roster
from core_model import BorbelyFatigueModel
from easa_utils import FatigueRiskScorer

def main():
    print("=" * 70)
    print("EASA Fatigue Analysis - Simple Example")
    print("=" * 70)
    print()
    
    # ========================================================================
    # DEFINE A SIMPLE DUTY - DOH to LHR
    # ========================================================================
    
    print("Creating sample duty: DOH → LHR...")
    
    # Define airports
    doh = Airport("DOH", "Asia/Qatar", 25.273056, 51.608056)
    lhr = Airport("LHR", "Europe/London", 51.4700, -0.4543)
    
    # Create flight segment
    departure_time = datetime(2024, 1, 18, 2, 30, tzinfo=pytz.utc)  # 02:30 UTC
    arrival_time = datetime(2024, 1, 18, 9, 0, tzinfo=pytz.utc)     # 09:00 UTC
    
    segment = FlightSegment(
        flight_number="QR001",
        departure_airport=doh,
        arrival_airport=lhr,
        scheduled_departure_utc=departure_time,
        scheduled_arrival_utc=arrival_time
    )
    
    # Create duty (with 1h pre-flight, 1h post-flight)
    duty = Duty(
        duty_id="D001",
        date=datetime(2024, 1, 18),
        report_time_utc=departure_time - pytz.utc.localize(datetime(1970, 1, 1, 1, 0)).replace(tzinfo=None).astimezone(pytz.utc).utcoffset(),
        release_time_utc=arrival_time + pytz.utc.localize(datetime(1970, 1, 1, 1, 0)).replace(tzinfo=None).astimezone(pytz.utc).utcoffset(),
        segments=[segment],
        home_base_timezone="Asia/Qatar"
    )
    
    # Simpler duty creation
    report_time = departure_time - timedelta(hours=1)
    release_time = arrival_time + timedelta(hours=1)
    
    duty = Duty(
        duty_id="D001", 
        date=datetime(2024, 1, 18),
        report_time_utc=report_time,
        release_time_utc=release_time,
        segments=[segment],
        home_base_timezone="Asia/Qatar"
    )
    
    # Create roster with this single duty
    roster = Roster(
        roster_id="R001",
        pilot_id="P12345",
        month="2024-01",
        duties=[duty],
        home_base_timezone="Asia/Qatar"
    )
    
    print(f"  Departure: {departure_time.strftime('%Y-%m-%d %H:%M')} UTC")
    print(f"  Arrival:   {arrival_time.strftime('%Y-%m-%d %H:%M')} UTC")
    print(f"  Duration:  {(arrival_time - departure_time).total_seconds() / 3600:.1f} hours")
    print()
    
    # ========================================================================
    # RUN FATIGUE ANALYSIS
    # ========================================================================
    
    print("Running biomathematical fatigue analysis...")
    
    # Initialize model
    model = BorbelyFatigueModel(config=ModelConfig.default_easa_config())
    
    # Run simulation
    analysis = model.simulate_roster(roster)
    
    print("✓ Analysis complete")
    print()
    
    # ========================================================================
    # DISPLAY RESULTS
    # ========================================================================
    
    timeline = analysis.duty_timelines[0]
    
    print("─" * 70)
    print("PERFORMANCE METRICS")
    print("─" * 70)
    print(f"  Minimum Performance:     {timeline.min_performance:.1f}/100")
    print(f"  Landing Performance:     {timeline.landing_performance:.1f}/100")
    print(f"  Cumulative Sleep Debt:   {timeline.cumulative_sleep_debt:.1f} hours")
    print(f"  WOCL Encroachment:       {timeline.wocl_encroachment_hours:.1f} hours")
    print()
    
    # ========================================================================
    # RISK ASSESSMENT
    # ========================================================================
    
    scorer = FatigueRiskScorer()
    risk = scorer.score_duty_timeline(timeline)
    
    print("─" * 70)
    print("RISK ASSESSMENT")
    print("─" * 70)
    print(f"  Overall Risk Level:      {risk['overall_risk'].upper()}")
    print(f"  Recommended Action:      {risk['recommended_action']}")
    print(f"  EASA Reference:          {risk['easa_reference'] or 'N/A'}")
    print(f"  SMS Reportable:          {'YES ⚠️' if risk['is_reportable'] else 'No'}")
    print()
    
    if risk['additional_warnings']:
        print("⚠️  WARNINGS:")
        for warning in risk['additional_warnings']:
            print(f"    • {warning}")
        print()
    
    if timeline.pinch_events:
        print("⚠️  PINCH EVENTS DETECTED:")
        for event in timeline.pinch_events:
            print(f"    • {str(event)}")
        print()
    
    # ========================================================================
    # SUMMARY
    # ========================================================================
    
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    
    risk_emoji = {
        'low': '✅',
        'moderate': '⚠️ ',
        'high': '⛔',
        'critical': '🚨',
        'extreme': '🔴'
    }
    
    emoji = risk_emoji.get(risk['overall_risk'], '❓')
    
    print(f"{emoji}  This duty has {risk['overall_risk'].upper()} fatigue risk")
    print(f"    Landing performance predicted at {timeline.landing_performance:.1f}/100")
    print()
    print("Next Steps:")
    if risk['is_reportable']:
        print("  1. File proactive fatigue report with SMS")
        print("  2. Request roster modification if possible")
        print("  3. Discuss fatigue mitigation with crew scheduling")
    else:
        print("  1. No immediate action required")
        print("  2. Monitor your actual fatigue levels")
        print("  3. Use controlled rest if needed during flight")
    
    print()
    print("=" * 70)
    print("✈️  Analysis complete!")
    print("=" * 70)

if __name__ == "__main__":
    main()
