#!/usr/bin/env python3
"""
Test that post-duty sleep is properly exposed in the API response
with correct timezone information
"""

from datetime import datetime
import pytz
from data_models import Duty, Roster, FlightSegment, Airport
from core_model import BorbelyFatigueModel, ModelConfig
import json

def test_api_exposure():
    """Test that post-duty sleep appears correctly in API response"""
    
    print("=" * 80)
    print("Testing API Exposure of Post-Duty Sleep")
    print("=" * 80)
    
    # Create test roster
    home_tz = pytz.timezone('Europe/Rome')
    layover_tz = pytz.timezone('Asia/Dubai')
    
    rome = Airport(code='FCO', timezone='Europe/Rome')
    dubai = Airport(code='DXB', timezone='Asia/Dubai')
    
    # Night flight: Rome -> Dubai
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
    
    # Return flight: Dubai -> Rome
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
    
    # Run simulation
    config = ModelConfig.default_easa_config()
    model = BorbelyFatigueModel(config=config)
    analysis = model.simulate_roster(roster)
    
    # Check API response
    print("\n--- SLEEP STRATEGIES (API Response) ---")
    
    post_duty_found = False
    correct_timezone = False
    
    if hasattr(model, 'sleep_strategies'):
        for key, strategy in model.sleep_strategies.items():
            print(f"\n{key}:")
            print(f"  Strategy: {strategy['strategy_type']}")
            print(f"  Confidence: {strategy['confidence']:.0%}")
            print(f"  Sleep blocks: {len(strategy['sleep_blocks'])}")
            
            if 'post_duty' in key:
                post_duty_found = True
                print(f"  >>> POST-DUTY SLEEP FOUND IN API <<<")
                
                for block in strategy['sleep_blocks']:
                    print(f"\n  Block details:")
                    print(f"    Time: {block['sleep_start_time']} - {block['sleep_end_time']}")
                    print(f"    ISO: {block['sleep_start_iso']}")
                    print(f"    Environment: {block['environment']}")
                    print(f"    Timezone: {block['location_timezone']}")
                    print(f"    Duration: {block['duration_hours']:.2f}h")
                    print(f"    Effective: {block['effective_hours']:.2f}h")
                    
                    # Check if timezone is Dubai (not Rome)
                    if block['location_timezone'] == 'Asia/Dubai':
                        correct_timezone = True
                        print(f"    ✓ Correct timezone (layover location)")
                    else:
                        print(f"    ✗ Wrong timezone (expected Asia/Dubai, got {block['location_timezone']})")
    
    # Check pre-duty sleep timezone
    print("\n--- PRE-DUTY SLEEP TIMEZONE CHECK ---")
    duty1_strategy = model.sleep_strategies.get('duty_1', {})
    if duty1_strategy:
        for block in duty1_strategy.get('sleep_blocks', []):
            tz = block.get('location_timezone', 'N/A')
            env = block.get('environment', 'N/A')
            print(f"Pre-duty block: {block['sleep_start_time']}-{block['sleep_end_time']}")
            print(f"  Timezone: {tz}, Environment: {env}")
            if tz == 'Europe/Rome' and env == 'home':
                print(f"  ✓ Correct (home base)")
    
    # Final results
    print("\n" + "=" * 80)
    print("TEST RESULTS:")
    print("=" * 80)
    
    if post_duty_found:
        print("✓ Post-duty sleep appears in API response")
    else:
        print("✗ Post-duty sleep NOT in API response")
    
    if correct_timezone:
        print("✓ Sleep times shown in correct location timezone")
    else:
        print("✗ Sleep times NOT in correct timezone")
    
    if post_duty_found and correct_timezone:
        print("\n✓✓ ALL TESTS PASSED ✓✓")
        return True
    else:
        print("\n✗✗ TESTS FAILED ✗✗")
        return False

if __name__ == '__main__':
    test_api_exposure()
