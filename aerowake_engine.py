"""
aerowake_engine.py - AeroWake Engine with Corrections
======================================================

FIXES APPLIED:
1. Process S properly handles sleep vs wake
2. S_0 initialization from sleep history with tiered fallback
3. Circadian process uses correct timezone
4. Multiplicative integration (non-linear)
5. Inflight rest support
6. TOD surge masking

KEPT FROM ORIGINAL:
- Vulnerability multiplier
- TOD surge masking
- Light phase shift framework
- 15-minute time steps
"""

import numpy as np
import math
from datetime import datetime, timedelta
from typing import List, Optional, Tuple, Dict
from dataclasses import dataclass
import pytz

# Your existing imports
from data_models import Duty, FlightPhase, PerformancePoint
from time_on_task import TimeOnTaskModel
from sleep_debt import SleepDebtModel, SleepHistory


class AeroWakeEngine:
    """
    Gold Standard Fatigue Engine
    
    Integrates:
    - Borbély Two-Process (with sleep/wake states)
    - Time-on-Task vigilance decrement
    - Multi-day sleep debt vulnerability
    - TOD surge (adrenaline masking)
    - Light-induced circadian shifts
    """
    
    def __init__(self, config: Optional[Dict] = None):
        """
        Initialize AeroWake Engine with configuration
        
        Args:
            config: Optional configuration dictionary. Defaults to sensible values.
        """
        self.config = config or {
            # Borbély parameters
            "s_upper": 1.0,
            "s_lower": 0.1,
            "tau_i": 18.2,      # Hours - wake accumulation
            "tau_d": 4.2,       # Hours - sleep recovery
            
            # Circadian parameters
            "c_amplitude": 0.3,  # Increased from 0.1 (literature: 0.2-0.4)
            "c_peak_hour": 16.0, # Local time of peak alertness
            
            # Operational parameters
            "tod_surge_val": 0.05,    # 5% performance boost
            "light_shift_rate": 0.5,  # Hours/hour of bright light
            
            # Integration
            "interaction_exponent": 1.5,  # Non-linearity
            
            # Fallback defaults (NEW)
            "default_wake_hour": 8,      # Hour of day if not specified
            "default_initial_s": 0.3,    # Default S if no history
        }
        
        self.tot_model = TimeOnTaskModel()
        self.debt_model = SleepDebtModel()
    
    def simulate_duty(
        self, 
        duty: Duty, 
        history: SleepHistory,
        reference_timezone: str = "Asia/Qatar"  # Home base
    ) -> List[PerformancePoint]:
        """
        Primary simulation loop with all corrections applied
        
        Args:
            duty: Duty period to simulate
            history: Prior sleep history (7-day window)
            reference_timezone: Circadian reference (home base or acclimated)
        
        Returns:
            Timeline of performance points
        """
        timeline = []
        
        # ====================================================================
        # STEP 1: INITIAL STATE CALCULATION
        # ====================================================================
        
        # 1a. Sleep debt vulnerability
        debt = history.get_cumulative_debt(as_of_date=duty.date)
        restricted_nights = history.get_recent_nights_restricted()
        severity = debt / history.window_days if history.window_days > 0 else 0
        vulnerability = self.debt_model.calculate_vulnerability_modifier(
            restricted_nights, 
            severity
        )
        
        # 1b. Initial Process S (from last sleep)
        s_current = self._initialize_s_from_history(duty.report_time_utc, history)
        
        # 1c. Circadian phase adjustment (from timezone changes)
        phi_adjustment = 0.0  # Will update based on light exposure
        
        # ====================================================================
        # STEP 2: TIME-STEPPING SIMULATION
        # ====================================================================
        
        current_time = duty.report_time_utc
        dt_hours = 0.25  # 15-minute steps
        
        while current_time <= duty.release_time_utc:
            
            # ---------------------------------------------------------------
            # PHASE A: ENVIRONMENTAL FACTORS
            # ---------------------------------------------------------------
            
            # Light-induced phase shift (if crossing timezones)
            phi_adjustment += self._calculate_light_phase_shift(
                current_time, duty, dt_hours
            )
            
            # ---------------------------------------------------------------
            # PHASE B: BIOMATHEMATICAL MODEL
            # ---------------------------------------------------------------
            
            # Check if sleeping (inflight rest)
            is_sleeping = self._is_during_sleep_period(current_time, duty)
            
            # Update Process S (sleep pressure)
            s_current = self._update_s_process(
                s_current, 
                dt_hours, 
                is_sleeping
            )
            
            # Calculate Process C (circadian rhythm)
            c_value = self._calculate_c_process(
                current_time, 
                reference_timezone, 
                phi_adjustment
            )
            
            # ---------------------------------------------------------------
            # PHASE C: TIME-ON-TASK EFFECTS
            # ---------------------------------------------------------------
            
            hours_since_report = (
                (current_time - duty.report_time_utc).total_seconds() / 3600
            )
            
            # Base alertness (before time-on-task)
            base_alertness = self._integrate_s_and_c(s_current, c_value)
            
            # Time-on-task impairment
            tot_impairment = self.tot_model.calculate_time_on_task_impairment(
                hours_since_report,
                workload_level=1.0,
                baseline_fatigue=(1.0 - base_alertness)
            )
            
            # ---------------------------------------------------------------
            # PHASE D: VULNERABILITY MULTIPLICATION
            # ---------------------------------------------------------------
            
            # Sleep debt amplifies time-on-task effects
            effective_impairment = tot_impairment * vulnerability
            
            # Combined performance (multiplicative)
            raw_performance = base_alertness * (1.0 - effective_impairment)
            
            # ---------------------------------------------------------------
            # PHASE E: MASKING EFFECTS (TOD Surge)
            # ---------------------------------------------------------------
            
            current_phase = self._get_flight_phase(current_time, duty)
            masking_bonus = 0.0
            
            if current_phase in [FlightPhase.DESCENT, FlightPhase.APPROACH, FlightPhase.LANDING]:
                # Adrenaline surge during critical phases
                masking_bonus = self.config["tod_surge_val"]
            
            # Final score (0-100 scale)
            final_performance = min(1.0, raw_performance + masking_bonus) * 100
            
            # ---------------------------------------------------------------
            # PHASE F: DATA CAPTURE
            # ---------------------------------------------------------------
            
            timeline.append(PerformancePoint(
                timestamp_utc=current_time,
                raw_performance=final_performance,
                homeostatic_component=s_current,
                circadian_component=c_value,
                tot_component=tot_impairment,
                vulnerability_factor=vulnerability,
                is_masked=(masking_bonus > 0),
                current_flight_phase=current_phase
            ))
            
            # Advance time
            current_time += timedelta(minutes=15)
        
        return timeline
    
    # ========================================================================
    # CORRECTED HELPER FUNCTIONS
    # ========================================================================
    
    def _update_s_process(
        self, 
        s_current: float, 
        delta_t: float, 
        is_sleeping: bool
    ) -> float:
        """
        Update Process S (sleep homeostatic pressure)
        
        CORRECTED: Now handles both sleep and wake states
        
        Formula (wake):   S(t) = S_upper - (S_upper - S_0) * exp(-t/τ_i)
        Formula (sleep):  S(t) = S_lower + (S_0 - S_lower) * exp(-t/τ_d)
        
        Args:
            s_current: Current S value (0-1)
            delta_t: Time step in hours
            is_sleeping: Whether in sleep state
        
        Returns:
            Updated S value
        """
        if is_sleeping:
            # During sleep: S decays toward lower asymptote
            s_target = self.config["s_lower"]
            tau = self.config["tau_d"]
            return s_target + (s_current - s_target) * math.exp(-delta_t / tau)
        else:
            # During wake: S rises toward upper asymptote
            s_target = self.config["s_upper"]
            tau = self.config["tau_i"]
            return s_target - (s_target - s_current) * math.exp(-delta_t / tau)
    
    def _calculate_c_process(
        self, 
        t_utc: datetime, 
        reference_tz_str: str, 
        phi_adjustment: float
    ) -> float:
        """
        Calculate Process C (circadian rhythm)
        
        CORRECTED: Now uses proper timezone conversion
        
        Formula: C(t) = cos(2π * (t_local - φ) / 24)
        where φ = peak alertness hour (default 16:00 local)
        
        Args:
            t_utc: Current time in UTC
            reference_tz_str: Reference timezone string (e.g. "Asia/Qatar")
            phi_adjustment: Phase adjustment in hours (from light exposure)
        
        Returns:
            C value (-1 to +1)
        """
        # Convert UTC to reference timezone
        ref_tz = pytz.timezone(reference_tz_str)
        t_local = t_utc.astimezone(ref_tz)
        
        # Local hour (0-24)
        t_hour = t_local.hour + t_local.minute / 60.0 + t_local.second / 3600.0
        
        # Peak alertness hour (adjusted for light exposure)
        phi = self.config["c_peak_hour"] + phi_adjustment
        
        # Cosine wave (peak at phi, trough at phi+12)
        return math.cos(2 * math.pi * (t_hour - phi) / 24)
    
    def _integrate_s_and_c(self, s: float, c: float) -> float:
        """
        Integrate Process S and C into base alertness
        
        CORRECTED: Multiplicative integration (non-linear)
        
        Formula: Alertness = (1 - S) * (1 + A*C) / 2
        where A = circadian amplitude
        
        Args:
            s: Process S value (0-1, 0=rested, 1=maximally sleepy)
            c: Process C value (-1 to +1, circadian phase)
        
        Returns:
            Base alertness (0-1)
        """
        # S component (inverted - high S = low alertness)
        s_alertness = 1.0 - s
        
        # C component (normalized to 0-1 range)
        # C ranges from -1 to +1, we want 0 to 1
        c_alertness = (1.0 + self.config["c_amplitude"] * c) / \
                      (1.0 + self.config["c_amplitude"])
        
        # Multiplicative combination
        base_alertness = s_alertness * c_alertness
        
        return base_alertness
    
    def _initialize_s_from_history(
        self, 
        report_time_utc: datetime, 
        history: SleepHistory
    ) -> float:
        """
        Calculates starting Sleep Pressure based on the time elapsed 
        since the last known wake event.
        
        CORRECTED: Implements tiered fallback for wake time:
        1. Direct data: last_sleep.wake_time_utc
        2. Configurable default: config["default_wake_hour"]
        3. Engine default: 08:00 UTC
        
        Also handles edge case where report time is before wake time
        (e.g., night shift crossing midnight).
        
        Args:
            report_time_utc: When the duty starts (UTC)
            history: Sleep history object
        
        Returns:
            Initial S value at report time
        """
        # If no sleep history, return default
        if not history.daily_sleep:
            return self.config.get("default_initial_s", 0.3)

        last_sleep = history.daily_sleep[-1]
        
        # ========================================================================
        # TIER 1: ACTUAL WAKE TIME (if available)
        # ========================================================================
        if hasattr(last_sleep, 'wake_time_utc') and last_sleep.wake_time_utc:
            wake_time = last_sleep.wake_time_utc
        else:
            # ====================================================================
            # TIER 2: CONFIGURED DEFAULT HOUR
            # ====================================================================
            default_hour = self.config.get("default_wake_hour", 8)
            wake_time = datetime.combine(
                last_sleep.date, 
                datetime.min.time()
            ).replace(hour=default_hour, tzinfo=pytz.utc)

        # ====================================================================
        # CALCULATE TIME ELAPSED
        # ====================================================================
        hours_awake = (report_time_utc - wake_time).total_seconds() / 3600
        
        # ====================================================================
        # EDGE CASE: NEGATIVE HOURS (Report before wake - night shift)
        # ====================================================================
        if hours_awake < 0:
            # If the math says they reported before they woke up, 
            # assume they just woke up (minimum sleep pressure).
            print(f"⚠️  Report time before wake time: {hours_awake:.1f}h")
            print("    Assuming just woken (S = s_lower)")
            return self.config["s_lower"]

        # ====================================================================
        # EVOLVE S FROM WAKE TO REPORT
        # ====================================================================
        s_at_wake = self.config["s_lower"]
        s_at_report = self._update_s_process(s_at_wake, hours_awake, is_sleeping=False)
        
        return s_at_report
    
    def _is_during_sleep_period(
        self, 
        current_time: datetime, 
        duty: Duty
    ) -> bool:
        """
        Check if current time is during inflight rest period
        
        Args:
            current_time: Current simulation time (UTC)
            duty: Duty object
        
        Returns:
            True if pilot is sleeping (inflight rest)
        """
        # Check if duty has defined sleep windows
        if not hasattr(duty, 'sleep_windows') or not duty.sleep_windows:
            return False
        
        for sleep_window in duty.sleep_windows:
            if sleep_window.start_time_utc <= current_time <= sleep_window.end_time_utc:
                return True
        
        return False
    
    def _calculate_light_phase_shift(
        self, 
        current_time: datetime, 
        duty: Duty, 
        delta_t: float
    ) -> float:
        """
        Calculate circadian phase shift from light exposure
        
        Placeholder for sophisticated geo-spatial light modeling
        
        In production:
        - Calculate solar position
        - Determine if in cockpit with sunlight
        - Apply phase shift based on direction (advance/delay)
        
        Args:
            current_time: Current time (UTC)
            duty: Duty object with segment information
            delta_t: Time step in hours
        
        Returns:
            Hours of phase shift (can be negative for delay)
        """
        # TODO: Implement full solar position calculation
        # For now, return 0 (no shift)
        return 0.0
    
    def _get_flight_phase(
        self, 
        current_time: datetime, 
        duty: Duty
    ) -> FlightPhase:
        """
        Determine current flight phase for TOD surge detection
        
        Logic:
        - Last 45min of segment = DESCENT/APPROACH
        - First 30min = TAKEOFF/CLIMB
        - Middle = CRUISE
        - On ground = PREFLIGHT or POSTFLIGHT
        
        Args:
            current_time: Current simulation time (UTC)
            duty: Duty object with segments
        
        Returns:
            Current FlightPhase enum
        """
        if not duty.segments:
            return FlightPhase.PREFLIGHT
        
        for segment in duty.segments:
            # Check if we're in this segment
            if segment.scheduled_departure_utc <= current_time <= segment.scheduled_arrival_utc:
                
                # Time into segment
                time_since_dep = (current_time - segment.scheduled_departure_utc).total_seconds() / 60
                time_to_arr = (segment.scheduled_arrival_utc - current_time).total_seconds() / 60
                
                # Phase determination
                if time_since_dep <= 30:
                    return FlightPhase.TAKEOFF
                elif time_to_arr <= 45:
                    # TOD surge region
                    if time_to_arr <= 15:
                        return FlightPhase.LANDING
                    elif time_to_arr <= 30:
                        return FlightPhase.APPROACH
                    else:
                        return FlightPhase.DESCENT
                else:
                    return FlightPhase.CRUISE
        
        # Between segments or after last segment
        return FlightPhase.POSTFLIGHT
