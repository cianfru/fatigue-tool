#!/usr/bin/env python3

import requests
import json

# Test the API endpoint
try:
    response = requests.get('http://localhost:8000/analyze')
    if response.status_code == 200:
        data = response.json()
        
        # Look for Feb 23rd data
        for day_result in data.get('results', []):
            if '2024-02-23' in day_result.get('date', ''):
                print(f"Date: {day_result['date']}")
                print(f"Sleep blocks: {len(day_result.get('sleep_blocks', []))}")
                for i, sleep in enumerate(day_result.get('sleep_blocks', [])):
                    print(f"  Sleep {i+1}: {sleep.get('sleep_start_time')} - {sleep.get('sleep_end_time')}")
                    print(f"    ISO: {sleep.get('sleep_start_iso')} - {sleep.get('sleep_end_iso')}")
                
                duties = day_result.get('duties', [])
                print(f"Duties: {len(duties)}")
                for i, duty in enumerate(duties):
                    print(f"  Duty {i+1}: Report {duty.get('report_time_local')}, Release {duty.get('release_time_local')}")
                break
        else:
            print('Feb 23rd not found in API response')
    else:
        print(f'API error: {response.status_code}')
except Exception as e:
    print(f'Error connecting to API: {e}')
    print('Try starting the server first with: python3 fatigue_app.py')