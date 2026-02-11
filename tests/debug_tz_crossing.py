#!/usr/bin/env python3
"""Diagnostic: trace timezone crossing scenarios for inter-duty recovery."""
import sys
sys.path.insert(0, '.')

from datetime import datetime, timedelta
import pytz
from models.data_models import Duty, FlightSegment, Airport, Roster, SleepBlock
from core import BorbelyFatigueModel, ModelConfig

# ── Airports ──
DOH = Airport(code='DOH', timezone='Asia/Qatar', latitude=25.26, longitude=51.56)
LHR = Airport(code='LHR', timezone='Europe/London', latitude=51.47, longitude=-0.46)
AGP = Airport(code='AGP', timezone='Europe/Madrid', latitude=36.67, longitude=-4.49)
BKK = Airport(code='BKK', timezone='Asia/Bangkok', latitude=13.69, longitude=100.75)
JFK = Airport(code='JFK', timezone='America/New_York', latitude=40.64, longitude=-73.78)

utc = pytz.utc
doh_tz = pytz.timezone('Asia/Qatar')

def make_duty(duty_id, dep_airport, arr_airport, dep_utc, arr_utc, report_offset_h=-1, release_offset_h=0.5):
    report = dep_utc + timedelta(hours=report_offset_h)
    release = arr_utc + timedelta(hours=release_offset_h)
    seg = FlightSegment(
        flight_number=f'{duty_id}_FLT',
        departure_airport=dep_airport,
        arrival_airport=arr_airport,
        scheduled_departure_utc=dep_utc,
        scheduled_arrival_utc=arr_utc,
    )
    return Duty(
        duty_id=duty_id,
        date=dep_utc.replace(tzinfo=None),
        report_time_utc=report,
        release_time_utc=release,
        segments=[seg],
        home_base_timezone='Asia/Qatar',
    )

def print_strategy(label, strategy, home_tz_str='Asia/Qatar'):
    ht = pytz.timezone(home_tz_str)
    print(f"\n{'─'*70}")
    print(f"  {label}")
    print(f"{'─'*70}")
    print(f"  Strategy : {strategy.strategy_type}")
    print(f"  Confidence: {strategy.confidence:.2f}")
    print(f"  Explanation: {strategy.explanation}")

    for i, block in enumerate(strategy.sleep_blocks):
        loc_tz = pytz.timezone(block.location_timezone)
        s_loc = block.start_utc.astimezone(loc_tz)
        e_loc = block.end_utc.astimezone(loc_tz)
        s_home = block.start_utc.astimezone(ht)
        e_home = block.end_utc.astimezone(ht)
        dur = (block.end_utc - block.start_utc).total_seconds() / 3600
        label_type = 'NAP' if (hasattr(block, 'is_anchor_sleep') and not block.is_anchor_sleep) else 'MAIN'
        print(f"  Block {i} [{label_type}]:")
        print(f"    UTC      : {block.start_utc.strftime('%d %H:%M')} → {block.end_utc.strftime('%d %H:%M')} ({dur:.1f}h)")
        print(f"    Local    : {s_loc.strftime('%d %H:%M %Z')} → {e_loc.strftime('%d %H:%M %Z')}")
        print(f"    Home(DOH): {s_home.strftime('%d %H:%M')} → {e_home.strftime('%d %H:%M')}")
        print(f"    Env={block.environment}, Eff={block.effective_sleep_hours:.1f}h, Q={block.quality_factor:.0%}")

model = BorbelyFatigueModel()
calc = model.sleep_calculator

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Scenario 1: LHR→DOH, morning arrival at home (07:10 DOH), next day DOH→AGP
# Expected: daytime nap + night sleep (two blocks)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
print("\n" + "=" * 70)
print("SCENARIO 1: LHR→DOH morning arrival (07:10 DOH), next DOH→AGP (07:55)")
print("=" * 70)
d1 = make_duty('S1D1', LHR, DOH,
    dep_utc=utc.localize(datetime(2025, 1, 15, 22, 0)),
    arr_utc=utc.localize(datetime(2025, 1, 16, 4, 10)))  # 07:10 DOH
d2 = make_duty('S1D2', DOH, AGP,
    dep_utc=utc.localize(datetime(2025, 1, 17, 4, 55)),   # 07:55 DOH
    arr_utc=utc.localize(datetime(2025, 1, 17, 11, 30)))

release_doh = d1.release_time_utc.astimezone(doh_tz)
report_doh = d2.report_time_utc.astimezone(doh_tz)
print(f"  D1 release: {release_doh.strftime('%d %H:%M %Z')}")
print(f"  D2 report : {report_doh.strftime('%d %H:%M %Z')}")
print(f"  Gap: {(d2.report_time_utc - d1.release_time_utc).total_seconds()/3600:.1f}h")

strategy = calc.generate_inter_duty_sleep(d1, d2, 'Asia/Qatar', 'DOH')
print_strategy("LHR→DOH morning arrival → nap + night", strategy)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Scenario 2: DOH→LHR, evening arrival at layover (18:00 LHR), next LHR→DOH
# Expected: single night block at hotel (evening onset → circadian-gated wake)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
print("\n" + "=" * 70)
print("SCENARIO 2: DOH→LHR evening arrival (18:00 LHR), next LHR→DOH")
print("=" * 70)
d3 = make_duty('S2D1', DOH, LHR,
    dep_utc=utc.localize(datetime(2025, 1, 20, 7, 0)),    # 10:00 DOH
    arr_utc=utc.localize(datetime(2025, 1, 20, 17, 30)))  # 17:30 UTC = 17:30 LHR winter
d4 = make_duty('S2D2', LHR, DOH,
    dep_utc=utc.localize(datetime(2025, 1, 21, 10, 0)),   # 10:00 LHR
    arr_utc=utc.localize(datetime(2025, 1, 21, 18, 0)))

lhr_tz = pytz.timezone('Europe/London')
release_lhr = d3.release_time_utc.astimezone(lhr_tz)
report_lhr = d4.report_time_utc.astimezone(lhr_tz)
print(f"  D1 release: {release_lhr.strftime('%d %H:%M %Z')} (= {d3.release_time_utc.astimezone(doh_tz).strftime('%d %H:%M')} DOH)")
print(f"  D2 report : {report_lhr.strftime('%d %H:%M %Z')}")
print(f"  Gap: {(d4.report_time_utc - d3.release_time_utc).total_seconds()/3600:.1f}h")

strategy = calc.generate_inter_duty_sleep(d3, d4, 'Asia/Qatar', 'DOH')
print_strategy("DOH→LHR evening layover → hotel night", strategy)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Scenario 3: DOH→BKK, night arrival at layover (02:00 BKK), next BKK→DOH
# Expected: single block, immediate sleep (post-midnight onset → duration dominates)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
print("\n" + "=" * 70)
print("SCENARIO 3: DOH→BKK night arrival (02:00 BKK), next BKK→DOH")
print("=" * 70)
d5 = make_duty('S3D1', DOH, BKK,
    dep_utc=utc.localize(datetime(2025, 1, 22, 14, 0)),   # 17:00 DOH
    arr_utc=utc.localize(datetime(2025, 1, 22, 19, 0)))   # 19:00 UTC = 02:00 BKK+7
d6 = make_duty('S3D2', BKK, DOH,
    dep_utc=utc.localize(datetime(2025, 1, 23, 15, 0)),   # 22:00 BKK
    arr_utc=utc.localize(datetime(2025, 1, 23, 20, 0)))

bkk_tz = pytz.timezone('Asia/Bangkok')
release_bkk = d5.release_time_utc.astimezone(bkk_tz)
report_bkk = d6.report_time_utc.astimezone(bkk_tz)
print(f"  D1 release: {release_bkk.strftime('%d %H:%M %Z')} (= {d5.release_time_utc.astimezone(doh_tz).strftime('%d %H:%M')} DOH)")
print(f"  D2 report : {report_bkk.strftime('%d %H:%M %Z')}")
print(f"  Gap: {(d6.report_time_utc - d5.release_time_utc).total_seconds()/3600:.1f}h")

strategy = calc.generate_inter_duty_sleep(d5, d6, 'Asia/Qatar', 'DOH')
print_strategy("DOH→BKK night arrival → hotel immediate", strategy)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Scenario 4: Short turnaround - DOH→AGP→DOH same day
# Expected: single short block or restricted
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
print("\n" + "=" * 70)
print("SCENARIO 4: DOH→AGP, afternoon arrival, short turnaround (10h gap)")
print("=" * 70)
d7 = make_duty('S4D1', DOH, AGP,
    dep_utc=utc.localize(datetime(2025, 1, 25, 5, 0)),    # 08:00 DOH
    arr_utc=utc.localize(datetime(2025, 1, 25, 12, 0)))   # 12:00 UTC = 13:00 AGP
d8 = make_duty('S4D2', AGP, DOH,
    dep_utc=utc.localize(datetime(2025, 1, 25, 23, 0)),   # 00:00 AGP
    arr_utc=utc.localize(datetime(2025, 1, 26, 5, 0)))

agp_tz = pytz.timezone('Europe/Madrid')
release_agp = d7.release_time_utc.astimezone(agp_tz)
report_agp = d8.report_time_utc.astimezone(agp_tz)
print(f"  D1 release: {release_agp.strftime('%d %H:%M %Z')}")
print(f"  D2 report : {report_agp.strftime('%d %H:%M %Z')}")
print(f"  Gap: {(d8.report_time_utc - d7.release_time_utc).total_seconds()/3600:.1f}h")

strategy = calc.generate_inter_duty_sleep(d7, d8, 'Asia/Qatar', 'DOH')
print_strategy("DOH→AGP afternoon layover → hotel evening", strategy)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Scenario 5: DOH→DOH domestic-style, evening arrival at home (22:00 DOH)
# Expected: single night block at home
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
print("\n" + "=" * 70)
print("SCENARIO 5: evening arrival at home (22:00 DOH), next DOH→LHR 07:00")
print("=" * 70)
d9 = make_duty('S5D1', AGP, DOH,
    dep_utc=utc.localize(datetime(2025, 1, 28, 14, 0)),
    arr_utc=utc.localize(datetime(2025, 1, 28, 18, 30)))  # 21:30 DOH
d10 = make_duty('S5D2', DOH, LHR,
    dep_utc=utc.localize(datetime(2025, 1, 29, 4, 0)),    # 07:00 DOH
    arr_utc=utc.localize(datetime(2025, 1, 29, 11, 0)))

print(f"  D1 release: {d9.release_time_utc.astimezone(doh_tz).strftime('%d %H:%M %Z')}")
print(f"  D2 report : {d10.report_time_utc.astimezone(doh_tz).strftime('%d %H:%M %Z')}")
print(f"  Gap: {(d10.report_time_utc - d9.release_time_utc).total_seconds()/3600:.1f}h")

strategy = calc.generate_inter_duty_sleep(d9, d10, 'Asia/Qatar', 'DOH')
print_strategy("Evening home arrival → night sleep", strategy)

print("\n" + "=" * 70)
print("DONE - All scenarios traced")
print("=" * 70)
