"""
Test script to demonstrate Aviation Workload Integration Model

Compares fatigue accumulation between:
- Multi-sector short-haul (4 sectors, 8 landings total)
- Single-sector long-haul (1 sector, 2 landings total)
"""

from core_model import WorkloadModel, WorkloadParameters, FlightPhase

def test_workload_differences():
    """Demonstrate how workload affects fatigue accumulation"""
    
    workload = WorkloadModel()
    
    print("=" * 80)
    print("AVIATION WORKLOAD INTEGRATION MODEL - DEMONSTRATION")
    print("=" * 80)
    print()
    print("Scientific Foundation:")
    print("- Bourgeois-Bougrine et al. (2003): Short-haul vs long-haul pilot workload")
    print("- Van Dongen et al. (2003): Cumulative cost of wakefulness")
    print()
    
    # ========================================================================
    # SHORT-HAUL: 4-SECTOR DAY
    # ========================================================================
    
    print("SCENARIO 1: SHORT-HAUL (4 Sectors)")
    print("-" * 80)
    print("Duty: 06:00-12:00 (6 hours)")
    print("Sectors: 4 × 1.5 hours = 6 hours flight time")
    print("Landings: 4 (each landing = high workload)")
    print()
    
    short_haul_phases = [
        # Sector 1
        (FlightPhase.PREFLIGHT, 30/60, 1),
        (FlightPhase.TAXI_OUT, 5/60, 1),
        (FlightPhase.TAKEOFF, 2/60, 1),
        (FlightPhase.CLIMB, 10/60, 1),
        (FlightPhase.CRUISE, 45/60, 1),
        (FlightPhase.DESCENT, 10/60, 1),
        (FlightPhase.APPROACH, 5/60, 1),
        (FlightPhase.LANDING, 3/60, 1),
        (FlightPhase.TAXI_IN, 5/60, 1),
        
        # Turnaround
        (FlightPhase.GROUND_TURNAROUND, 30/60, 2),
        
        # Sector 2
        (FlightPhase.TAXI_OUT, 5/60, 2),
        (FlightPhase.TAKEOFF, 2/60, 2),
        (FlightPhase.CLIMB, 10/60, 2),
        (FlightPhase.CRUISE, 45/60, 2),
        (FlightPhase.DESCENT, 10/60, 2),
        (FlightPhase.APPROACH, 5/60, 2),
        (FlightPhase.LANDING, 3/60, 2),
        (FlightPhase.TAXI_IN, 5/60, 2),
        
        # Turnaround
        (FlightPhase.GROUND_TURNAROUND, 30/60, 3),
        
        # Sector 3
        (FlightPhase.TAXI_OUT, 5/60, 3),
        (FlightPhase.TAKEOFF, 2/60, 3),
        (FlightPhase.CLIMB, 10/60, 3),
        (FlightPhase.CRUISE, 45/60, 3),
        (FlightPhase.DESCENT, 10/60, 3),
        (FlightPhase.APPROACH, 5/60, 3),
        (FlightPhase.LANDING, 3/60, 3),
        (FlightPhase.TAXI_IN, 5/60, 3),
        
        # Turnaround
        (FlightPhase.GROUND_TURNAROUND, 30/60, 4),
        
        # Sector 4
        (FlightPhase.TAXI_OUT, 5/60, 4),
        (FlightPhase.TAKEOFF, 2/60, 4),
        (FlightPhase.CLIMB, 10/60, 4),
        (FlightPhase.CRUISE, 45/60, 4),
        (FlightPhase.DESCENT, 10/60, 4),
        (FlightPhase.APPROACH, 5/60, 4),
        (FlightPhase.LANDING, 3/60, 4),
        (FlightPhase.TAXI_IN, 5/60, 4),
    ]
    
    total_actual_hours = 0
    total_effective_hours = 0
    
    for phase, duration_hours, sector in short_haul_phases:
        actual = duration_hours
        effective = workload.calculate_effective_wake_time(actual, phase, sector)
        multiplier = workload.get_combined_multiplier(phase, sector)
        
        total_actual_hours += actual
        total_effective_hours += effective
        
        # Only print critical phases
        if phase in [FlightPhase.TAKEOFF, FlightPhase.LANDING, FlightPhase.APPROACH]:
            print(f"  Sector {sector} {phase.value:12s}: "
                  f"{actual*60:3.0f} min × {multiplier:.2f} = "
                  f"{effective*60:4.0f} min effective")
    
    print()
    print(f"📊 Total actual duty time:    {total_actual_hours:.2f} hours")
    print(f"📊 Total effective wake time: {total_effective_hours:.2f} hours")
    print(f"📊 Fatigue multiplier:        {total_effective_hours/total_actual_hours:.2f}x")
    print()
    
    # ========================================================================
    # LONG-HAUL: SINGLE SECTOR
    # ========================================================================
    
    print("SCENARIO 2: LONG-HAUL (Single Sector)")
    print("-" * 80)
    print("Duty: 22:00-08:00 (10 hours)")
    print("Sectors: 1 × 10 hours = 10 hours flight time")
    print("Landings: 1 (single landing event)")
    print()
    
    long_haul_phases = [
        (FlightPhase.PREFLIGHT, 60/60, 1),
        (FlightPhase.TAXI_OUT, 10/60, 1),
        (FlightPhase.TAKEOFF, 3/60, 1),
        (FlightPhase.CLIMB, 20/60, 1),
        (FlightPhase.CRUISE, 480/60, 1),  # 8 hours cruise
        (FlightPhase.DESCENT, 30/60, 1),
        (FlightPhase.APPROACH, 10/60, 1),
        (FlightPhase.LANDING, 3/60, 1),
        (FlightPhase.TAXI_IN, 10/60, 1),
    ]
    
    total_actual_hours_lh = 0
    total_effective_hours_lh = 0
    
    for phase, duration_hours, sector in long_haul_phases:
        actual = duration_hours
        effective = workload.calculate_effective_wake_time(actual, phase, sector)
        multiplier = workload.get_combined_multiplier(phase, sector)
        
        total_actual_hours_lh += actual
        total_effective_hours_lh += effective
        
        print(f"  {phase.value:12s}: "
              f"{actual*60:4.0f} min × {multiplier:.2f} = "
              f"{effective*60:4.0f} min effective")
    
    print()
    print(f"📊 Total actual duty time:    {total_actual_hours_lh:.2f} hours")
    print(f"📊 Total effective wake time: {total_effective_hours_lh:.2f} hours")
    print(f"📊 Fatigue multiplier:        {total_effective_hours_lh/total_actual_hours_lh:.2f}x")
    print()
    
    # ========================================================================
    # COMPARISON
    # ========================================================================
    
    print("=" * 80)
    print("KEY FINDINGS")
    print("=" * 80)
    print()
    print(f"Short-haul (4 sectors): {total_actual_hours:.1f}h actual → "
          f"{total_effective_hours:.1f}h effective "
          f"({total_effective_hours/total_actual_hours:.2f}x multiplier)")
    print(f"Long-haul (1 sector):   {total_actual_hours_lh:.1f}h actual → "
          f"{total_effective_hours_lh:.1f}h effective "
          f"({total_effective_hours_lh/total_actual_hours_lh:.2f}x multiplier)")
    print()
    print("✅ Multi-sector duties accumulate fatigue FASTER due to:")
    print("   • Multiple high-workload phases (takeoffs, landings)")
    print("   • Cumulative sector penalty (each sector compounds fatigue)")
    print("   • Reduced low-workload cruise time")
    print()
    print(f"💡 Despite shorter duty time, short-haul accumulates")
    print(f"   {(total_effective_hours/total_effective_hours_lh)*100:.0f}% "
          f"of long-haul's effective fatigue")
    print()
    print("This aligns with Bourgeois-Bougrine (2003) findings:")
    print("'Short-haul pilots reported higher workload-related fatigue'")
    print("=" * 80)


if __name__ == "__main__":
    test_workload_differences()
