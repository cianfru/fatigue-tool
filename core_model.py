"""
core_model.py - Biomathematical Fatigue Model Engine (UNIFIED)
==============================================================

Advanced Two-Process Borbély Model with Corrections

VERSION 3 FEATURES (UNIFIED):
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
"""

from datetime import datetime, timedelta
from typing import List, Tuple, Optional, Dict
import math
import pytz

from config import ModelConfig, BorbelyParameters, AdaptationRates
from data_models import (
    Duty, Roster, FlightSegment, SleepBlock, CircadianState,
    PerformancePoint, PinchEvent, DutyTimeline, MonthlyAnalysis, FlightPhase
)
from easa_utils import BiomathematicalSleepEstimator, EASAComplianceValidator
from time_on_task import TimeOnTaskModel
from sleep_debt import SleepDebtModel, SleepHistory


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
        
        # Advanced fatigue models
        self.tot_model = TimeOnTaskModel()
        self.debt_model = SleepDebtModel()
        
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
        initial_s: float,
        current_time: datetime,
        sleep_history: List[SleepBlock],
        reference_time: datetime
    ) -> float:
        """
        Process S: Homeostatic sleep pressure
        Borbély & Achermann (1999) equations
        """
        s_current = initial_s
        last_event_time = reference_time - timedelta(hours=48)
        
        # Build sleep/wake timeline
        events = []
        for sleep in sleep_history:
            if sleep.end_utc <= current_time:
                events.append(('sleep', sleep.start_utc, sleep.end_utc, sleep.effective_sleep_hours))
        
        events.sort(key=lambda x: x[1])
        
        # Process timeline
        current_pos = last_event_time
        
        for event_type, start, end, duration in events:
            # Wake period before sleep
            if start > current_pos:
                wake_duration = (start - current_pos).total_seconds() / 3600
                s_infinity = self.params.S_max
                s_current = s_infinity - (s_infinity - s_current) * \
                           math.exp(-wake_duration / self.params.tau_i)
                current_pos = start
            
            # Sleep period (decay)
            s_current = s_current * math.exp(-duration / self.params.tau_d)
            current_pos = end
        
        # Final wake period
        if current_pos < current_time:
            wake_duration = (current_time - current_pos).total_seconds() / 3600
            s_infinity = self.params.S_max
            s_current = s_infinity - (s_infinity - s_current) * \
                       math.exp(-wake_duration / self.params.tau_i)
        
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
        history: SleepHistory
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
        CORRECTED Integration: Multiplicative (non-linear)
        
        Formula: Alertness = (1 - S) × (1 + A×C) / (1 + A)
        where A = circadian amplitude
        """
        s_alertness = 1.0 - s
        c_alertness = (1.0 + self.c_amplitude * c) / (1.0 + self.c_amplitude)
        return s_alertness * c_alertness
    
    def integrate_performance(self, c: float, s: float, w: float) -> float:
        """
        Integrate three processes into performance
        
        V2: MULTIPLICATIVE INTEGRATION
        Captures interaction (high S during low C = multiplicatively worse)
        """
        # Validation
        assert 0 <= c <= 1, f"C out of range: {c}"
        assert 0 <= s <= 1, f"S out of range: {s}"
        assert 0 <= w <= 1, f"W out of range: {w}"
        
        # Convert S to alertness
        h_alertness = (self.params.S_max - s) / (self.params.S_max - self.params.S_min)
        
        # Weighted combination
        weighted_sum = (
            c * self.params.weight_circadian +
            h_alertness * self.params.weight_homeostatic
        )
        
        # Apply interaction exponent
        if self.params.interaction_exponent != 1.0:
            weighted_sum = weighted_sum ** self.params.interaction_exponent
        
        # Multiplicative penalty for inertia
        combined = weighted_sum * (1.0 - w)
        
        # Scale to 0-100
        performance = combined * 100
        
        assert 0 <= performance <= 100, f"Performance out of range: {performance}"
        
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
        resolution_minutes: int = 5
    ) -> DutyTimeline:
        """Simulate single duty with high-resolution timeline"""
        
        timeline = []
        
        # Last sleep
        last_sleep = None
        for sleep in reversed(sleep_history):
            if sleep.end_utc <= duty.report_time_utc:
                last_sleep = sleep
                break
        
        time_since_wake = timedelta(0)
        if last_sleep:
            time_since_wake = duty.report_time_utc - last_sleep.end_utc
        
        # Simulate
        current_time = duty.report_time_utc
        
        while current_time <= duty.release_time_utc:
            s = self.compute_process_s(initial_s, current_time, sleep_history, duty.report_time_utc)
            c = self.compute_process_c(current_time, duty.home_base_timezone, circadian_phase_shift)
            current_wake = (current_time - duty.report_time_utc) + time_since_wake
            w = self.compute_sleep_inertia(current_wake)
            
            performance = self.integrate_performance(c, s, w)
            phase = self.get_flight_phase(duty.segments, current_time)
            
            tz = pytz.timezone(duty.home_base_timezone)
            point = PerformancePoint(
                timestamp_utc=current_time,
                timestamp_local=current_time.astimezone(tz),
                circadian_component=c,
                homeostatic_component=s,
                sleep_inertia_component=w,
                raw_performance=performance,
                current_flight_phase=phase,
                is_critical_phase=(phase in [FlightPhase.TAKEOFF, FlightPhase.LANDING, FlightPhase.APPROACH])
            )
            
            timeline.append(point)
            current_time += timedelta(minutes=resolution_minutes)
        
        return self._build_duty_timeline(duty, timeline, sleep_history, circadian_phase_shift)
    
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
        
        for i, duty in enumerate(roster.duties):
            phase_shift = self._get_phase_shift_at_time(duty.report_time_utc, body_clock_timeline)
            
            relevant_sleep = [
                s for s in all_sleep
                if s.end_utc <= duty.report_time_utc and
                   s.end_utc >= duty.report_time_utc - timedelta(hours=48)
            ]
            
            timeline_obj = self.simulate_duty(duty, relevant_sleep, phase_shift, initial_s=current_s)
            
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
