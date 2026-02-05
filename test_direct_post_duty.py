#!/usr/bin/env python3
"""
Direct test of _generate_post_duty_sleep function
"""

from datetime import datetime
import pytz
from data_models import Duty, FlightSegment, Airport
from core_model import BorbelyFatigueModel, ModelConfig

def test_generate_post_duty_sleep():
    """Test _generate_post_duty_sleep directly"""
    
    print("=" * 80)
    print("Direct Test of _generate_post_duty_sleep")
    print("=" * 80)
    
    config = ModelConfig.default_easa_config()
    model = BorbelyFatigueModel(config=config)
    
    # Create a night flight duty arriving in Dubai (hotel layover)
    home_tz = pytz.timezone('Europe/Rome')
    layover_tz = pytz.timezone('Asia/Dubai')
    
    rome = Airport(code='FCO', timezone='Europe/Rome')
    dubai = Airport(code='DXB', timezone='Asia/Dubai')
    
    # Night flight: depart Rome 23:00, arrive Dubai 06:00 next day (local times)
    duty1_report = home_tz.localize(datetime(2024, 2, 23, 22, 0))
    duty1_start = home_tz.localize(datetime(2024, 2, 23, 23, 0))
    duty1_end = layover_tz.localize(datetime(2024, 2, 24, 6, 0))
    duty1_release = layover_tz.localize(datetime(2024, 2, 24, 6, 30))
    
    segment1 = FlightSegment(
        flight_number='QR123',
        departure_airport=rome,
        arrival_airport=dubai,
        scheduled_departure_utc=duty1_start.astimezone(pytz.utc),
        scheduled_arrival_utc=duty1_end.astimezone(pytz.utc)
    )
    
    duty1 = Duty(
        duty_id='duty_1',
        date=datetime(2024, 2, 23).date(),
        report_time_utc=duty1_report.astimezone(pytz.utc),
        release_time_utc=duty1_release.astimezone(pytz.utc),
        segments=[segment1],
        home_base_timezone='Europe/Rome'
    )
    
    # Return flight (next duty)
    duty2_report = layover_tz.localize(datetime(2024, 2, 25, 5, 0))
    duty2_start = layover_tz.localize(datetime(2024, 2, 25, 6, 0))
    duty2_end = home_tz.localize(datetime(2024, 2, 25, 10, 0))
    duty2_release = home_tz.localize(datetime(2024, 2, 25, 10, 30))
    
    segment2 = FlightSegment(
        flight_number='QR124',
        departure_airport=dubai,
        arrival_airport=rome,
        scheduled_departure_utc=duty2_start.astimezone(pytz.utc),
        scheduled_arrival_utc=duty2_end.astimezone(pytz.utc)
    )
    
    duty2 = Duty(
        duty_id='duty_2',
        date=datetime(2024, 2, 25).date(),
        report_time_utc=duty2_report.astimezone(pytz.utc),
        release_time_utc=duty2_release.astimezone(pytz.utc),
        segments=[segment2],
        home_base_timezone='Europe/Rome'
    )
    
    print("\nDUTY DETAILS:")
    print(f"Duty 1:")
    print(f"  Route: {rome.code} -> {dubai.code}")
    print(f"  Release: {duty1_release.strftime('%Y-%m-%d %H:%M %Z')} (local)")
    print(f"  Release UTC: {duty1_release.astimezone(pytz.utc).strftime('%Y-%m-%d %H:%M %Z')}")
    print(f"  Arrival hour (local): {duty1_release.hour}")
    print(f"  Home base: FCO")
    print(f"  Arrival airport: {dubai.code}")
    print(f"  Is home base? {dubai.code == 'FCO'}")
    
    print(f"\nDuty 2:")
    print(f"  Report: {duty2_report.strftime('%Y-%m-%d %H:%M %Z')} (local)")
    print(f"  Report UTC: {duty2_report.astimezone(pytz.utc).strftime('%Y-%m-%d %H:%M %Z')}")
    
    # Call _generate_post_duty_sleep
    print("\n" + "=" * 80)
    print("Calling _generate_post_duty_sleep...")
    print("=" * 80)
    
    post_duty_sleep = model._generate_post_duty_sleep(
        duty=duty1,
        next_duty=duty2,
        home_timezone='Europe/Rome',
        home_base='FCO'
    )
    
    if post_duty_sleep:
        print("\n✓ POST-DUTY SLEEP WAS GENERATED:")
        print(f"  Start UTC: {post_duty_sleep.start_utc.strftime('%Y-%m-%d %H:%M %Z')}")
        print(f"  End UTC:   {post_duty_sleep.end_utc.strftime('%Y-%m-%d %H:%M %Z')}")
        
        # Convert to Dubai time for clarity
        dubai_tz = pytz.timezone('Asia/Dubai')
        start_local = post_duty_sleep.start_utc.astimezone(dubai_tz)
        end_local = post_duty_sleep.end_utc.astimezone(dubai_tz)
        
        print(f"  Start Dubai: {start_local.strftime('%Y-%m-%d %H:%M %Z')}")
        print(f"  End Dubai:   {end_local.strftime('%Y-%m-%d %H:%M %Z')}")
        print(f"  Duration: {post_duty_sleep.duration_hours:.2f}h")
        print(f"  Effective: {post_duty_sleep.effective_sleep_hours:.2f}h")
        print(f"  Quality: {post_duty_sleep.quality_factor:.1%}")
        print(f"  Environment: {post_duty_sleep.environment}")
        print(f"  Location timezone: {post_duty_sleep.location_timezone}")
        
        print("\n✓ TEST PASSED")
        return True
    else:
        print("\n✗ POST-DUTY SLEEP WAS NOT GENERATED")
        print("  This indicates the function returned None")
        print("\n✗ TEST FAILED")
        return False

if __name__ == '__main__':
    test_generate_post_duty_sleep()
