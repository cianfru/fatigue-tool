#!/usr/bin/env python3
"""
Test that post-duty sleep is included in the simulation's sleep blocks
"""

from datetime import datetime
import pytz
from data_models import Duty, Roster, FlightSegment, Airport
from core_model import BorbelyFatigueModel, ModelConfig

def test_post_duty_in_simulation():
    """Test that post-duty sleep appears in simulation sleep blocks"""
    
    print("=" * 80)
    print("Testing Post-Duty Sleep in Full Simulation")
    print("=" * 80)
    
    # Home base timezone
    home_tz = pytz.timezone('Europe/Rome')
    layover_tz = pytz.timezone('Asia/Dubai')
    
    # Create airports
    rome = Airport(code='FCO', timezone='Europe/Rome')
    dubai = Airport(code='DXB', timezone='Asia/Dubai')
    
    # Night flight from Rome to Dubai
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
    
    # Return flight
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
    
    roster = Roster(
        roster_id='TEST_ROSTER_001',
        pilot_id='TEST001',
        month='2024-02',
        duties=[duty1, duty2],
        pilot_base='FCO',
        home_base_timezone='Europe/Rome'
    )
    
    config = ModelConfig.default_easa_config()
    model = BorbelyFatigueModel(config=config)
    
    # Access the internal _extract_sleep_from_roster method
    body_clock_timeline = [(duty1.report_time_utc, None)]
    
    print("\nExtracting sleep from roster...")
    sleep_blocks, sleep_strategies = model._extract_sleep_from_roster(roster, body_clock_timeline)
    
    print(f"\nTotal sleep blocks generated: {len(sleep_blocks)}")
    
    # Filter for sleep in the post-duty window
    duty1_release_utc = duty1.release_time_utc
    duty2_report_utc = duty2.report_time_utc
    
    print(f"\nLooking for post-duty sleep between:")
    print(f"  Duty 1 release: {duty1_release_utc.strftime('%Y-%m-%d %H:%M %Z')}")
    print(f"  Duty 2 report:  {duty2_report_utc.strftime('%Y-%m-%d %H:%M %Z')}")
    
    print("\n--- ALL SLEEP BLOCKS ---")
    post_duty_found = False
    
    for i, block in enumerate(sleep_blocks):
        dubai_tz = pytz.timezone(block.location_timezone)
        start_local = block.start_utc.astimezone(dubai_tz)
        end_local = block.end_utc.astimezone(dubai_tz)
        
        print(f"\nBlock {i+1}:")
        print(f"  Start: {block.start_utc.strftime('%Y-%m-%d %H:%M %Z')}")
        print(f"  End:   {block.end_utc.strftime('%Y-%m-%d %H:%M %Z')}")
        print(f"  Local: {start_local.strftime('%H:%M')} - {end_local.strftime('%H:%M')} {dubai_tz}")
        print(f"  Duration: {block.duration_hours:.2f}h")
        print(f"  Environment: {block.environment}")
        print(f"  Timezone: {block.location_timezone}")
        
        # Check if in post-duty window
        if duty1_release_utc <= block.start_utc <= duty2_report_utc:
            if block.environment == 'hotel':
                print(f"  >>> POST-DUTY HOTEL SLEEP <<<")
                post_duty_found = True
    
    print("\n" + "=" * 80)
    if post_duty_found:
        print("✓ TEST PASSED: Post-duty hotel sleep found in sleep blocks")
    else:
        print("✗ TEST FAILED: No post-duty hotel sleep in sleep blocks")
    print("=" * 80)
    
    return post_duty_found

if __name__ == '__main__':
    test_post_duty_in_simulation()
