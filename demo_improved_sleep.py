#!/usr/bin/env python3
"""
Improved Roster Analyzer with Sleep Window Visualization
=========================================================

Shows:
1. Day-by-day roster (duties AND off days)
2. Assumed sleep windows (editable by user)
3. Visual timeline of sleep/wake cycles
"""

from datetime import datetime, timedelta
import pytz

from enhanced_models import EnhancedRoster, DayType, SleepWindow
from data_models import Airport, FlightSegment
from core_model import BorbelyFatigueModel
from easa_utils import FatigueRiskScorer, BiomathematicalSleepEstimator
from config import ModelConfig


def print_sleep_timeline(roster: EnhancedRoster):
    """
    Visual timeline showing sleep/wake periods
    
    Example output:
    Jan 15 (Duty DOH→LHR):
      Sleep: 23:00-07:00 (8h window) → 6.8h effective ✓
      Report: 04:30 | Duty: 8.5h | Release: 13:00
      Sleep: None (quick turn)
    
    Jan 16 (OFF):
      Sleep: 23:00-07:00 (8h window) → 7.2h effective ✓
    """
    print("=" * 70)
    print("SLEEP/WAKE TIMELINE")
    print("=" * 70)
    print()
    
    for day in roster.days:
        print(f"📅 {day.summary_line}")
        
        if day.is_duty:
            # Show duty timing
            report = day.report_time_utc.astimezone(pytz.timezone(day.location_timezone))
            release = day.release_time_utc.astimezone(pytz.timezone(day.location_timezone))
            duty_hours = (day.release_time_utc - day.report_time_utc).total_seconds() / 3600
            
            print(f"   ✈️  Report: {report.strftime('%H:%M LT')} | " +
                  f"Duty: {duty_hours:.1f}h | " +
                  f"Release: {release.strftime('%H:%M LT')}")
        
        # Show sleep windows
        if day.sleep_windows:
            for i, window in enumerate(day.sleep_windows, 1):
                print(f"   💤 {window.display_summary}")
                
                # Show if user can edit
                if window.window_type == "automatic":
                    print(f"      (Auto-estimated - you can modify this)")
        else:
            print(f"   ⚠️  No sleep opportunity")
        
        print()


def print_day_comparison(roster: EnhancedRoster):
    """
    Table view comparing sleep across days
    """
    print("=" * 70)
    print("DAY-BY-DAY SLEEP SUMMARY")
    print("=" * 70)
    print()
    print(f"{'Date':<12} {'Type':<8} {'Sleep Hrs':<12} {'Quality':<10} {'Status':<15}")
    print("─" * 70)
    
    for day in roster.days:
        date_str = day.date.strftime("%b %d")
        type_str = day.day_type.value.upper()
        
        total_sleep = day.get_total_sleep_hours()
        
        # Quality indicator
        if total_sleep >= 7.5:
            quality = "Good ✓"
        elif total_sleep >= 6.0:
            quality = "Adequate"
        else:
            quality = "Poor ⚠️"
        
        # Status
        if day.is_duty:
            status = "Flying"
        elif day.is_off:
            status = "Resting"
        else:
            status = "-"
        
        print(f"{date_str:<12} {type_str:<8} {total_sleep:>5.1f}h      {quality:<10} {status:<15}")
    
    print()


def demonstrate_sleep_editing():
    """
    Show how user can edit sleep windows
    """
    print("=" * 70)
    print("SLEEP WINDOW EDITING DEMO")
    print("=" * 70)
    print()
    
    # Create sample roster
    doh = Airport("DOH", "Asia/Qatar", 25.273056, 51.608056)
    lhr = Airport("LHR", "Europe/London", 51.4700, -0.4543)
    
    roster = EnhancedRoster(
        roster_id="JAN2024",
        pilot_id="P12345",
        month="2024-01",
        home_base_timezone="Asia/Qatar",
        typical_sleep_need_hours=8.0,
        typical_bedtime_local="23:00",
        typical_wake_time_local="07:00"
    )
    
    # Add some days
    print("Building sample roster...")
    
    # Day 1: OFF (at home)
    roster.add_off_day(datetime(2024, 1, 15), "Asia/Qatar")
    
    # Day 2: DUTY (DOH→LHR)
    segment1 = FlightSegment(
        flight_number="QR001",
        departure_airport=doh,
        arrival_airport=lhr,
        scheduled_departure_utc=datetime(2024, 1, 16, 2, 30, tzinfo=pytz.utc),
        scheduled_arrival_utc=datetime(2024, 1, 16, 9, 0, tzinfo=pytz.utc)
    )
    roster.add_duty_day(
        date=datetime(2024, 1, 16),
        duty_id="D001",
        report_time_utc=datetime(2024, 1, 16, 1, 30, tzinfo=pytz.utc),
        release_time_utc=datetime(2024, 1, 16, 10, 0, tzinfo=pytz.utc),
        segments=[segment1]
    )
    
    # Day 3: OFF (layover in London)
    roster.add_off_day(datetime(2024, 1, 17), "Europe/London")
    
    # Day 4: DUTY (LHR→DOH)
    segment2 = FlightSegment(
        flight_number="QR002",
        departure_airport=lhr,
        arrival_airport=doh,
        scheduled_departure_utc=datetime(2024, 1, 18, 14, 0, tzinfo=pytz.utc),
        scheduled_arrival_utc=datetime(2024, 1, 18, 23, 30, tzinfo=pytz.utc)
    )
    roster.add_duty_day(
        date=datetime(2024, 1, 18),
        duty_id="D002",
        report_time_utc=datetime(2024, 1, 18, 13, 0, tzinfo=pytz.utc),
        release_time_utc=datetime(2024, 1, 19, 0, 30, tzinfo=pytz.utc),
        segments=[segment2]
    )
    
    # Day 5-6: OFF (back home)
    roster.add_off_day(datetime(2024, 1, 19), "Asia/Qatar")
    roster.add_off_day(datetime(2024, 1, 20), "Asia/Qatar")
    
    print(f"✓ Created {len(roster.days)} days")
    print()
    
    # Auto-generate sleep windows
    print("Auto-generating sleep windows...")
    roster.auto_generate_sleep_windows()
    print("✓ Sleep windows created")
    print()
    
    # Display the timeline
    print_sleep_timeline(roster)
    
    # Show day comparison
    print_day_comparison(roster)
    
    # Show roster summary
    summary = roster.get_summary()
    print("=" * 70)
    print("ROSTER SUMMARY")
    print("=" * 70)
    print(f"Total days: {summary['total_days']}")
    print(f"Duty days: {summary['duty_days']}")
    print(f"OFF days: {summary['off_days']}")
    print(f"Average sleep: {summary['average_sleep_per_day']:.1f}h/day")
    print()
    
    # Demonstrate editing
    print("=" * 70)
    print("EDITING SLEEP WINDOWS")
    print("=" * 70)
    print()
    print("Example: User modifies Jan 16 post-duty sleep")
    print()
    
    # Find Jan 16 (first duty)
    jan16 = [d for d in roster.days if d.date.day == 16][0]
    
    if jan16.sleep_windows:
        original = jan16.sleep_windows[0]
        print(f"Original (auto): {original.display_summary}")
        
        # User says: "Actually, I got hotel at 12:00 and slept until 20:00"
        original.user_specified_duration_hours = 6.5
        original.user_notes = "Hotel check-in delayed, but slept well"
        original.window_type = "user_edited"
        
        # Recalculate effective sleep
        original.effective_sleep_hours = original.user_specified_duration_hours * original.quality_factor
        
        print(f"User edit:       {original.display_summary}")
        print(f"User notes:      \"{original.user_notes}\"")
        print()
    
    print("✓ Sleep window updated!")
    print()
    print("In the full app, users would:")
    print("  1. Click on any sleep window")
    print("  2. Adjust start/end times with sliders")
    print("  3. Rate sleep quality (1-5 stars)")
    print("  4. Add notes")
    print("  5. Re-run fatigue analysis with updated data")
    print()
    
    # Now run fatigue analysis
    print("=" * 70)
    print("RUNNING FATIGUE ANALYSIS")
    print("=" * 70)
    print()
    
    # Convert to old format
    old_roster = roster.export_for_analysis()
    
    # Add sleep blocks manually (since we have enhanced sleep windows)
    from data_models import SleepBlock
    sleep_blocks = []
    for day in roster.days:
        for window in day.sleep_windows:
            sleep_blocks.append(window.to_sleep_block())
    
    print(f"Analyzing with {len(sleep_blocks)} sleep periods...")
    
    # Run model
    model = BorbelyFatigueModel()
    analysis = model.simulate_roster(old_roster)
    
    print("✓ Analysis complete")
    print()
    
    # Show results
    for timeline in analysis.duty_timelines:
        print(f"Duty {timeline.duty_id}:")
        print(f"  Landing performance: {timeline.landing_performance:.1f}/100")
        print(f"  Sleep debt: {timeline.cumulative_sleep_debt:.1f}h")
        print()


if __name__ == "__main__":
    demonstrate_sleep_editing()
    
    print("=" * 70)
    print("KEY IMPROVEMENTS")
    print("=" * 70)
    print()
    print("✅ OFF days are now explicit (not just gaps)")
    print("✅ Sleep windows are visible and clearly shown")
    print("✅ Users can see EXACTLY what assumptions are being made")
    print("✅ Users can edit sleep windows to match reality")
    print("✅ Day-by-day timeline makes roster easy to understand")
    print()
    print("This is the foundation for a much better UI!")
