#!/usr/bin/env python3
"""
Visual Timeline Generator
==========================

Creates ASCII-art timelines showing sleep/wake/duty cycles
"""

from datetime import datetime, timedelta
import pytz
from typing import List
from enhanced_models import EnhancedRoster, RosterDay, SleepWindow


def create_24h_timeline(day: RosterDay, width: int = 60) -> List[str]:
    """
    Create 24-hour visual timeline for a single day
    
    Shows:
    - Sleep periods (████)
    - Awake periods (░░░░)
    - Duty periods (✈✈✈✈)
    - WOCL (Window of Circadian Low) highlight
    """
    lines = []
    
    # Header
    date_str = day.date.strftime("%b %d (%a)")
    type_str = day.day_type.value.upper()
    lines.append("┌" + "─" * (width - 2) + "┐")
    lines.append(f"│ {date_str} - {type_str}" + " " * (width - len(date_str) - len(type_str) - 6) + "│")
    lines.append("├" + "─" * (width - 2) + "┤")
    
    # Create 24-hour bar
    bar_width = width - 14  # Leave space for labels
    timeline = ['░'] * bar_width  # Default: awake
    
    tz = pytz.timezone(day.location_timezone)
    day_start = tz.localize(datetime(
        day.date.year, day.date.month, day.date.day, 0, 0, 0
    ))
    day_end = day_start + timedelta(days=1)
    
    # Mark sleep periods
    for window in day.sleep_windows:
        start_local = window.start_local
        end_local = window.end_local
        
        # Calculate positions in the bar
        start_hour = start_local.hour + start_local.minute / 60
        end_hour = end_local.hour + end_local.minute / 60
        
        # Handle wrap-around (sleep crossing midnight)
        if end_hour < start_hour:
            end_hour += 24
        
        start_pos = int((start_hour / 24) * bar_width)
        end_pos = int((end_hour / 24) * bar_width)
        
        # Fill in sleep
        for i in range(start_pos, min(end_pos, bar_width)):
            timeline[i] = '█'
    
    # Mark duty periods
    if day.is_duty and day.report_time_utc and day.release_time_utc:
        report_local = day.report_time_utc.astimezone(tz)
        release_local = day.release_time_utc.astimezone(tz)
        
        report_hour = report_local.hour + report_local.minute / 60
        release_hour = release_local.hour + release_local.minute / 60
        
        if release_hour < report_hour:
            release_hour += 24
        
        report_pos = int((report_hour / 24) * bar_width)
        release_pos = int((release_hour / 24) * bar_width)
        
        # Mark duty (overwrite sleep if overlapping - shouldn't happen)
        for i in range(report_pos, min(release_pos, bar_width)):
            timeline[i] = '✈'
    
    # Build the visual line
    timeline_str = "".join(timeline)
    lines.append(f"│ 00:00 {timeline_str} 24:00 │")
    
    # Legend
    has_sleep = any(c == '█' for c in timeline)
    has_duty = any(c == '✈' for c in timeline)
    
    legend_parts = []
    if has_sleep:
        legend_parts.append("█ Sleep")
    if has_duty:
        legend_parts.append("✈ Duty")
    if not has_sleep and not has_duty:
        legend_parts.append("░ Awake")
    
    legend = " │ ".join(legend_parts)
    lines.append(f"│ {legend}" + " " * (width - len(legend) - 4) + "│")
    
    # Sleep summary
    if day.sleep_windows:
        for window in day.sleep_windows:
            start = window.start_local.strftime("%H:%M")
            end = window.end_local.strftime("%H:%M")
            effective = window.effective_sleep_hours
            emoji = "🏠" if window.environment == "home" else "🏨"
            summary = f"{emoji} {start}-{end} → {effective:.1f}h"
            lines.append(f"│ {summary}" + " " * (width - len(summary) - 4) + "│")
    
    # Duty summary
    if day.is_duty and day.report_time_utc:
        report = day.report_time_utc.astimezone(tz).strftime("%H:%M")
        release = day.release_time_utc.astimezone(tz).strftime("%H:%M")
        duration = (day.release_time_utc - day.report_time_utc).total_seconds() / 3600
        
        if day.segments:
            route = f"{day.segments[0].departure_airport.code}→{day.segments[-1].arrival_airport.code}"
            summary = f"✈️  {report}-{release} ({duration:.1f}h) {route}"
        else:
            summary = f"✈️  {report}-{release} ({duration:.1f}h)"
        
        lines.append(f"│ {summary}" + " " * (width - len(summary) - 4) + "│")
    
    # Footer
    lines.append("└" + "─" * (width - 2) + "┘")
    
    return lines


def create_roster_timeline(roster: EnhancedRoster, width: int = 60):
    """
    Create complete roster timeline
    """
    print()
    print("=" * width)
    print("VISUAL ROSTER TIMELINE")
    print("=" * width)
    print()
    
    for day in roster.days:
        timeline = create_24h_timeline(day, width)
        for line in timeline:
            print(line)
        print()


def create_sleep_quality_chart(roster: EnhancedRoster):
    """
    Bar chart showing sleep quality across days
    """
    print()
    print("=" * 60)
    print("SLEEP QUALITY BY DAY")
    print("=" * 60)
    print()
    
    for day in roster.days:
        date_str = day.date.strftime("%b %d")
        sleep_hours = day.get_total_sleep_hours()
        
        # Create bar
        max_bar = 40
        bar_length = int((sleep_hours / 10) * max_bar)
        bar = "█" * bar_length
        
        # Color indicator
        if sleep_hours >= 7.5:
            status = "✓"
        elif sleep_hours >= 6.0:
            status = "○"
        else:
            status = "⚠"
        
        print(f"{date_str} {status} │{bar:<{max_bar}}│ {sleep_hours:.1f}h")
    
    print()
    print("Legend: ✓ Good (≥7.5h) │ ○ Adequate (6-7.5h) │ ⚠ Poor (<6h)")
    print()


def create_fatigue_heatmap(roster: EnhancedRoster, analysis):
    """
    Heatmap showing fatigue risk across month
    """
    print()
    print("=" * 60)
    print("FATIGUE RISK HEATMAP")
    print("=" * 60)
    print()
    
    # Map duty IDs to timeline results
    duty_map = {dt.duty_id: dt for dt in analysis.duty_timelines}
    
    for day in roster.days:
        date_str = day.date.strftime("%b %d")
        
        if day.is_duty and day.duty_id in duty_map:
            timeline = duty_map[day.duty_id]
            perf = timeline.landing_performance if timeline.landing_performance else timeline.min_performance
            
            # Risk level
            if perf >= 75:
                risk = "LOW"
                emoji = "🟢"
                bar_char = "░"
            elif perf >= 65:
                risk = "MOD"
                emoji = "🟡"
                bar_char = "▒"
            elif perf >= 55:
                risk = "HIGH"
                emoji = "🟠"
                bar_char = "▓"
            else:
                risk = "CRIT"
                emoji = "🔴"
                bar_char = "█"
            
            # Performance bar
            bar_length = int((perf / 100) * 30)
            bar = bar_char * bar_length
            
            print(f"{date_str} {emoji} │{bar:<30}│ {perf:>5.1f}/100 ({risk})")
        
        elif day.is_off:
            print(f"{date_str} 💤 OFF")
    
    print()
    print("Legend: 🟢 Low │ 🟡 Moderate │ 🟠 High │ 🔴 Critical")
    print()


# Demo
if __name__ == "__main__":
    from demo_improved_sleep import demonstrate_sleep_editing
    from enhanced_models import EnhancedRoster, DayType
    from data_models import Airport, FlightSegment
    from core_model import BorbelyFatigueModel
    
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
    
    # Add days
    roster.add_off_day(datetime(2024, 1, 15), "Asia/Qatar")
    
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
    
    roster.add_off_day(datetime(2024, 1, 17), "Europe/London")
    
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
    
    roster.add_off_day(datetime(2024, 1, 19), "Asia/Qatar")
    roster.add_off_day(datetime(2024, 1, 20), "Asia/Qatar")
    
    # Generate sleep
    roster.auto_generate_sleep_windows()
    
    # Show timeline
    create_roster_timeline(roster)
    
    # Show sleep chart
    create_sleep_quality_chart(roster)
    
    # Run analysis
    old_roster = roster.export_for_analysis()
    model = BorbelyFatigueModel()
    analysis = model.simulate_roster(old_roster)
    
    # Show heatmap
    create_fatigue_heatmap(roster, analysis)
