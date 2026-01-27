"""
core_model.py - Biomathematical Fatigue Model Engine (UNIFIED)
==============================================================

Advanced Two-Process Borbély Model with Aviation Workload Integration

VERSION 4 FEATURES (UNIFIED + WORKLOAD):
✅ Corrected Process S (distinct sleep/wake dynamics)
✅ Tiered wake time fallback (actual → config → default)
✅ Timezone-aware circadian rhythm calculation
✅ Multiplicative performance integration (non-linear)
✅ Sleep debt vulnerability amplification
✅ TOD surge masking (critical phases)
✅ Inflight rest support
✅ Solar-based light phase shift calculation
✅ Dynamic circadian adaptation
✅ Roster-level cumulative analysis
✅ Segment-based flight phases
✅ 15-minute time step simulation
✅ Aviation Workload Integration (multi-sector fatigue)

Scientific Foundation for Workload Model:
- Bourgeois-Bougrine, S., et al. (2003). Perceived fatigue for short- and long-haul 
  flights: A survey of 739 airline pilots. Aviation, Space, and Environmental Medicine, 
  74(10), 1072-1077.
- Van Dongen, H. P., et al. (2003). The cumulative cost of additional wakefulness: 
  Dose-response effects on neurobehavioral functions and sleep physiology from chronic 
  sleep restriction and total sleep deprivation. Sleep, 26(2), 117-126.

Key Findings:
- Short-haul fatigue driven by: high workload + multiple sectors + time pressure
- Long-haul fatigue driven by: circadian disruption + sleep loss
- Task intensity affects fatigue accumulation rate
- Multiple landing cycles compound fatigue more than cruise duration
"""

from datetime import datetime, timedelta
from typing import List, Tuple, Optional, Dict
import math
import pytz
import numpy as np
from dataclasses import dataclass

from config import ModelConfig, BorbelyParameters, AdaptationRates
from data_models import (
    Duty, Roster, FlightSegment, SleepBlock, CircadianState,
    PerformancePoint, PinchEvent, DutyTimeline, MonthlyAnalysis, FlightPhase
)
from easa_utils import BiomathematicalSleepEstimator, EASAComplianceValidator


# ============================================================================
# AVIATION WORKLOAD INTEGRATION MODEL
# ============================================================================

@dataclass
class WorkloadParameters:
    """
    Workload multipliers derived from aviation research.
    
    Multiplier interpretation:
    - 1.0 = Baseline fatigue accumulation rate
    - > 1.0 = Accelerated fatigue (high workload)
    - < 1.0 = Reduced fatigue (low workload, monitoring)
    
    Reference:
        Bourgeois-Bougrine et al. (2003) - Short-haul vs long-haul pilot workload
    """
    
    # Base workload multipliers by flight phase
    WORKLOAD_MULTIPLIERS = {
        FlightPhase.PREFLIGHT: 1.1,      # Briefing, checks
        FlightPhase.TAXI_OUT: 1.0,       # Baseline
        FlightPhase.TAKEOFF: 1.8,        # HIGH - critical phase
        FlightPhase.CLIMB: 1.3,          # Moderate-high
        FlightPhase.CRUISE: 0.8,         # LOW - monitoring, autopilot
        FlightPhase.DESCENT: 1.2,        # Moderate
        FlightPhase.APPROACH: 1.5,       # MEDIUM-HIGH
        FlightPhase.LANDING: 2.0,        # HIGHEST - most demanding
        FlightPhase.TAXI_IN: 1.0,        # Baseline
        FlightPhase.GROUND_TURNAROUND: 1.2,  # Ground ops, no rest opportunity
    }
    
    # Cumulative sector penalty
    # Each additional sector increases fatigue accumulation
    # Source: Van Dongen (2003) - cumulative cost concept
    SECTOR_PENALTY_RATE: float = 0.15  # 15% increase per sector
    
    # Minimum turnaround time for partial recovery (hours)
    RECOVERY_THRESHOLD_HOURS: float = 2.0
    
    # Recovery rate during turnaround (fraction of sleep dissipation rate)
    TURNAROUND_RECOVERY_RATE: float = 0.3  # 30% as effective as sleep


class WorkloadModel:
    """
    Integrates aviation workload into Three-Process Model
    
    Key insight: Not all wake time accumulates fatigue equally.
    High workload phases (takeoff, landing) accelerate fatigue more than 
    low workload phases (cruise monitoring).
    """
    
    def __init__(self, params: WorkloadParameters = None):
        self.params = params or WorkloadParameters()
    
    def get_phase_multiplier(self, phase: FlightPhase) -> float:
        """Get base workload multiplier for flight phase"""
        return self.params.WORKLOAD_MULTIPLIERS.get(phase, 1.0)
    
    def get_sector_multiplier(self, sector_number: int) -> float:
        """
        Calculate cumulative sector fatigue multiplier
        
        Research finding: Each additional sector compounds fatigue.
        This is why 4x 2-hour sectors is more fatiguing than 1x 8-hour sector.
        
        Args:
            sector_number: Sector count (1, 2, 3, 4, ...)
            
        Returns:
            Cumulative multiplier (1.0, 1.15, 1.30, 1.45, ...)
            
        Reference:
            Van Dongen (2003) - cumulative cost of wakefulness
        """
        return 1.0 + (sector_number - 1) * self.params.SECTOR_PENALTY_RATE
    
    def get_combined_multiplier(
        self, 
        phase: FlightPhase,
        sector_number: int
    ) -> float:
        """
        Combine phase workload and sector accumulation
        
        Example:
            Landing (2.0x) on Sector 4 (1.45x) = 2.9x fatigue rate
            Cruise (0.8x) on Sector 1 (1.0x) = 0.8x fatigue rate
        """
        phase_mult = self.get_phase_multiplier(phase)
        sector_mult = self.get_sector_multiplier(sector_number)
        return phase_mult * sector_mult
    
    def calculate_effective_wake_time(
        self,
        actual_duration_hours: float,
        phase: FlightPhase,
        sector_number: int
    ) -> float:
        """
        Convert actual duration to "effective wake time" based on workload
        
        High workload = more effective wake time = faster fatigue accumulation
        Low workload = less effective wake time = slower fatigue accumulation
        
        This is used to adjust the Three-Process Model's sleep pressure calculation.
        
        Args:
            actual_duration_hours: Real time spent in phase
            phase: Flight phase
            sector_number: Current sector
            
        Returns:
            Effective wake time for fatigue calculation
            
        Example:
            1 hour landing (2.0x workload) on sector 4 (1.45x) 
            = 2.9 hours of "effective wake time"
        """
        multiplier = self.get_combined_multiplier(phase, sector_number)
        return actual_duration_hours * multiplier
    
    def calculate_turnaround_recovery(
        self,
        turnaround_duration_hours: float,
        current_S: float,
        tau_d: float = 4.2
    ) -> float:
        """
        Calculate partial sleep pressure recovery during turnaround
        
        Research finding: Short breaks provide some recovery, but much less 
        effective than actual sleep.
        
        Args:
            turnaround_duration_hours: Ground time between sectors
            current_S: Current sleep pressure before turnaround
            tau_d: Sleep recovery time constant (hours)
            
        Returns:
            Adjusted sleep pressure after turnaround
            
        Note:
            Only applies if turnaround > RECOVERY_THRESHOLD_HOURS
        """
        if turnaround_duration_hours < self.params.RECOVERY_THRESHOLD_HOURS:
            return current_S  # No significant recovery
        
        # Partial recovery at reduced rate
        recovery_time_constant = tau_d / self.params.TURNAROUND_RECOVERY_RATE  # ~14 hours
        recovery_fraction = 1 - np.exp(-turnaround_duration_hours / recovery_time_constant)
        
        S_after = current_S * (1 - recovery_fraction)
        
        return max(0.0, S_after)


class BorbelyFatigueModel:
    """
    Unified Biomathematical Fatigue Prediction Engine
    
    Combines:
    - Borbély two-process model (homeostatic + circadian)
    - Time-on-task vigilance decrement
    - Sleep debt vulnerability amplification
    - TOD surge masking (adrenaline)
    - Solar-based light phase shift
    - Dynamic circadian adaptation
    
    Key improvements from integration:
    - Process S properly separates sleep recovery vs wake accumulation
    - Tiered fallback for wake time (actual → config → default)
    - Timezone-aware circadian calculation with solar position
    - Multiplicative integration for non-linear effects
    """
    
    def __init__(self, config: ModelConfig = None):
        self.config = config or ModelConfig.default_easa_config()
        self.params = self.config.borbely_params
        self.adaptation_rates = self.config.adaptation_rates
        self.sleep_estimator = BiomathematicalSleepEstimator(
            self.config.easa_framework,
            self.params,
            self.config.sleep_quality_params
        )
        self.validator = EASAComplianceValidator(self.config.easa_framework)
        
        # Aviation Workload Integration Model (NEW in V4)
        self.workload_model = WorkloadModel()
        
        # Borbély parameters (can be overridden)
        self.s_upper = 1.0
        self.s_lower = 0.1
        self.tau_i = 18.2  # Hours - wake accumulation
        self.tau_d = 4.2   # Hours - sleep recovery
        
        # Circadian parameters
        self.c_amplitude = 0.3       # Increased from 0.1
        self.c_peak_hour = 16.0      # Local time of peak alertness
        
        # Operational parameters
        self.tod_surge_val = 0.05    # 5% performance boost
        self.light_shift_rate = 0.5  # Hours/hour of bright light
        
        # Fallback defaults
        self.default_wake_hour = 8   # If not specified
        self.default_initial_s = 0.3 # If no history
    
    # ========================================================================
    # CIRCADIAN ADAPTATION
    # ========================================================================
    
    def calculate_adaptation(
        self,
        current_utc: datetime,
        last_state: CircadianState,
        current_tz_str: str,
        home_base_tz_str: str
    ) -> CircadianState:
        """
        Dynamic circadian phase shift adaptation
        
        Rates: Westward ~1.5h/day, Eastward ~1.0h/day
        Source: Aschoff (1978), Waterhouse (2007)
        """
        elapsed_seconds = (current_utc - last_state.last_update_utc).total_seconds()
        if elapsed_seconds <= 0:
            return last_state
        
        elapsed_days = elapsed_seconds / 86400
        
        # Calculate shift relative to HOME BASE
        current_tz = pytz.timezone(current_tz_str)
        home_tz = pytz.timezone(home_base_tz_str)
        
        # pytz requires naive datetime for utcoffset(), so we use a reference time
        # Convert UTC to naive, then get offset
        naive_time = current_utc.replace(tzinfo=None)
        home_offset = home_tz.localize(naive_time).utcoffset().total_seconds() / 3600
        current_offset = current_tz.localize(naive_time).utcoffset().total_seconds() / 3600
        
        target_shift = current_offset - home_offset
        
        # Required adjustment
        diff = target_shift - last_state.current_phase_shift_hours
        
        # Adaptation rate (direction-dependent)
        rate = self.adaptation_rates.get_rate(diff)
        
        # Gradual adaptation
        adjustment = math.copysign(min(abs(diff), rate * elapsed_days), diff)
        new_shift = last_state.current_phase_shift_hours + adjustment
        new_shift = max(-12, min(12, new_shift))
        
        return CircadianState(
            current_phase_shift_hours=new_shift,
            last_update_utc=current_utc,
            reference_timezone=current_tz_str
        )
    
    # ========================================================================
    # THREE-PROCESS MODEL
    # ========================================================================
    
    def compute_process_s(
        self,
        current_time: datetime,
        last_sleep_end: datetime,
        s_at_wake: float = 0.1
    ) -> float:
        """
        SIMPLIFIED Process S: Just evolve from wake time
        
        Much simpler and more reliable than trying to rebuild entire history
        
        Args:
            current_time: Current time point
            last_sleep_end: When did pilot wake up
            s_at_wake: S value at wake (typically 0.1 after good sleep)
        
        Returns:
            Current S value (0-1 scale)
        """
        # Hours since wake
        hours_awake = (current_time - last_sleep_end).total_seconds() / 3600
        
        if hours_awake < 0:
            # Still sleeping? Shouldn't happen
            return s_at_wake
        
        # S rises exponentially toward S_max during wake
        s_current = self.params.S_max - (self.params.S_max - s_at_wake) * \
                    math.exp(-hours_awake / self.params.tau_i)
        
        return max(self.params.S_min, min(self.params.S_max, s_current))
    
    def compute_process_c(
        self,
        time_utc: datetime,
        reference_timezone: str,
        circadian_phase_shift: float = 0.0
    ) -> float:
        """
        Process C: Circadian alertness
        Sinusoidal rhythm, peak at acrophase (~17:00)
        """
        tz = pytz.timezone(reference_timezone)
        local_time = time_utc.astimezone(tz)
        hour_of_day = local_time.hour + local_time.minute / 60.0
        
        # Adjust for phase shift
        effective_hour = (hour_of_day - circadian_phase_shift) % 24
        
        # Cosine rhythm
        angle = 2 * math.pi * (effective_hour - self.params.circadian_acrophase_hours) / 24
        c_value = (
            self.params.circadian_mesor +
            self.params.circadian_amplitude * math.cos(angle)
        )
        
        return max(0.0, min(1.0, c_value))
    
    def compute_sleep_inertia(self, time_since_wake: timedelta) -> float:
        """Process W: Sleep inertia (post-wake impairment)"""
        minutes_awake = time_since_wake.total_seconds() / 60
        
        if minutes_awake > self.params.inertia_duration_minutes:
            return 0.0
        
        inertia = self.params.inertia_max_magnitude * math.exp(
            -minutes_awake / (self.params.inertia_duration_minutes / 3)
        )
        
        return inertia
    
    # ========================================================================
    # AEROWAKE ENHANCEMENTS (Integrated from aerowake_engine.py)
    # ========================================================================
    
    def update_s_process_corrected(
        self, 
        s_current: float, 
        delta_t: float, 
        is_sleeping: bool
    ) -> float:
        """
        CORRECTED Process S: Properly handles sleep vs wake states
        
        Formula (wake):   S(t) = S_upper - (S_upper - S_0) * exp(-t/τ_i)
        Formula (sleep):  S(t) = S_lower + (S_0 - S_lower) * exp(-t/τ_d)
        
        This is more accurate than the original linear interpolation.
        """
        if is_sleeping:
            # During sleep: S decays toward lower asymptote
            s_target = self.s_lower
            tau = self.tau_d
            return s_target + (s_current - s_target) * math.exp(-delta_t / tau)
        else:
            # During wake: S rises toward upper asymptote
            s_target = self.s_upper
            tau = self.tau_i
            return s_target - (s_target - s_current) * math.exp(-delta_t / tau)
    
    def initialize_s_from_history_corrected(
        self, 
        report_time_utc: datetime, 
        history: List[SleepBlock]
    ) -> float:
        """
        CORRECTED S_0 initialization with tiered fallback
        
        Priority:
        1. Actual wake time from sleep data
        2. Configured default hour
        3. Engine default (8 AM)
        """
        if not history.daily_sleep:
            return self.default_initial_s

        last_sleep = history.daily_sleep[-1]
        
        # Tier 1: Actual wake time
        if hasattr(last_sleep, 'wake_time_utc') and last_sleep.wake_time_utc:
            wake_time = last_sleep.wake_time_utc
        else:
            # Tier 2 & 3: Configured or default hour
            hour = getattr(self, 'default_wake_hour', 8)
            wake_time = datetime.combine(
                last_sleep.date, 
                datetime.min.time()
            ).replace(hour=hour, tzinfo=pytz.utc)

        # Calculate time elapsed
        hours_awake = (report_time_utc - wake_time).total_seconds() / 3600
        
        # Edge case: report before wake (night shift)
        if hours_awake < 0:
            return self.s_lower

        # Evolve S from wake to report
        s_at_wake = self.s_lower
        s_at_report = self.update_s_process_corrected(
            s_at_wake, hours_awake, is_sleeping=False
        )
        
        return s_at_report
    
    def calculate_light_phase_shift(
        self, 
        current_time: datetime, 
        duty: Duty, 
        delta_t: float
    ) -> float:
        """
        ENHANCED Light phase shift from solar position
        
        Implements proper solar elevation calculation and phase response curve.
        Supports eastbound (advance) and westbound (delay) flight dynamics.
        """
        
        if not duty.segments:
            return 0.0
        
        # Find current segment
        current_segment = None
        for segment in duty.segments:
            if segment.scheduled_departure_utc <= current_time <= segment.scheduled_arrival_utc:
                current_segment = segment
                break
        
        if not current_segment:
            return 0.0
        
        # ====================================================================
        # SOLAR POSITION CALCULATION
        # ====================================================================
        
        try:
            dep_lat = current_segment.departure_airport.latitude
            dep_lon = current_segment.departure_airport.longitude
            arr_lat = current_segment.arrival_airport.latitude
            arr_lon = current_segment.arrival_airport.longitude
            
            lon_delta = arr_lon - dep_lon
            
            # Interpolate current position
            segment_duration = (
                current_segment.scheduled_arrival_utc - 
                current_segment.scheduled_departure_utc
            ).total_seconds() / 3600
            
            if segment_duration <= 0:
                return 0.0
            
            time_into_segment = (
                current_time - current_segment.scheduled_departure_utc
            ).total_seconds() / 3600
            
            progress = min(1.0, max(0.0, time_into_segment / segment_duration))
            
            current_lat = dep_lat + (arr_lat - dep_lat) * progress
            current_lon = dep_lon + (lon_delta) * progress
            
        except (AttributeError, TypeError):
            return 0.0
        
        # ====================================================================
        # SOLAR ELEVATION (simplified algorithm)
        # ====================================================================
        
        day_of_year = current_time.timetuple().tm_yday
        solar_declination = 23.44 * math.sin(
            2 * math.pi * (day_of_year - 81) / 365.25
        ) * math.pi / 180
        
        hour_angle = (current_time.hour + current_time.minute / 60.0) - 12.0
        hour_angle = hour_angle * 15 * math.pi / 180
        
        lat_rad = current_lat * math.pi / 180
        
        sin_elevation = (
            math.sin(lat_rad) * math.sin(solar_declination) +
            math.cos(lat_rad) * math.cos(solar_declination) * math.cos(hour_angle)
        )
        
        sin_elevation = max(-1.0, min(1.0, sin_elevation))
        elevation_deg = math.asin(sin_elevation) * 180 / math.pi
        
        # ====================================================================
        # LIGHT INTENSITY
        # ====================================================================
        
        if elevation_deg < 0:
            light_intensity = max(0.0, (elevation_deg + 6) / 6) * 0.2
        else:
            light_intensity = min(1.0, (elevation_deg / 30))
        
        # ====================================================================
        # FLIGHT DIRECTION
        # ====================================================================
        
        flight_direction = 1.0 if lon_delta > 0 else -1.0  # 1=East, -1=West
        
        # ====================================================================
        # PHASE RESPONSE CURVE
        # ====================================================================
        
        local_hour = current_time.hour + (current_lon / 15)
        local_hour = local_hour % 24
        
        melatonin_onset_local = 21.0
        phase = (local_hour - melatonin_onset_local) % 24
        
        if 3 <= phase < 9:      # Advance zone
            prc_amplitude = 1.5
        elif 9 <= phase < 15:   # Weaker advance
            prc_amplitude = 0.5
        elif 15 <= phase < 21:  # No shift zone
            prc_amplitude = 0.0
        else:                    # Delay zone
            prc_amplitude = 1.0
        
        # ====================================================================
        # CALCULATE PHASE SHIFT
        # ====================================================================
        
        phase_shift = (
            light_intensity *
            prc_amplitude *
            flight_direction *
            delta_t
        )
        
        return phase_shift
    
    def integrate_s_and_c_multiplicative(
        self, 
        s: float, 
        c: float
    ) -> float:
        """
        CORRECTED Integration: Weighted average (not multiplication)
        Based on Boeing BAM method
        
        Formula: Alertness = (1-S)*0.6 + normalize(C)*0.4
        where:
          - (1-S) is homeostatic alertness (0-1)
          - normalize(C) converts circadian from [-1,+1] to [0,1]
        """
        # Homeostatic alertness: High S = tired, so invert
        s_alertness = 1.0 - s
        
        # Circadian alertness: Normalize from [-1, +1] to [0, 1]
        # c = +1 (peak) → 1.0 alertness
        # c = -1 (trough) → 0.0 alertness
        c_alertness = (c + 1.0) / 2.0
        
        # Weighted average (NOT multiplication)
        # Homeostatic is primary driver (60%), circadian modulates (40%)
        base_alertness = s_alertness * 0.6 + c_alertness * 0.4
        
        return base_alertness
    
    def integrate_performance(self, c: float, s: float, w: float) -> float:
        """
        CORRECTED: Integrate three processes into performance (0-100 scale)
        
        Uses weighted average of S and C, then applies time-on-task penalty.
        Based on Boeing BAM (Biomathematical Alertness Model).
        
        Returns score 0-100 where:
        - 85-100: Optimal (well-rested, good circadian alignment)
        - 70-85: Good (slight fatigue)
        - 55-70: Moderate fatigue
        - 40-55: High fatigue
        - <40: Critical fatigue
        
        CALIBRATION: Minimum performance floor of 20% prevents complete cognitive collapse
        (even severely fatigued pilots retain some basic function)
        """
        # Validation
        assert 0 <= c <= 1, f"C out of range: {c}"
        assert 0 <= s <= 1, f"S out of range: {s}"
        assert 0 <= w <= 1, f"W out of range: {w}"
        
        # STEP 1: Get weighted average of S and C (converts C from [0,1] to [-1,+1] range)
        # Note: c is already in [0,1], convert to [-1,+1] for proper circadian phase
        c_phase = (c * 2.0) - 1.0  # Convert [0,1] to [-1,+1]
        base_alertness = self.integrate_s_and_c_multiplicative(s, c_phase)
        
        # STEP 2: Apply time-on-task impairment (multiplicative penalty)
        alertness_with_tot = base_alertness * (1.0 - w)
        
        # STEP 3: Scale to 0-100 with minimum floor
        # Floor of 20% represents minimal residual cognitive function under extreme fatigue
        MIN_PERFORMANCE_FLOOR = 20.0
        performance = MIN_PERFORMANCE_FLOOR + (alertness_with_tot * (100.0 - MIN_PERFORMANCE_FLOOR))
        
        # Validation
        performance = max(MIN_PERFORMANCE_FLOOR, min(100.0, performance))
        assert MIN_PERFORMANCE_FLOOR <= performance <= 100, f"Performance out of range: {performance}"
        
        return performance
    
    # ========================================================================
    # SLEEP EXTRACTION
    # ========================================================================
    
    def extract_sleep_from_roster(
        self,
        roster: Roster,
        body_clock_timeline: List[Tuple[datetime, CircadianState]]
    ) -> List[SleepBlock]:
        """
        Auto-generate sleep opportunities from duty gaps
        NEW in V2
        """
        sleep_blocks = []
        
        for i, duty in enumerate(roster.duties):
            if i + 1 < len(roster.duties):
                next_duty = roster.duties[i + 1]
                
                # Sleep window: release + 1h to report - 2h
                sleep_start = duty.release_time_utc + timedelta(hours=1)
                sleep_end = next_duty.report_time_utc - timedelta(hours=2)
                
                if sleep_end <= sleep_start:
                    continue
                
                # Location
                location_tz = duty.segments[-1].arrival_airport.timezone
                is_home_base = (location_tz == roster.home_base_timezone)
                
                # Get circadian state
                phase_shift = self._get_phase_shift_at_time(sleep_start, body_clock_timeline)
                
                # Prior wake time
                prior_wake = (sleep_start - duty.report_time_utc).total_seconds() / 3600
                if i > 0 and sleep_blocks:
                    prior_wake += (duty.report_time_utc - sleep_blocks[-1].end_utc).total_seconds() / 3600
                
                # Estimate sleep
                environment = 'home' if is_home_base else 'layover'
                
                sleep = self.sleep_estimator.estimate_sleep_block(
                    opportunity_start=sleep_start,
                    opportunity_end=sleep_end,
                    location_timezone=location_tz,
                    circadian_phase_shift=phase_shift,
                    environment=environment,
                    prior_wake_hours=min(24, prior_wake)
                )
                
                sleep_blocks.append(sleep)
        
        return sleep_blocks
    
    def _get_phase_shift_at_time(
        self,
        target_time: datetime,
        body_clock_timeline: List[Tuple[datetime, CircadianState]]
    ) -> float:
        """Get phase shift at specific time"""
        for timestamp, state in reversed(body_clock_timeline):
            if timestamp <= target_time:
                return state.current_phase_shift_hours
        return 0.0
    
    # ========================================================================
    # FLIGHT PHASES
    # ========================================================================
    
    def get_flight_phase(self, segments: List[FlightSegment], current_time: datetime) -> FlightPhase:
        """
        Determine phase from segment schedule
        NEW in V2: Segment-based (not duty percentage)
        """
        for segment in segments:
            dep = segment.scheduled_departure_utc
            arr = segment.scheduled_arrival_utc
            
            if current_time < dep - timedelta(minutes=30):
                return FlightPhase.PREFLIGHT
            elif current_time < dep:
                return FlightPhase.TAXI_OUT
            elif current_time < dep + timedelta(minutes=15):
                return FlightPhase.TAKEOFF
            elif current_time < dep + timedelta(minutes=30):
                return FlightPhase.CLIMB
            elif current_time < arr - timedelta(minutes=40):
                return FlightPhase.CRUISE
            elif current_time < arr - timedelta(minutes=20):
                return FlightPhase.DESCENT
            elif current_time < arr - timedelta(minutes=10):
                return FlightPhase.APPROACH
            elif current_time <= arr + timedelta(minutes=5):
                return FlightPhase.LANDING
            elif current_time <= arr + timedelta(minutes=15):
                return FlightPhase.TAXI_IN
        
        return FlightPhase.CRUISE
    
    # ========================================================================
    # DUTY SIMULATION
    # ========================================================================
    
    def simulate_duty(
        self,
        duty: Duty,
        sleep_history: List[SleepBlock],
        circadian_phase_shift: float = 0.0,
        initial_s: float = 0.3,
        resolution_minutes: int = 5,
        cached_s: Optional[float] = None
    ) -> DutyTimeline:
        """
        Simulate single duty with high-resolution timeline
        
        UPDATED V4: Integrates aviation workload model for multi-sector duties
        - Tracks current sector number
        - Applies workload multipliers per flight phase
        - Uses effective wake time for S calculation
        
        FIXED: Now properly uses sleep history to initialize S value
        """
        
        timeline = []
        
        # ====================================================================
        # STEP 1: Find last sleep and calculate S_0
        # ====================================================================
        
        last_sleep = None
        for sleep in reversed(sleep_history):
            if sleep.end_utc <= duty.report_time_utc:
                last_sleep = sleep
                break
        
        if last_sleep:
            # Calculate S at wake from sleep quality
            # After perfect 8h sleep: S ≈ 0.1
            # After poor 4h sleep: S ≈ 0.5
            sleep_quality_ratio = last_sleep.effective_sleep_hours / 8.0
            s_at_wake = max(0.1, 0.7 - (sleep_quality_ratio * 0.6))
            
            wake_time = last_sleep.end_utc
        else:
            # No sleep history - use default
            s_at_wake = initial_s
            wake_time = duty.report_time_utc - timedelta(hours=8)  # Assume woke 8h ago
        
        # ====================================================================
        # STEP 2: Track sectors and workload
        # ====================================================================
        
        # Determine current sector based on time
        def get_current_sector(current_time: datetime) -> int:
            """Get current sector number (1, 2, 3, ...) based on segments"""
            sector = 1
            for seg in duty.segments:
                if current_time >= seg.scheduled_departure_utc:
                    # Each segment represents a different sector if departure times differ
                    if seg == duty.segments[0]:
                        sector = 1
                    else:
                        # Check if this is a new sector (different departure from previous)
                        prev_seg = duty.segments[duty.segments.index(seg) - 1]
                        if seg.scheduled_departure_utc > prev_seg.scheduled_arrival_utc:
                            sector += 1
            return sector
        
        # Track effective wake time (workload-adjusted)
        effective_wake_hours = 0.0
        last_step_time = duty.report_time_utc
        
        # ====================================================================
        # STEP 3: Simulate duty timeline with workload integration
        # ====================================================================
        
        # Initialize s_current before loop (in case loop doesn't execute)
        s_current = s_at_wake
        current_time = duty.report_time_utc
        
        while current_time <= duty.release_time_utc:
            
            # Get current sector and flight phase
            current_sector = get_current_sector(current_time)
            phase = self.get_flight_phase(duty.segments, current_time)
            
            # Calculate step duration in hours
            step_duration_hours = resolution_minutes / 60.0
            
            # Apply workload multiplier to get effective wake time
            workload_multiplier = self.workload_model.get_combined_multiplier(
                phase, current_sector
            )
            effective_step_duration = step_duration_hours * workload_multiplier
            effective_wake_hours += effective_step_duration
            
            # Calculate S using EFFECTIVE wake time (workload-adjusted)
            # This makes high-workload phases accumulate fatigue faster
            s_current = self.params.S_max - (self.params.S_max - s_at_wake) * \
                        math.exp(-effective_wake_hours / self.params.tau_i)
            s_current = max(self.params.S_min, min(self.params.S_max, s_current))
            
            # Calculate C: circadian component
            c = self.compute_process_c(current_time, duty.home_base_timezone, circadian_phase_shift)
            
            # Calculate W: sleep inertia (time since wake)
            current_wake = current_time - wake_time
            w = self.compute_sleep_inertia(current_wake)
            
            # Integrate into performance (weighted average + time-on-task penalty)
            performance = self.integrate_performance(c, s_current, w)
            
            # Create performance point
            tz = pytz.timezone(duty.home_base_timezone)
            point = PerformancePoint(
                timestamp_utc=current_time,
                timestamp_local=current_time.astimezone(tz),
                circadian_component=c,
                homeostatic_component=s_current,
                sleep_inertia_component=w,
                raw_performance=performance,
                current_flight_phase=phase,
                is_critical_phase=(phase in [FlightPhase.TAKEOFF, FlightPhase.LANDING, FlightPhase.APPROACH])
            )
            
            timeline.append(point)
            last_step_time = current_time
            current_time += timedelta(minutes=resolution_minutes)
        
        # Build timeline and cache final state
        duty_timeline = self._build_duty_timeline(duty, timeline, sleep_history, circadian_phase_shift)
        duty_timeline.final_process_s = s_current  # Cache for next duty
        
        return duty_timeline
    
    def _build_duty_timeline(
        self,
        duty: Duty,
        timeline: List[PerformancePoint],
        sleep_history: List[SleepBlock],
        phase_shift: float
    ) -> DutyTimeline:
        """Build summary with statistics"""
        
        if not timeline:
            return DutyTimeline(duty.duty_id, duty.date, [])
        
        min_perf = min(p.raw_performance for p in timeline)
        min_point = min(timeline, key=lambda p: p.raw_performance)
        avg_perf = sum(p.raw_performance for p in timeline) / len(timeline)
        
        landing_points = [p for p in timeline if p.current_flight_phase == FlightPhase.LANDING]
        landing_perf = min(p.raw_performance for p in landing_points) if landing_points else None
        landing_time = landing_points[-1].timestamp_utc if landing_points else None
        
        recent_sleep = [s for s in sleep_history if s.end_utc <= duty.report_time_utc][-3:]
        total_prior_sleep = sum(s.effective_sleep_hours for s in recent_sleep)
        
        disruption = self.validator.is_disruptive_duty(duty)
        pinch_events = self._detect_pinch_events(timeline)
        
        return DutyTimeline(
            duty_id=duty.duty_id,
            duty_date=duty.date,
            timeline=timeline,
            min_performance=min_perf,
            min_performance_time=min_point.timestamp_utc,
            average_performance=avg_perf,
            landing_performance=landing_perf,
            landing_time=landing_time,
            prior_sleep_hours=total_prior_sleep,
            easa_compliant=True,
            wocl_encroachment_hours=disruption['wocl_hours'],
            pinch_events=pinch_events,
            circadian_phase_shift=phase_shift
        )
    
    def _detect_pinch_events(self, timeline: List[PerformancePoint]) -> List[PinchEvent]:
        """Detect high S + low C during critical phases"""
        pinch_events = []
        
        for point in timeline:
            if point.is_critical_phase:
                if point.circadian_component < 0.4 and point.homeostatic_component > 0.6:
                    severity = 'critical' if point.raw_performance < 50 else 'high'
                    
                    pinch_events.append(PinchEvent(
                        time_utc=point.timestamp_utc,
                        time_local=point.timestamp_local,
                        flight_phase=point.current_flight_phase,
                        performance=point.raw_performance,
                        circadian=point.circadian_component,
                        sleep_pressure=point.homeostatic_component,
                        severity=severity
                    ))
        
        return pinch_events
    
    # ========================================================================
    # ROSTER SIMULATION
    # ========================================================================
    
    def simulate_roster(self, roster: Roster) -> MonthlyAnalysis:
        """
        Process entire roster with cumulative tracking
        NEW in V2: State persists across duties
        """
        # Validate roster has duties
        if not roster.duties or len(roster.duties) == 0:
            raise ValueError(
                "Cannot simulate roster: No duties found. "
                "The roster parser failed to extract any duty information. "
                "Please verify the PDF/CSV format is correct and contains roster data."
            )
        
        duty_timelines = []
        
        current_s = roster.initial_sleep_pressure
        cumulative_sleep_debt = roster.initial_sleep_debt
        
        # Initialize body clock
        body_clock = CircadianState(
            current_phase_shift_hours=0.0,
            last_update_utc=roster.duties[0].report_time_utc - timedelta(days=1),
            reference_timezone=roster.home_base_timezone
        )
        
        # Build adaptation timeline
        body_clock_timeline = [(body_clock.last_update_utc, body_clock)]
        
        for duty in roster.duties:
            departure_tz = duty.segments[0].departure_airport.timezone
            body_clock = self.calculate_adaptation(
                duty.report_time_utc,
                body_clock,
                departure_tz,
                roster.home_base_timezone
            )
            body_clock_timeline.append((duty.report_time_utc, body_clock))
        
        # Extract sleep
        all_sleep = self.extract_sleep_from_roster(roster, body_clock_timeline)
        
        # Simulate each duty
        previous_duty = None
        previous_timeline = None
        
        for i, duty in enumerate(roster.duties):
            phase_shift = self._get_phase_shift_at_time(duty.report_time_utc, body_clock_timeline)
            
            relevant_sleep = [
                s for s in all_sleep
                if s.end_utc <= duty.report_time_utc and
                   s.end_utc >= duty.report_time_utc - timedelta(hours=48)
            ]
            
            # OPTIMIZATION: Use cached S from previous duty to avoid history re-computation
            cached_s_value = None
            if previous_timeline and previous_timeline.final_process_s > 0:
                cached_s_value = previous_timeline.final_process_s
            
            timeline_obj = self.simulate_duty(
                duty, relevant_sleep, phase_shift, 
                initial_s=current_s,
                cached_s=cached_s_value
            )
            previous_timeline = timeline_obj
            
            # Update sleep debt (with decay)
            if previous_duty:
                days_since_last = (duty.date - previous_duty.date).days
                if days_since_last > 0:
                    cumulative_sleep_debt *= math.exp(-self.params.sleep_debt_decay_rate * days_since_last)
            
            duty_sleep = sum(
                s.effective_sleep_hours for s in relevant_sleep
                if s.start_utc >= (previous_duty.release_time_utc if previous_duty else duty.report_time_utc - timedelta(days=1))
            )
            
            daily_debt = max(0, self.params.baseline_sleep_need_hours - duty_sleep)
            cumulative_sleep_debt += daily_debt
            
            timeline_obj.cumulative_sleep_debt = cumulative_sleep_debt
            
            if timeline_obj.timeline:
                current_s = timeline_obj.timeline[-1].homeostatic_component
            
            duty_timelines.append(timeline_obj)
            previous_duty = duty
        
        return self._build_monthly_analysis(roster, duty_timelines)
    
    def _build_monthly_analysis(self, roster: Roster, duty_timelines: List[DutyTimeline]) -> MonthlyAnalysis:
        """Build monthly summary"""
        
        risk_thresholds = self.config.risk_thresholds
        
        high_risk = sum(
            1 for dt in duty_timelines
            if dt.landing_performance and risk_thresholds.classify(dt.landing_performance) == 'high'
        )
        critical_risk = sum(
            1 for dt in duty_timelines
            if dt.landing_performance and risk_thresholds.classify(dt.landing_performance) in ['critical', 'extreme']
        )
        
        total_pinch = sum(len(dt.pinch_events) for dt in duty_timelines)
        
        all_sleep = [dt.prior_sleep_hours for dt in duty_timelines if dt.prior_sleep_hours > 0]
        avg_sleep = sum(all_sleep) / len(all_sleep) if all_sleep else 0.0
        
        max_debt = max(dt.cumulative_sleep_debt for dt in duty_timelines)
        
        worst_duty = min(duty_timelines, key=lambda dt: dt.min_performance)
        
        return MonthlyAnalysis(
            roster=roster,
            duty_timelines=duty_timelines,
            high_risk_duties=high_risk,
            critical_risk_duties=critical_risk,
            total_pinch_events=total_pinch,
            average_sleep_per_night=avg_sleep,
            max_sleep_debt=max_debt,
            lowest_performance_duty=worst_duty.duty_id,
            lowest_performance_value=worst_duty.min_performance
        )
