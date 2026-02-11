#!/usr/bin/env python3
"""
Diagnostic script: Trace sleep generation for SAFAR Peter's Feb 2026 roster.

Builds the roster programmatically from the PDF data, runs it through the
fatigue model, and prints detailed trace for each inter-duty gap showing
where sleep blocks are generated (or missing).
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta, time
from models.data_models import Duty, FlightSegment, Airport, Roster, SleepBlock
from core.fatigue_model import BorbelyFatigueModel
from core.sleep_calculator import UnifiedSleepCalculator
import pytz

utc = pytz.utc
DOH_TZ = pytz.timezone('Asia/Qatar')       # UTC+3
ZRH_TZ = pytz.timezone('Europe/Zurich')    # UTC+1 (Feb = CET)
KWI_TZ = pytz.timezone('Asia/Kuwait')      # UTC+3
DXB_TZ = pytz.timezone('Asia/Dubai')       # UTC+4
KHI_TZ = pytz.timezone('Asia/Karachi')     # UTC+5
IAD_TZ = pytz.timezone('America/New_York') # UTC-5 (Feb = EST)
LHR_TZ = pytz.timezone('Europe/London')    # UTC+0 (Feb = GMT)
MIA_TZ = pytz.timezone('America/New_York') # UTC-5 (Feb = EST)

# Airports
DOH = Airport(code='DOH', timezone='Asia/Qatar', latitude=25.27, longitude=51.56)
ZRH = Airport(code='ZRH', timezone='Europe/Zurich', latitude=47.46, longitude=8.55)
KWI = Airport(code='KWI', timezone='Asia/Kuwait', latitude=29.23, longitude=47.97)
DXB = Airport(code='DXB', timezone='Asia/Dubai', latitude=25.25, longitude=55.36)
KHI = Airport(code='KHI', timezone='Asia/Karachi', latitude=24.91, longitude=67.16)
IAD = Airport(code='IAD', timezone='America/New_York', latitude=38.94, longitude=-77.46)
LHR = Airport(code='LHR', timezone='Europe/London', latitude=51.47, longitude=-0.46)
MIA = Airport(code='MIA', timezone='America/New_York', latitude=25.80, longitude=-80.29)


def make_utc(year, month, day, hour, minute):
    """Create UTC-aware datetime"""
    return utc.localize(datetime(year, month, day, hour, minute))


def local_to_utc(year, month, day, hour, minute, tz):
    """Create datetime in local TZ and convert to UTC"""
    local_dt = tz.localize(datetime(year, month, day, hour, minute))
    return local_dt.astimezone(utc)


def build_roster():
    """Build SAFAR Peter's February 2026 roster from PDF data.

    All times from the roster are LOCAL times at the respective airports.
    We convert to UTC for the model.
    """
    duties = []
    home_tz_str = 'Asia/Qatar'

    # -----------------------------------------------------------------------
    # Feb 1 (Sun): RPT 01:25 DOH, FLT 093 DOH-ZRH 02:40/07:00, ZRH-DOH 08:45/16:30
    # All times are local: DOH=UTC+3, ZRH=UTC+1(CET in Feb)
    # -----------------------------------------------------------------------
    d1_report = local_to_utc(2026, 2, 1, 1, 25, DOH_TZ)   # 01:25 DOH = 22:25 UTC Jan 31
    d1_seg1_dep = local_to_utc(2026, 2, 1, 2, 40, DOH_TZ)  # 02:40 DOH = 23:40 UTC Jan 31
    d1_seg1_arr = local_to_utc(2026, 2, 1, 7, 0, ZRH_TZ)   # 07:00 ZRH = 06:00 UTC
    d1_seg2_dep = local_to_utc(2026, 2, 1, 8, 45, ZRH_TZ)  # 08:45 ZRH = 07:45 UTC
    d1_seg2_arr = local_to_utc(2026, 2, 1, 16, 30, DOH_TZ)  # 16:30 DOH = 13:30 UTC
    d1_release = d1_seg2_arr + timedelta(minutes=30)         # +30 min post-flight

    d1 = Duty(
        duty_id='D001', date=datetime(2026, 2, 1),
        report_time_utc=d1_report, release_time_utc=d1_release,
        segments=[
            FlightSegment('QR093', DOH, ZRH, d1_seg1_dep, d1_seg1_arr),
            FlightSegment('QR093', ZRH, DOH, d1_seg2_dep, d1_seg2_arr),
        ],
        home_base_timezone=home_tz_str
    )
    duties.append(d1)

    # -----------------------------------------------------------------------
    # Feb 2 (Mon): RPT 07:45 DOH, FLT 094 DOH-ZRH 09:00/13:20, ZRH-DOH 14:50/22:30
    # (Estimated from typical QR094 schedule — the PDF partially cut off)
    # -----------------------------------------------------------------------
    d2_report = local_to_utc(2026, 2, 2, 7, 45, DOH_TZ)
    d2_seg1_dep = local_to_utc(2026, 2, 2, 9, 0, DOH_TZ)
    d2_seg1_arr = local_to_utc(2026, 2, 2, 13, 20, ZRH_TZ)
    d2_seg2_dep = local_to_utc(2026, 2, 2, 14, 50, ZRH_TZ)
    d2_seg2_arr = local_to_utc(2026, 2, 2, 22, 30, DOH_TZ)
    d2_release = d2_seg2_arr + timedelta(minutes=30)

    d2 = Duty(
        duty_id='D002', date=datetime(2026, 2, 2),
        report_time_utc=d2_report, release_time_utc=d2_release,
        segments=[
            FlightSegment('QR094', DOH, ZRH, d2_seg1_dep, d2_seg1_arr),
            FlightSegment('QR094', ZRH, DOH, d2_seg2_dep, d2_seg2_arr),
        ],
        home_base_timezone=home_tz_str
    )
    duties.append(d2)

    # Feb 3-4: OFF DOH (no duties)

    # -----------------------------------------------------------------------
    # Feb 5 (Thu): RPT 18:10, FLT 1082 DOH-KWI 19:25/20:50, FLT 1083 KWI-DOH 22:20/23:45
    # All local times at respective airports. KWI=UTC+3 same as DOH.
    # -----------------------------------------------------------------------
    d3_report = local_to_utc(2026, 2, 5, 18, 10, DOH_TZ)
    d3_seg1_dep = local_to_utc(2026, 2, 5, 19, 25, DOH_TZ)
    d3_seg1_arr = local_to_utc(2026, 2, 5, 20, 50, KWI_TZ)
    d3_seg2_dep = local_to_utc(2026, 2, 5, 22, 20, KWI_TZ)
    d3_seg2_arr = local_to_utc(2026, 2, 5, 23, 45, DOH_TZ)
    d3_release = d3_seg2_arr + timedelta(minutes=30)

    d3 = Duty(
        duty_id='D003', date=datetime(2026, 2, 5),
        report_time_utc=d3_report, release_time_utc=d3_release,
        segments=[
            FlightSegment('QR1082', DOH, KWI, d3_seg1_dep, d3_seg1_arr),
            FlightSegment('QR1083', KWI, DOH, d3_seg2_dep, d3_seg2_arr),
        ],
        home_base_timezone=home_tz_str
    )
    duties.append(d3)

    # -----------------------------------------------------------------------
    # Feb 6 (Fri): RPT 17:45, FLT 1018 DOH-DXB 19:00/21:15, FLT 1019 DXB-DOH 22:50/23:05
    # DXB = UTC+4
    # -----------------------------------------------------------------------
    d4_report = local_to_utc(2026, 2, 6, 17, 45, DOH_TZ)
    d4_seg1_dep = local_to_utc(2026, 2, 6, 19, 0, DOH_TZ)
    d4_seg1_arr = local_to_utc(2026, 2, 6, 21, 15, DXB_TZ)
    d4_seg2_dep = local_to_utc(2026, 2, 6, 22, 50, DXB_TZ)
    d4_seg2_arr = local_to_utc(2026, 2, 6, 23, 5, DOH_TZ)
    d4_release = d4_seg2_arr + timedelta(minutes=30)

    d4 = Duty(
        duty_id='D004', date=datetime(2026, 2, 6),
        report_time_utc=d4_report, release_time_utc=d4_release,
        segments=[
            FlightSegment('QR1018', DOH, DXB, d4_seg1_dep, d4_seg1_arr),
            FlightSegment('QR1019', DXB, DOH, d4_seg2_dep, d4_seg2_arr),
        ],
        home_base_timezone=home_tz_str
    )
    duties.append(d4)

    # -----------------------------------------------------------------------
    # Feb 7 (Sat): RPT 19:55, FLT 604 DOH-KHI 21:10/01:35+1
    # KHI = UTC+5
    # -----------------------------------------------------------------------
    d5_report = local_to_utc(2026, 2, 7, 19, 55, DOH_TZ)
    d5_seg1_dep = local_to_utc(2026, 2, 7, 21, 10, DOH_TZ)
    d5_seg1_arr = local_to_utc(2026, 2, 8, 1, 35, KHI_TZ)  # +1 day at KHI
    d5_release = d5_seg1_arr + timedelta(minutes=30)

    d5 = Duty(
        duty_id='D005', date=datetime(2026, 2, 7),
        report_time_utc=d5_report, release_time_utc=d5_release,
        segments=[
            FlightSegment('QR604', DOH, KHI, d5_seg1_dep, d5_seg1_arr),
        ],
        home_base_timezone=home_tz_str
    )
    duties.append(d5)

    # -----------------------------------------------------------------------
    # Feb 8 (Sun): FLT 605 KHI-DOH 04:20/05:10 (same day)
    # Report ~03:05 KHI (1h15 before dep)
    # KHI = UTC+5, DOH = UTC+3 (05:10 DOH local)
    # -----------------------------------------------------------------------
    d6_report = local_to_utc(2026, 2, 8, 3, 5, KHI_TZ)  # ~1h15 before departure
    d6_seg1_dep = local_to_utc(2026, 2, 8, 4, 20, KHI_TZ)
    d6_seg1_arr = local_to_utc(2026, 2, 8, 5, 10, DOH_TZ)  # Arrives DOH 05:10 LT
    d6_release = d6_seg1_arr + timedelta(minutes=30)

    d6 = Duty(
        duty_id='D006', date=datetime(2026, 2, 8),
        report_time_utc=d6_report, release_time_utc=d6_release,
        segments=[
            FlightSegment('QR605', KHI, DOH, d6_seg1_dep, d6_seg1_arr),
        ],
        home_base_timezone=home_tz_str
    )
    duties.append(d6)

    # Feb 8-10: OFF DOH

    # -----------------------------------------------------------------------
    # Feb 11 (Wed): RPT 00:10 DOH, FLT 709 DOH-IAD 01:25/08:20 (same day IAD)
    # IAD = UTC-5 (EST in Feb), DOH = UTC+3
    # -----------------------------------------------------------------------
    d7_report = local_to_utc(2026, 2, 11, 0, 10, DOH_TZ)
    d7_seg1_dep = local_to_utc(2026, 2, 11, 1, 25, DOH_TZ)
    d7_seg1_arr = local_to_utc(2026, 2, 11, 8, 20, IAD_TZ)  # 08:20 IAD EST
    d7_release = d7_seg1_arr + timedelta(minutes=30)

    d7 = Duty(
        duty_id='D007', date=datetime(2026, 2, 11),
        report_time_utc=d7_report, release_time_utc=d7_release,
        segments=[
            FlightSegment('QR709', DOH, IAD, d7_seg1_dep, d7_seg1_arr),
        ],
        home_base_timezone=home_tz_str
    )
    duties.append(d7)

    # Feb 12: DOFF IAD

    # -----------------------------------------------------------------------
    # Feb 13 (Fri): RPT 09:40 IAD, FLT 710 IAD-DOH 10:40/07:15+1
    # IAD = UTC-5, DOH = UTC+3. Arrival 07:15 DOH = next day
    # -----------------------------------------------------------------------
    d8_report = local_to_utc(2026, 2, 13, 9, 40, IAD_TZ)
    d8_seg1_dep = local_to_utc(2026, 2, 13, 10, 40, IAD_TZ)
    d8_seg1_arr = local_to_utc(2026, 2, 14, 7, 15, DOH_TZ)  # +1 day
    d8_release = d8_seg1_arr + timedelta(minutes=30)

    d8 = Duty(
        duty_id='D008', date=datetime(2026, 2, 13),
        report_time_utc=d8_report, release_time_utc=d8_release,
        segments=[
            FlightSegment('QR710', IAD, DOH, d8_seg1_dep, d8_seg1_arr),
        ],
        home_base_timezone=home_tz_str
    )
    duties.append(d8)

    # Feb 15-16: OFF DOH

    # -----------------------------------------------------------------------
    # Feb 17 (Tue): RPT 07:30 DOH, FLT 007 DOH-LHR 08:45/13:20 (DH deadhead)
    # LHR = UTC+0 (GMT in Feb)
    # -----------------------------------------------------------------------
    d9_report = local_to_utc(2026, 2, 17, 7, 30, DOH_TZ)
    d9_seg1_dep = local_to_utc(2026, 2, 17, 8, 45, DOH_TZ)
    d9_seg1_arr = local_to_utc(2026, 2, 17, 13, 20, LHR_TZ)
    d9_release = d9_seg1_arr + timedelta(minutes=30)

    d9 = Duty(
        duty_id='D009', date=datetime(2026, 2, 17),
        report_time_utc=d9_report, release_time_utc=d9_release,
        segments=[
            FlightSegment('QR007', DOH, LHR, d9_seg1_dep, d9_seg1_arr),
        ],
        home_base_timezone=home_tz_str
    )
    duties.append(d9)

    # -----------------------------------------------------------------------
    # Feb 18 (Wed): RPT 07:25 LHR, FLT 112 LHR-DOH 08:40/18:20
    # LHR = UTC+0, DOH = UTC+3
    # -----------------------------------------------------------------------
    d10_report = local_to_utc(2026, 2, 18, 7, 25, LHR_TZ)
    d10_seg1_dep = local_to_utc(2026, 2, 18, 8, 40, LHR_TZ)
    d10_seg1_arr = local_to_utc(2026, 2, 18, 18, 20, DOH_TZ)
    d10_release = d10_seg1_arr + timedelta(minutes=30)

    d10 = Duty(
        duty_id='D010', date=datetime(2026, 2, 18),
        report_time_utc=d10_report, release_time_utc=d10_release,
        segments=[
            FlightSegment('QR112', LHR, DOH, d10_seg1_dep, d10_seg1_arr),
        ],
        home_base_timezone=home_tz_str
    )
    duties.append(d10)

    # Feb 19-20: OFF DOH

    # -----------------------------------------------------------------------
    # Feb 21 (Sat): RPT 06:45 DOH, FLT 777 DOH-MIA 08:00/16:25
    # MIA = UTC-5 (EST in Feb)
    # -----------------------------------------------------------------------
    d11_report = local_to_utc(2026, 2, 21, 6, 45, DOH_TZ)
    d11_seg1_dep = local_to_utc(2026, 2, 21, 8, 0, DOH_TZ)
    d11_seg1_arr = local_to_utc(2026, 2, 21, 16, 25, MIA_TZ)
    d11_release = d11_seg1_arr + timedelta(minutes=30)

    d11 = Duty(
        duty_id='D011', date=datetime(2026, 2, 21),
        report_time_utc=d11_report, release_time_utc=d11_release,
        segments=[
            FlightSegment('QR777', DOH, MIA, d11_seg1_dep, d11_seg1_arr),
        ],
        home_base_timezone=home_tz_str
    )
    duties.append(d11)

    # Feb 22: DOFF MIA

    # -----------------------------------------------------------------------
    # Feb 23 (Mon): RPT 18:15 MIA, FLT 778 MIA-DOH 19:15/17:00+1
    # MIA = UTC-5, DOH = UTC+3
    # -----------------------------------------------------------------------
    d12_report = local_to_utc(2026, 2, 23, 18, 15, MIA_TZ)
    d12_seg1_dep = local_to_utc(2026, 2, 23, 19, 15, MIA_TZ)
    d12_seg1_arr = local_to_utc(2026, 2, 24, 17, 0, DOH_TZ)  # +1 day
    d12_release = d12_seg1_arr + timedelta(minutes=30)

    d12 = Duty(
        duty_id='D012', date=datetime(2026, 2, 23),
        report_time_utc=d12_report, release_time_utc=d12_release,
        segments=[
            FlightSegment('QR778', MIA, DOH, d12_seg1_dep, d12_seg1_arr),
        ],
        home_base_timezone=home_tz_str
    )
    duties.append(d12)

    roster = Roster(
        roster_id='FEB2026_SAFAR',
        pilot_id='133152',
        month='2026-02',
        duties=duties,
        home_base_timezone=home_tz_str,
        pilot_name='SAFAR Peter',
        pilot_base='DOH',
        pilot_aircraft='A350'
    )
    return roster


def trace_sleep_generation(roster):
    """Trace through sleep generation for each inter-duty gap."""
    calc = UnifiedSleepCalculator()
    home_tz = pytz.timezone(roster.home_base_timezone)

    print("=" * 90)
    print("SLEEP GENERATION TRACE — SAFAR Peter Feb 2026")
    print("=" * 90)
    print()

    for i, duty in enumerate(roster.duties):
        prev_duty = roster.duties[i - 1] if i > 0 else None

        # Print duty info
        dep_ap = duty.segments[0].departure_airport.code if duty.segments else '???'
        arr_ap = duty.segments[-1].arrival_airport.code if duty.segments else '???'
        report_local = duty.report_time_utc.astimezone(home_tz)
        release_local = duty.release_time_utc.astimezone(home_tz)
        print(f"--- DUTY {duty.duty_id} ({duty.date.strftime('%b %d')}) ---")
        print(f"  Route: {dep_ap} → {arr_ap}")
        print(f"  Report: {report_local.strftime('%Y-%m-%d %H:%M')} DOH / {duty.report_time_utc.strftime('%H:%M')} UTC")
        print(f"  Release: {release_local.strftime('%Y-%m-%d %H:%M')} DOH / {duty.release_time_utc.strftime('%H:%M')} UTC")

        if prev_duty:
            gap_hours = (duty.report_time_utc - prev_duty.release_time_utc).total_seconds() / 3600
            print(f"  Gap from previous: {gap_hours:.1f}h")

        # Generate sleep
        if i == 0:
            print(f"  → First duty: using estimate_sleep_for_duty()")
            try:
                strategy = calc.estimate_sleep_for_duty(
                    duty=duty,
                    previous_duty=None,
                    home_timezone=roster.home_base_timezone,
                    home_base=roster.pilot_base
                )
            except Exception as e:
                print(f"  ❌ ERROR: {e}")
                print()
                continue
        else:
            print(f"  → Inter-duty: using generate_inter_duty_sleep()")
            try:
                strategy = calc.generate_inter_duty_sleep(
                    previous_duty=prev_duty,
                    next_duty=duty,
                    home_timezone=roster.home_base_timezone,
                    home_base=roster.pilot_base
                )
            except Exception as e:
                print(f"  ❌ ERROR generating sleep: {type(e).__name__}: {e}")
                import traceback
                traceback.print_exc()
                print()
                continue

        print(f"  Strategy: {strategy.strategy_type} (confidence={strategy.confidence:.2f})")
        print(f"  Explanation: {strategy.explanation}")

        if not strategy.sleep_blocks:
            print(f"  ⚠️  NO SLEEP BLOCKS GENERATED!")
        else:
            for j, block in enumerate(strategy.sleep_blocks):
                block_start_local = block.start_utc.astimezone(home_tz)
                block_end_local = block.end_utc.astimezone(home_tz)
                # Also show in sleep location timezone
                sleep_loc_tz = pytz.timezone(block.location_timezone)
                block_start_sleep_tz = block.start_utc.astimezone(sleep_loc_tz)
                block_end_sleep_tz = block.end_utc.astimezone(sleep_loc_tz)
                print(f"  Block {j+1}: {block_start_sleep_tz.strftime('%Y-%m-%d %H:%M')} → "
                      f"{block_end_sleep_tz.strftime('%Y-%m-%d %H:%M')} ({block.location_timezone})")
                print(f"           {block_start_local.strftime('%Y-%m-%d %H:%M')} → "
                      f"{block_end_local.strftime('%Y-%m-%d %H:%M')} (DOH time)")
                print(f"           Duration: {block.duration_hours:.1f}h, "
                      f"Effective: {block.effective_sleep_hours:.1f}h, "
                      f"Env: {block.environment}, "
                      f"Anchor: {block.is_anchor_sleep}")

                # Check if block ends before duty report
                if block.end_utc > duty.report_time_utc:
                    print(f"  ⚠️  BLOCK ENDS AFTER DUTY REPORT! (overlap)")

        print()

    # Now trace the full model to see rest-day blocks too
    print("\n" + "=" * 90)
    print("FULL MODEL SIMULATION — checking all sleep blocks")
    print("=" * 90)

    model = BorbelyFatigueModel()
    try:
        result = model.simulate_roster(roster)
    except Exception as e:
        print(f"❌ simulate_roster FAILED: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return

    # Access the sleep blocks by re-extracting them
    from models.data_models import CircadianState
    body_clock = CircadianState(
        current_phase_shift_hours=0.0,
        last_update_utc=roster.duties[0].report_time_utc - timedelta(days=1),
        reference_timezone=roster.home_base_timezone
    )
    body_clock_timeline = [(body_clock.last_update_utc, body_clock)]
    for duty in roster.duties:
        dep_tz = duty.segments[0].departure_airport.timezone
        body_clock = model.calculate_adaptation(
            duty.report_time_utc, body_clock, dep_tz, roster.home_base_timezone
        )
        body_clock_timeline.append((duty.report_time_utc, body_clock))

    all_sleep, strategies = model._extract_sleep_from_roster(roster, body_clock_timeline)
    all_sleep.sort(key=lambda s: s.start_utc)

    print(f"\nTotal sleep blocks: {len(all_sleep)}")
    print(f"Total duties: {len(roster.duties)}")

    print("\n--- All sleep blocks (chronological) ---")
    for j, block in enumerate(all_sleep):
        loc_tz = pytz.timezone(block.location_timezone)
        start_local = block.start_utc.astimezone(loc_tz)
        end_local = block.end_utc.astimezone(loc_tz)
        start_home = block.start_utc.astimezone(home_tz)
        end_home = block.end_utc.astimezone(home_tz)
        anchor_str = "MAIN" if block.is_anchor_sleep else "NAP "
        print(f"  [{j+1:2d}] {start_home.strftime('%b %d %H:%M')}-{end_home.strftime('%H:%M')} DOH | "
              f"{start_local.strftime('%H:%M')}-{end_local.strftime('%H:%M')} {block.location_timezone[-10:]:>10} | "
              f"{block.duration_hours:.1f}h eff={block.effective_sleep_hours:.1f}h | "
              f"{anchor_str} {block.environment}")

    # Check each duty for prior sleep
    print("\n--- Per-duty sleep coverage check ---")
    issues_found = 0
    for i, duty in enumerate(roster.duties):
        report_local = duty.report_time_utc.astimezone(home_tz)
        dep = duty.segments[0].departure_airport.code if duty.segments else '???'
        arr = duty.segments[-1].arrival_airport.code if duty.segments else '???'

        # Find sleep blocks in the 48h before this duty
        prior_blocks = [
            s for s in all_sleep
            if s.end_utc <= duty.report_time_utc and
               s.end_utc >= duty.report_time_utc - timedelta(hours=48)
        ]
        prior_total = sum(s.effective_sleep_hours for s in prior_blocks)

        # Find the most recent sleep block
        recent_sleep = [s for s in all_sleep if s.end_utc <= duty.report_time_utc]
        if recent_sleep:
            last_block = recent_sleep[-1]
            hours_since_sleep = (duty.report_time_utc - last_block.end_utc).total_seconds() / 3600
        else:
            hours_since_sleep = float('inf')

        status = "✓" if prior_total >= 5 and hours_since_sleep < 20 else "⚠️"
        if prior_total < 3:
            status = "❌"
            issues_found += 1

        print(f"  {status} {duty.duty_id} ({duty.date.strftime('%b %d')} {report_local.strftime('%H:%M')}) "
              f"{dep}→{arr}: {len(prior_blocks)} blocks, {prior_total:.1f}h effective, "
              f"{hours_since_sleep:.1f}h since last sleep")

    print(f"\n{'❌ ' + str(issues_found) + ' duties with insufficient prior sleep' if issues_found else '✅ All duties have adequate prior sleep'}")


def check_simulate_roster_exists():
    """Check if simulate_roster method exists and its signature."""
    model = BorbelyFatigueModel()
    if not hasattr(model, 'simulate_roster'):
        print("⚠️  BorbelyFatigueModel has no simulate_roster() method!")
        print("   Available methods:", [m for m in dir(model) if not m.startswith('_')])
        return False
    return True


if __name__ == '__main__':
    roster = build_roster()

    print("Roster built with", len(roster.duties), "duties")
    print()

    # First check if simulate_roster exists
    has_sim = check_simulate_roster_exists()

    # Always do the per-gap trace
    trace_sleep_generation(roster)
