#!/usr/bin/env python3
"""
Test post-duty sleep generation, especially after night flights and at hotel layovers.
"""

from datetime import datetime, timezone as dt_timezone
import pytz
from data_models import Duty, Roster, FlightSegment, Airport
from core_model import BorbelyFatigueModel, ModelConfig

def create_test_roster_with_layover():
    """Create a roster with a night flight arriving at a hotel layover."""
    
    # Home base timezone
    home_tz = pytz.timezone('Europe/Rome')
    layover_tz = pytz.timezone('Asia/Dubai')
    
    # Create airports
    rome = Airport(code='FCO', timezone='Europe/Rome')
    dubai = Airport(code='DXB', timezone='Asia/Dubai')
    
    # Night flight from Rome to Dubai
    # Depart Rome at 23:00, arrive Dubai at 06:00 next day (local times)
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
    
    # Return flight Dubai to Rome (24 hours later)
    # This confirms it's a layover scenario
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
    
    return roster

def test_post_duty_sleep_generation():
    """Test that post-duty sleep is generated after night flight at hotel."""
    
    print("=" * 80)
    print("Testing Post-Duty Sleep Generation After Night Flight")
    print("=" * 80)
    
    roster = create_test_roster_with_layover()
    config = ModelConfig.default_easa_config()
    model = BorbelyFatigueModel(config=config)
    
    # Run simulation
    analysis = model.simulate_roster(roster)
    
    # Print all duties
    print("\n--- DUTIES ---")
    for duty in roster.duties:
        local_tz = pytz.timezone(duty.segments[0].departure_airport.timezone)
        report_local = duty.report_time_utc.astimezone(local_tz)
        release_local = duty.release_time_utc.astimezone(local_tz)
        arrival_airport = duty.segments[-1].arrival_airport
        
        print(f"\nDuty ID: {duty.duty_id}")
        print(f"  Route: {duty.segments[0].departure_airport.code} -> {arrival_airport.code}")
        print(f"  Report: {report_local.strftime('%Y-%m-%d %H:%M %Z')}")
        print(f"  Release: {release_local.strftime('%Y-%m-%d %H:%M %Z')}")
        print(f"  Arrival hour (local): {release_local.hour}")
    
    # Extract all sleep blocks from analysis
    print("\n--- ALL SLEEP BLOCKS ---")
    
    # Check the sleep_strategies dictionary which contains all generated sleep
    if hasattr(model, 'sleep_strategies') and model.sleep_strategies:
        for duty_id, strategy in model.sleep_strategies.items():
            print(f"\n{duty_id}:")
            print(f"  Strategy: {strategy.get('strategy_type')}")
            sleep_blocks_info = strategy.get('sleep_blocks', [])
            print(f"  Sleep blocks: {len(sleep_blocks_info)}")
            
            for i, block in enumerate(sleep_blocks_info):
                print(f"    Block {i+1}: {block['sleep_start_time']} - {block['sleep_end_time']}")
                print(f"      ISO: {block['sleep_start_iso']}")
                print(f"      Type: {block['sleep_type']}")
                print(f"      Duration: {block['duration_hours']:.2f}h")
                print(f"      Effective: {block['effective_hours']:.2f}h")
                print(f"      Quality: {block['quality_factor']:.1%}")
    
    # Check for sleep blocks that fall AFTER duty 1 release
    duty1_release = roster.duties[0].release_time_utc
    duty2_report = roster.duties[1].report_time_utc
    
    print("\n--- POST-DUTY SLEEP ANALYSIS ---")
    print(f"Looking for sleep between:")
    print(f"  Duty 1 release: {duty1_release.strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"  Duty 2 report:  {duty2_report.strftime('%Y-%m-%d %H:%M UTC')}")
    
    post_duty_sleep_found = False
    
    # Iterate through all strategies to find post-duty sleep
    if hasattr(model, 'sleep_strategies') and model.sleep_strategies:
        for duty_id, strategy in model.sleep_strategies.items():
            for block in strategy.get('sleep_blocks', []):
                sleep_start = datetime.fromisoformat(block['sleep_start_iso'])
                sleep_end = datetime.fromisoformat(block['sleep_end_iso'])
                
                # Check if this sleep block is in the gap between duties
                # Make times timezone-aware for comparison
                if not sleep_start.tzinfo:
                    continue
                if not sleep_end.tzinfo:
                    continue
                    
                # Check if this sleep block is in the gap between duties
                if sleep_start >= duty1_release and sleep_end <= duty2_report:
                    print(f"\n✓ POST-DUTY SLEEP FOUND (in {duty_id}):")
                    print(f"  Start: {block['sleep_start_iso']}")
                    print(f"  End:   {block['sleep_end_iso']}")
                    print(f"  Duration: {block['duration_hours']:.2f}h")
                    print(f"  Effective: {block['effective_hours']:.2f}h")
                    print(f"  Type: {block['sleep_type']}")
                    post_duty_sleep_found = True
    
    if not post_duty_sleep_found:
        print("\n✗ NO POST-DUTY SLEEP FOUND IN THE GAP!")
        print("  This indicates a bug in sleep generation.")
    
    # Final verdict
    print("\n" + "=" * 80)
    if post_duty_sleep_found:
        print("✓ TEST PASSED: Post-duty sleep generated after night flight at hotel")
    else:
        print("✗ TEST FAILED: No post-duty sleep after night flight")
    print("=" * 80)
    
    return post_duty_sleep_found

if __name__ == '__main__':
    test_post_duty_sleep_generation()
