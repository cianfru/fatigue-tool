#!/usr/bin/env python3

from core_model import UnifiedSleepCalculator
from datetime import datetime
import pytz

# Create calculator (now using unified version)
calc = UnifiedSleepCalculator()

print("=== TEST 1: Sleep that SHOULD overlap WOCL ===")
# Test the WOCL overlap fix with the Feb 23rd scenario
sleep_start_utc = datetime(2024, 2, 22, 20, 0, tzinfo=pytz.UTC)  # 20:00 UTC = 23:00 DOH
sleep_end_utc = datetime(2024, 2, 23, 5, 0, tzinfo=pytz.UTC)     # 05:00 UTC = 08:00 DOH

wocl_overlap = calc._calculate_wocl_overlap(sleep_start_utc, sleep_end_utc, 'Asia/Qatar')
doh_tz = pytz.timezone('Asia/Qatar')
sleep_start_local = sleep_start_utc.astimezone(doh_tz)
sleep_end_local = sleep_end_utc.astimezone(doh_tz)

print(f'Sleep period: {sleep_start_local.strftime("%H:%M")} - {sleep_end_local.strftime("%H:%M")} DOH')
print(f'WOCL window: 02:00 - 06:00 DOH')
print(f'Overlap detected: {wocl_overlap} hours')
print(f'Expected: 4.0 hours (02:00-06:00 overlap)')

if wocl_overlap == 4.0:
    print('✅ CORRECT: Sleep 23:00-08:00 overlaps WOCL 02:00-06:00 for 4 hours\n')
else:
    print('❌ INCORRECT overlap calculation\n')

print("=== TEST 2: Sleep that should NOT overlap WOCL ===")
# Test with sleep that doesn't overlap WOCL: 07:00-15:00 DOH
sleep_start_utc2 = datetime(2024, 2, 23, 4, 0, tzinfo=pytz.UTC)  # 04:00 UTC = 07:00 DOH  
sleep_end_utc2 = datetime(2024, 2, 23, 12, 0, tzinfo=pytz.UTC)   # 12:00 UTC = 15:00 DOH

wocl_overlap2 = calc._calculate_wocl_overlap(sleep_start_utc2, sleep_end_utc2, 'Asia/Qatar')
sleep_start_local2 = sleep_start_utc2.astimezone(doh_tz)
sleep_end_local2 = sleep_end_utc2.astimezone(doh_tz)

print(f'Sleep period: {sleep_start_local2.strftime("%H:%M")} - {sleep_end_local2.strftime("%H:%M")} DOH')
print(f'WOCL window: 02:00 - 06:00 DOH')  
print(f'Overlap detected: {wocl_overlap2} hours')
print(f'Expected: 0.0 hours (no overlap)')

if wocl_overlap2 == 0.0:
    print('✅ CORRECT: Sleep 07:00-15:00 does not overlap WOCL 02:00-06:00\n')
else:
    print('❌ INCORRECT: Should be no overlap\n')

print("=== TEST 3: Sleep ending before WOCL starts ===")
# Test with sleep that ends before WOCL: 22:00-01:00 DOH
sleep_start_utc3 = datetime(2024, 2, 22, 19, 0, tzinfo=pytz.UTC)  # 19:00 UTC = 22:00 DOH
sleep_end_utc3 = datetime(2024, 2, 22, 22, 0, tzinfo=pytz.UTC)    # 22:00 UTC = 01:00 DOH next day

wocl_overlap3 = calc._calculate_wocl_overlap(sleep_start_utc3, sleep_end_utc3, 'Asia/Qatar')
sleep_start_local3 = sleep_start_utc3.astimezone(doh_tz)
sleep_end_local3 = sleep_end_utc3.astimezone(doh_tz)

print(f'Sleep period: {sleep_start_local3.strftime("%H:%M")} - {sleep_end_local3.strftime("%H:%M")} DOH')
print(f'WOCL window: 02:00 - 06:00 DOH')
print(f'Overlap detected: {wocl_overlap3} hours')
print(f'Expected: 0.0 hours (sleep ends before WOCL starts)')

if wocl_overlap3 == 0.0:
    print('✅ CORRECT: Sleep 22:00-01:00 does not overlap WOCL 02:00-06:00')
else:
    print('❌ INCORRECT: Should be no overlap')