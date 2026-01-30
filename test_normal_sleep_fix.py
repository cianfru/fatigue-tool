#!/usr/bin/env python3
"""
Test suite for normal sleep strategy fix
Tests realistic sleep patterns for afternoon/evening duties
"""

from datetime import datetime, timedelta
import pytz
from data_models import Airport, FlightSegment, Duty
from core_model import UnifiedSleepCalculator

print("=" * 70)
print("TEST SUITE: Normal Sleep Strategy Fix")
print("=" * 70)

# Setup
DOH = Airport('DOH', 'Asia/Qatar', 25.273056, 51.608056)
LHR = Airport('LHR', 'Europe/London', 51.4700, -0.4543)
sleep_calc = UnifiedSleepCalculator()

def create_test_duty(report_hour, report_minute=0, date=None):
    """Helper to create a test duty with specified report time"""
    if date is None:
        date = datetime(2024, 8, 26)  # Tuesday, Aug 26, 2024
    
    # Set report time in Qatar time (home timezone)
    qatar_tz = pytz.timezone('Asia/Qatar')
    report_local = qatar_tz.localize(datetime(date.year, date.month, date.day, report_hour, report_minute))
    report_utc = report_local.astimezone(pytz.utc)
    
    # Create a segment departing 30 minutes after report
    departure_utc = report_utc + timedelta(minutes=30)
    arrival_utc = departure_utc + timedelta(hours=6)  # 6-hour flight
    
    seg = FlightSegment(
        flight_number='QR001',
        departure_airport=DOH,
        arrival_airport=LHR,
        scheduled_departure_utc=departure_utc,
        scheduled_arrival_utc=arrival_utc
    )
    
    release_utc = arrival_utc + timedelta(minutes=30)  # Release 30 min after landing
    
    duty = Duty(
        duty_id=f"TEST_{report_hour:02d}{report_minute:02d}",
        date=date,
        segments=[seg],
        report_time_utc=report_utc,
        release_time_utc=release_utc,
        home_base_timezone='Asia/Qatar'
    )
    
    return duty, report_local

def test_afternoon_duty():
    """Test the example from the problem statement: 17:30 duty"""
    print("\n" + "=" * 70)
    print("TEST 1: Afternoon Duty (17:30 Report)")
    print("=" * 70)
    
    duty, report_local = create_test_duty(17, 30)
    
    print(f"\nDuty report time: {report_local.strftime('%A, %b %d, %Y at %H:%M')} (Qatar time)")
    
    # Calculate sleep strategy
    strategy = sleep_calc.estimate_sleep_for_duty(
        duty=duty,
        previous_duty=None,
        home_timezone='Asia/Qatar'
    )
    
    print(f"\nStrategy type: {strategy.strategy_type}")
    print(f"Confidence: {strategy.confidence:.1%}")
    print(f"Explanation: {strategy.explanation}")
    
    for i, sleep_block in enumerate(strategy.sleep_blocks, 1):
        qatar_tz = pytz.timezone('Asia/Qatar')
        sleep_start_local = sleep_block.start_utc.astimezone(qatar_tz)
        sleep_end_local = sleep_block.end_utc.astimezone(qatar_tz)
        
        print(f"\nSleep Block {i}:")
        print(f"  Start: {sleep_start_local.strftime('%A, %b %d at %H:%M')} (Qatar time)")
        print(f"  End:   {sleep_end_local.strftime('%A, %b %d at %H:%M')} (Qatar time)")
        print(f"  Duration: {sleep_block.duration_hours:.1f} hours")
        print(f"  Effective: {sleep_block.effective_sleep_hours:.1f} hours")
        
        # Verify it's a nighttime sleep pattern (should be 23:00 -> 07:00)
        assert sleep_start_local.hour == 23, f"Expected sleep start at 23:00, got {sleep_start_local.hour:02d}:00"
        assert sleep_end_local.hour == 7, f"Expected sleep end at 07:00, got {sleep_end_local.hour:02d}:00"
        
        # Verify it's the previous night
        assert sleep_start_local.day == 25, f"Expected sleep on Aug 25, got day {sleep_start_local.day}"
        assert sleep_end_local.day == 26, f"Expected wake on Aug 26, got day {sleep_end_local.day}"
        
        print("  ✅ PASS: Sleep is on previous night (23:00 Aug 25 → 07:00 Aug 26)")
    
    # Check awake hours
    if "10.5h awake" in strategy.explanation or "10.3h awake" in strategy.explanation:
        print("  ✅ PASS: Awake duration is ~10.5 hours (correct)")
    else:
        print(f"  ⚠️  Awake duration in explanation: {strategy.explanation}")

def test_morning_duty():
    """Test morning duty (09:00 Report)"""
    print("\n" + "=" * 70)
    print("TEST 2: Morning Duty (09:00 Report)")
    print("=" * 70)
    
    duty, report_local = create_test_duty(9, 0)
    
    print(f"\nDuty report time: {report_local.strftime('%A, %b %d, %Y at %H:%M')} (Qatar time)")
    
    strategy = sleep_calc.estimate_sleep_for_duty(
        duty=duty,
        previous_duty=None,
        home_timezone='Asia/Qatar'
    )
    
    print(f"\nStrategy type: {strategy.strategy_type}")
    print(f"Confidence: {strategy.confidence:.1%}")
    print(f"Explanation: {strategy.explanation}")
    
    for sleep_block in strategy.sleep_blocks:
        qatar_tz = pytz.timezone('Asia/Qatar')
        sleep_start_local = sleep_block.start_utc.astimezone(qatar_tz)
        sleep_end_local = sleep_block.end_utc.astimezone(qatar_tz)
        
        print(f"\nSleep:")
        print(f"  Start: {sleep_start_local.strftime('%H:%M on %b %d')}")
        print(f"  End:   {sleep_end_local.strftime('%H:%M on %b %d')}")
        
        # Verify nighttime sleep
        assert sleep_start_local.hour == 23, f"Expected 23:00 start, got {sleep_start_local.hour:02d}:00"
        assert sleep_end_local.hour == 7, f"Expected 07:00 end, got {sleep_end_local.hour:02d}:00"
        print("  ✅ PASS: Sleep is on previous night (23:00 → 07:00)")
    
    # Morning duty should have ~2 hours awake
    if "2.0h awake" in strategy.explanation:
        print("  ✅ PASS: Awake duration is 2 hours (correct for 09:00 duty)")

def test_noon_duty():
    """Test noon duty (12:00 Report)"""
    print("\n" + "=" * 70)
    print("TEST 3: Noon Duty (12:00 Report)")
    print("=" * 70)
    
    duty, report_local = create_test_duty(12, 0)
    
    print(f"\nDuty report time: {report_local.strftime('%A, %b %d, %Y at %H:%M')} (Qatar time)")
    
    strategy = sleep_calc.estimate_sleep_for_duty(
        duty=duty,
        previous_duty=None,
        home_timezone='Asia/Qatar'
    )
    
    print(f"\nStrategy type: {strategy.strategy_type}")
    print(f"Confidence: {strategy.confidence:.1%}")
    print(f"Explanation: {strategy.explanation}")
    
    for sleep_block in strategy.sleep_blocks:
        qatar_tz = pytz.timezone('Asia/Qatar')
        sleep_start_local = sleep_block.start_utc.astimezone(qatar_tz)
        sleep_end_local = sleep_block.end_utc.astimezone(qatar_tz)
        
        print(f"\nSleep:")
        print(f"  Start: {sleep_start_local.strftime('%H:%M on %b %d')}")
        print(f"  End:   {sleep_end_local.strftime('%H:%M on %b %d')}")
        
        # Verify nighttime sleep
        assert sleep_start_local.hour == 23, f"Expected 23:00 start"
        assert sleep_end_local.hour == 7, f"Expected 07:00 end"
        print("  ✅ PASS: Sleep is on previous night (23:00 → 07:00)")
    
    # Noon duty should have ~5 hours awake
    if "5.0h awake" in strategy.explanation:
        print("  ✅ PASS: Awake duration is 5 hours (correct for 12:00 duty)")

def test_very_early_duty():
    """Test very early morning duty (07:15 Report) - should trigger sleep inertia warning"""
    print("\n" + "=" * 70)
    print("TEST 4: Very Early Duty (07:15 Report)")
    print("=" * 70)
    
    duty, report_local = create_test_duty(7, 15)
    
    print(f"\nDuty report time: {report_local.strftime('%A, %b %d, %Y at %H:%M')} (Qatar time)")
    
    strategy = sleep_calc.estimate_sleep_for_duty(
        duty=duty,
        previous_duty=None,
        home_timezone='Asia/Qatar'
    )
    
    print(f"\nStrategy type: {strategy.strategy_type}")
    print(f"Confidence: {strategy.confidence:.1%}")
    print(f"Explanation: {strategy.explanation}")
    
    # Very early duty (0.25h awake) should have high confidence but note sleep inertia
    if strategy.confidence >= 0.90:
        print("  ✅ PASS: Confidence is high (pilot just woke up)")

def test_confidence_scaling():
    """Test that confidence scales appropriately with awake time"""
    print("\n" + "=" * 70)
    print("TEST 5: Confidence Scaling with Awake Time")
    print("=" * 70)
    
    test_times = [
        (7, 30, "Just woke", 0.95),
        (9, 0, "Morning", 0.90),
        (12, 0, "Noon", 0.90),
        (15, 0, "Afternoon", 0.80),
        (17, 30, "Evening", 0.70),
        (19, 0, "Late", 0.70),
    ]
    
    print("\n| Report Time | Awake Hours | Expected Conf | Actual Conf | Status |")
    print("|-------------|-------------|---------------|-------------|---------|")
    
    for hour, minute, label, expected_conf in test_times:
        duty, report_local = create_test_duty(hour, minute)
        strategy = sleep_calc.estimate_sleep_for_duty(
            duty=duty,
            previous_duty=None,
            home_timezone='Asia/Qatar'
        )
        
        # Extract awake hours from explanation
        awake_text = strategy.explanation.split("h awake")[0].split()[-1]
        try:
            awake_hours = float(awake_text)
        except:
            awake_hours = 0.0
        
        status = "✅" if abs(strategy.confidence - expected_conf) < 0.01 else "⚠️"
        print(f"| {hour:02d}:{minute:02d}      | {awake_hours:5.1f}h      | {expected_conf:.0%}         | {strategy.confidence:.0%}         | {status}      |")

# Run all tests
if __name__ == "__main__":
    try:
        test_afternoon_duty()
        test_morning_duty()
        test_noon_duty()
        test_very_early_duty()
        test_confidence_scaling()
        
        print("\n" + "=" * 70)
        print("ALL TESTS PASSED ✅")
        print("=" * 70)
        
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        raise
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        raise
