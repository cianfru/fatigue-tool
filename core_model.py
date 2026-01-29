"""
core_model.py - UNIFIED Biomathematical Fatigue Model Engine
============================================================

Consolidated aviation fatigue prediction system with all components unified.

VERSION 5.0 - UNIFIED ARCHITECTURE

This file consolidates all fatigue and sleep logic into 8 organized sections:

SECTION 1: Configuration & Parameters
SECTION 2: Data Models (imported from data_models.py)
SECTION 3: Sleep Calculation Engine (UnifiedSleepCalculator - NEW)
SECTION 4: Borbély Model Implementation
SECTION 5: EASA Compliance Validation
SECTION 6: Workload Integration
SECTION 7: Timeline Simulation
SECTION 8: Roster Analysis Engine

BUGS FIXED:
- Bug #1 (WOCL Timezone): Converts to local timezone before extracting hours
- Bug #2 (Night Threshold): Changed from 22 to 20 for Qatar night departures
- Bug #3 (Missing Variables): duty_duration and crosses_wocl calculated before use

Scientific Foundation:
- Borbély & Achermann (1999) - Two-process model
- Signal et al. (2009) - Night flight napping strategies
- Gander et al. (2013) - Early morning sleep patterns
- Roach et al. (2012) - Split sleep effectiveness
- Åkerstedt (1995) - Sleep environment quality
- Van Dongen et al. (2003) - Sleep debt dynamics
- Bourgeois-Bougrine et al. (2003) - Workload integration
"""

from datetime import datetime, timedelta, time
from typing import List, Tuple, Optional, Dict, Any
from dataclasses import dataclass, field
import math
import pytz
import logging

# Module-level logger
logger = logging.getLogger(__name__)

# Import data models (Section 2 uses external file to avoid duplication)
from data_models import (
    Duty, Roster, FlightSegment, SleepBlock, CircadianState,
    PerformancePoint, PinchEvent, DutyTimeline, MonthlyAnalysis, FlightPhase
)


# ============================================================================
# SECTION 1: CONFIGURATION & PARAMETERS
# ============================================================================

@dataclass
class EASAFatigueFramework:
    """
    EASA FTL regulatory definitions and thresholds
    Source: EU Regulation 965/2012 ORO.FTL + AMC/GM
    """
    
    # Window of Circadian Low (WOCL) - AMC1 ORO.FTL.105(10)
    wocl_start_hour: int = 2      # 02:00 local (reference time)
    wocl_end_hour: int = 5         # 05:59 local
    wocl_end_minute: int = 59
    
    # Acclimatization - AMC1 ORO.FTL.105(1)
    acclimatization_timezone_band_hours: float = 2.0
    acclimatization_required_local_nights: int = 3
    acclimatization_unknown_threshold_hours: float = 60.0
    acclimatization_partial_threshold_hours: float = 12.0
    acclimatization_full_threshold_hours: float = 36.0
    
    # Circadian reference strategy
    circadian_reference_strategy: str = 'adaptive'
    circadian_reference_switch_threshold: float = 0.5
    
    # Local night definition (22:00-08:00)
    local_night_start_hour: int = 22
    local_night_end_hour: int = 8
    
    # Disruptive duties - GM1 ORO.FTL.235
    early_start_threshold_hour: int = 6
    late_finish_threshold_hour: int = 2
    
    # Rest requirements - ORO.FTL.235
    minimum_rest_hours: float = 12.0
    minimum_sleep_opportunity_hours: float = 8.0
    recurrent_rest_hours: float = 36.0
    recurrent_rest_local_nights: int = 2
    recurrent_rest_frequency_days: int = 7
    
    # FDP limits - ORO.FTL.205
    max_fdp_basic_hours: float = 13.0
    max_duty_hours: float = 14.0


@dataclass
class BorbelyParameters:
    """
    Two-process sleep regulation model parameters
    
    SCIENTIFIC REFERENCES:
    - Borbély AA (1982). A two process model of sleep regulation.
      Human Neurobiology, 1(3), 195-204.
    - Borbély AA, Achermann P (1999). Sleep homeostasis and models of sleep regulation.
      Journal of Biological Rhythms, 14(6), 557-568.
    - Jewett ME, Kronauer RE (1999). Interactive mathematical models of subjective
      alertness and cognitive throughput in humans. Journal of Biological Rhythms, 14(6), 588-597.
    - Van Dongen HPA, Maislin G, Mullington JM, Dinges DF (2003). The cumulative cost
      of additional wakefulness. Sleep, 26(2), 117-126.
    - Åkerstedt T, Folkard S (1997). The three-process model of alertness.
      Ergonomics, 40(3), 313-334.
    - Tassi P, Muzet A (2000). Sleep inertia. Sleep Medicine Reviews, 4(4), 341-353.
    """
    
    # Process S (Homeostatic Sleep Pressure)
    # Borbély (1982): S oscillates between asymptotic bounds during wake/sleep
    S_max: float = 1.0  # Upper asymptote (normalized)
    S_min: float = 0.0  # Lower asymptote (normalized)
    
    # Time constants from Jewett & Kronauer (1999), Table 1
    # tau_i: Time constant for sleep pressure buildup during wakefulness
    # tau_d: Time constant for sleep pressure decay during sleep
    tau_i: float = 18.2  # Hours - Jewett & Kronauer (1999): 18.18h
    tau_d: float = 4.2   # Hours - Jewett & Kronauer (1999): 4.2h
    
    # Process C (Circadian) - Jewett & Kronauer (1999)
    # Circadian amplitude relative to mesor
    circadian_amplitude: float = 0.25  # Jewett & Kronauer (1999): ~0.97 raw, normalized here
    circadian_mesor: float = 0.5       # Midline estimating statistic of rhythm
    circadian_period_hours: float = 24.0  # Czeisler et al. (1999): 24.18h, rounded
    
    # Acrophase: Peak alertness time - Monk et al. (1997)
    # Core body temperature minimum at ~04:00-05:00, alertness peak ~12h later
    circadian_acrophase_hours: float = 17.0  # Peak alertness ~17:00 local
    
    # Performance integration weights
    # Åkerstedt & Folkard (1997): Relative contribution of processes
    weight_circadian: float = 0.4   # C-process contribution
    weight_homeostatic: float = 0.6 # S-process contribution
    interaction_exponent: float = 1.5  # Non-linear fatigue accumulation
    
    # Sleep inertia (Process W) - Tassi & Muzet (2000)
    # Duration: 15-30 minutes for most effects to dissipate
    # Magnitude: Can reduce performance by 10-40%
    inertia_duration_minutes: float = 30.0  # Tassi & Muzet (2000)
    inertia_max_magnitude: float = 0.30     # 30% performance decrement
    
    # Sleep debt - Van Dongen et al. (2003)
    # Chronic sleep restriction effects accumulate across days
    baseline_sleep_need_hours: float = 8.0  # Van Dongen et al. (2003): 7.91h rounded
    sleep_debt_decay_rate: float = 0.25     # Recovery rate per day off


@dataclass
class SleepQualityParameters:
    """
    Sleep quality multipliers by environment
    
    SCIENTIFIC REFERENCES:
    - Åkerstedt T, Nilsson PM (2003). Sleep as restitution: an introduction.
      Journal of Internal Medicine, 254(1), 6-12.
    - Signal TL, Gander PH, van den Berg MJ, Graeber RC (2013). In-flight sleep of
      flight crew during a 7-hour rest break. Aviation, Space, and Environmental Medicine, 84(10), 1041-1049.
    - Roach GD, et al. (2012). The relative importance of day-time sleep vs night-time
      sleep for recovery. Chronobiology International, 29(5), 594-604.
    - Pilcher JJ, Huffcutt AI (1996). Effects of sleep deprivation on performance.
      Sleep, 19(4), 318-326.
    """
    
    # Environment quality factors - Åkerstedt & Nilsson (2003)
    # Home environment as reference (1.0)
    quality_home: float = 1.0             # Reference baseline
    quality_hotel_quiet: float = 0.85     # Signal et al. (2013): ~15% reduction layover
    quality_hotel_typical: float = 0.80   # Typical hotel with some disturbance
    quality_hotel_airport: float = 0.75   # Airport noise impact
    quality_layover_unfamiliar: float = 0.78  # First night effect ~20% reduction
    quality_crew_rest_facility: float = 0.65  # Signal et al. (2013): Bunk rest ~65% efficiency
    
    # Circadian timing penalties - Roach et al. (2012)
    max_circadian_quality_penalty: float = 0.25  # Sleep during biological day
    early_wake_penalty_per_hour: float = 0.05    # Per hour before optimal wake
    late_sleep_start_penalty_per_hour: float = 0.03  # Per hour after optimal bedtime
    
    # Duration-based efficiency - Pilcher & Huffcutt (1996)
    short_sleep_penalty_threshold_hours: float = 4.0  # Below this, severe impairment
    short_sleep_efficiency_factor: float = 0.75       # Reduced efficiency for short sleep
    long_sleep_penalty_threshold_hours: float = 9.0   # Diminishing returns above this
    long_sleep_efficiency_decay_rate: float = 0.03    # Per hour above threshold


@dataclass
class AdaptationRates:
    """
    Circadian adaptation rates for timezone shifts
    
    SCIENTIFIC REFERENCES:
    - Waterhouse J, Reilly T, Atkinson G, Edwards B (2007). Jet lag: trends and
      coping strategies. The Lancet, 369(9567), 1117-1129.
    - Sack RL, et al. (2007). Circadian rhythm sleep disorders: Part II, advanced
      sleep phase disorder. Sleep, 30(11), 1484-1501.
    - Burgess HJ, Crowley SJ, Gazda CJ, Fogg LF, Eastman CI (2003). Preflight
      adjustment to eastward travel. Journal of Biological Rhythms, 18(4), 339-350.
    
    Asymmetric adaptation rates reflect that phase delays (westward) are easier
    than phase advances (eastward) for most individuals.
    """
    
    # Waterhouse et al. (2007): ~1.5h/day westward, ~1.0h/day eastward
    westward_hours_per_day: float = 1.5  # Phase delay - easier direction
    eastward_hours_per_day: float = 1.0  # Phase advance - harder direction
    
    def get_rate(self, timezone_shift_hours: float) -> float:
        """Return adaptation rate based on direction of shift"""
        return self.westward_hours_per_day if timezone_shift_hours < 0 else self.eastward_hours_per_day


@dataclass
class RiskThresholds:
    """Performance score thresholds with EASA regulatory references"""
    
    thresholds: Dict[str, Tuple[float, float]] = field(default_factory=lambda: {
        'low': (75, 100),
        'moderate': (65, 75),
        'high': (55, 65),
        'critical': (45, 55),
        'extreme': (0, 45)
    })
    
    actions: Dict[str, Dict[str, str]] = field(default_factory=lambda: {
        'low': {'action': 'None required', 'easa_reference': None, 'description': 'Well-rested state'},
        'moderate': {'action': 'Enhanced monitoring recommended', 'easa_reference': 'AMC1 ORO.FTL.120', 'description': 'Equivalent to ~6h sleep'},
        'high': {'action': 'Mitigation required', 'easa_reference': 'GM1 ORO.FTL.235', 'description': 'Equivalent to ~5h sleep'},
        'critical': {'action': 'MANDATORY roster modification', 'easa_reference': 'ORO.FTL.120(a)', 'description': 'Equivalent to ~4h sleep'},
        'extreme': {'action': 'UNSAFE - Do not fly', 'easa_reference': 'ORO.FTL.120(b)', 'description': 'Severe impairment'}
    })
    
    def classify(self, performance: float) -> str:
        if performance is None:
            return 'unknown'
        for level, (low, high) in self.thresholds.items():
            if low <= performance < high:
                return level
        return 'extreme'
    
    def get_action(self, risk_level: str) -> Dict[str, str]:
        return self.actions.get(risk_level, self.actions['extreme'])


@dataclass
class ModelConfig:
    """Master configuration - allows switching between model variants"""
    easa_framework: EASAFatigueFramework
    borbely_params: BorbelyParameters
    risk_thresholds: RiskThresholds
    adaptation_rates: AdaptationRates
    sleep_quality_params: SleepQualityParameters
    
    @classmethod
    def default_easa_config(cls):
        return cls(
            easa_framework=EASAFatigueFramework(),
            borbely_params=BorbelyParameters(),
            risk_thresholds=RiskThresholds(),
            adaptation_rates=AdaptationRates(),
            sleep_quality_params=SleepQualityParameters()
        )
    
    @classmethod
    def conservative_config(cls):
        config = cls.default_easa_config()
        config.risk_thresholds.thresholds = {
            'low': (80, 100), 'moderate': (70, 80), 'high': (60, 70),
            'critical': (50, 60), 'extreme': (0, 50)
        }
        config.borbely_params.interaction_exponent = 2.0
        return config
    
    @classmethod
    def liberal_config(cls):
        config = cls.default_easa_config()
        config.risk_thresholds.thresholds = {
            'low': (70, 100), 'moderate': (60, 70), 'high': (50, 60),
            'critical': (40, 50), 'extreme': (0, 40)
        }
        config.borbely_params.interaction_exponent = 1.2
        return config
    
    @classmethod
    def research_config(cls):
        config = cls.default_easa_config()
        config.borbely_params.interaction_exponent = 1.0
        return config


# ============================================================================
# SECTION 2: DATA MODELS
# ============================================================================
# Note: Data models are imported from data_models.py to avoid duplication
# See imports at top of file


# ============================================================================
# SECTION 3: UNIFIED SLEEP CALCULATION ENGINE
# ============================================================================

@dataclass
class SleepQualityAnalysis:
    """Detailed breakdown of sleep quality factors"""
    total_sleep_hours: float
    actual_sleep_hours: float
    effective_sleep_hours: float
    sleep_efficiency: float
    
    # Factor breakdown
    base_efficiency: float
    wocl_penalty: float
    late_onset_penalty: float
    recovery_boost: float
    time_pressure_factor: float
    insufficient_penalty: float
    
    # Context
    wocl_overlap_hours: float
    sleep_start_hour: float
    hours_since_duty: Optional[float]
    hours_until_duty: Optional[float]
    
    # Warnings
    warnings: List[Dict[str, str]]


@dataclass
class SleepStrategy:
    """Represents a pilot's strategic sleep approach"""
    strategy_type: str  # 'normal', 'afternoon_nap', 'early_bedtime', 'split_sleep'
    sleep_blocks: List[SleepBlock]
    confidence: float
    explanation: str
    quality_analysis: List[SleepQualityAnalysis]


class UnifiedSleepCalculator:
    """
    UNIFIED Sleep Calculation Engine
    
    Consolidates all sleep estimation and quality calculation logic.
    
    SCIENTIFIC REFERENCES:
    - Åkerstedt T, Folkard S (1995). Validation of the S and C components of the
      three-process model of alertness regulation. Sleep, 18(1), 1-6.
    - Gander PH, Signal TL, van den Berg MJ, et al. (2013). In-flight sleep,
      pilot fatigue and Psychomotor Vigilance Task performance on ultra-long
      range versus long range flights. J Sleep Res, 22(6), 697-706.
    - Signal TL, et al. (2009). Scheduled napping as a countermeasure to
      sleepiness in air traffic controllers. J Sleep Res, 18(1), 11-19.
    - Roach GD, et al. (2012). The relative importance of day-time sleep.
      Chronobiology International, 29(5), 594-604.
    - Roenneberg T, et al. (2007). Epidemiology of the human circadian clock.
      Sleep Medicine Reviews, 11(6), 429-438.
    
    BUGS FIXED:
    - Bug #1: WOCL calculation now converts to local timezone before extracting hours
    - Bug #2: NIGHT_FLIGHT_THRESHOLD changed from 22 to 20 for Qatar departures
    - Bug #3: duty_duration and crosses_wocl calculated before decision tree
    """
    
    def __init__(self, config: ModelConfig = None):
        self.config = config or ModelConfig.default_easa_config()
        
        # Sleep timing parameters - Roenneberg et al. (2007) chronotype data
        # Average adult bedtime ~23:00, wake ~07:00
        self.NORMAL_BEDTIME_HOUR = 23   # Roenneberg et al. (2007): median ~23:30
        self.NORMAL_WAKE_HOUR = 7       # Roenneberg et al. (2007): median ~07:30
        self.NORMAL_SLEEP_DURATION = 8.0  # Van Dongen et al. (2003): 7.91h rounded
        
        # Night flight threshold - EASA CS-FTL.1.235 "early type" starts at 05:00,
        # "late type" encompasses duties starting 20:00+
        # BUG FIX #2: Changed from 22 to 20 to capture evening departures
        self.NIGHT_FLIGHT_THRESHOLD = 20  # EASA late-type duty threshold
        
        # Early morning threshold - EASA GM1 ORO.FTL.235: early start <07:00
        self.EARLY_REPORT_THRESHOLD = 7
        
        # WOCL definition - EASA AMC1 ORO.FTL.105(10): 02:00-05:59
        self.WOCL_START = 2
        self.WOCL_END = 6
        
        # Base sleep efficiency by location
        # Åkerstedt et al. (1995), Signal et al. (2009), Gander et al. (2013)
        self.LOCATION_EFFICIENCY = {
            'home': 0.90,          # Reference baseline - Åkerstedt (1995)
            'hotel': 0.85,         # Gander et al. (2013): ~15% layover reduction
            'crew_rest': 0.88,     # Signal et al. (2009): bunk rest efficiency
            'airport_hotel': 0.82, # Added noise factor
            'crew_house': 0.87     # Similar to hotel but more familiar
        }
        
        # Biological limits - Roach et al. (2012)
        self.MAX_REALISTIC_SLEEP = 10.0   # Max single sleep episode
        self.MIN_SLEEP_FOR_QUALITY = 6.0  # Minimum for restorative sleep
        
        # Timezone for current calculation (set per-call)
        self.home_tz = None
    
    def estimate_sleep_for_duty(
        self,
        duty: Duty,
        previous_duty: Optional[Duty] = None,
        home_timezone: str = 'UTC'
    ) -> SleepStrategy:
        """
        Main entry point: Estimate how pilot actually slept before duty
        
        BUG FIX #3: Now calculates duty_duration and crosses_wocl BEFORE
        the decision tree to ensure variables are defined.
        """
        # Set home timezone for this calculation
        self.home_tz = pytz.timezone(home_timezone)
        
        report_local = duty.report_time_utc.astimezone(self.home_tz)
        report_hour = report_local.hour
        
        # BUG FIX #3: Calculate these BEFORE the if/elif decision tree
        duty_duration = (duty.release_time_utc - duty.report_time_utc).total_seconds() / 3600
        crosses_wocl = self._duty_crosses_wocl(duty)
        
        # Decision tree based on research
        # BUG FIX #2: NIGHT_FLIGHT_THRESHOLD is now 20 (not 22)
        if report_hour >= self.NIGHT_FLIGHT_THRESHOLD or report_hour < 4:
            return self._night_departure_strategy(duty, previous_duty)
        
        elif report_hour < self.EARLY_REPORT_THRESHOLD:
            return self._early_morning_strategy(duty, previous_duty)
        
        elif crosses_wocl and duty_duration > 6:
            return self._wocl_duty_strategy(duty, previous_duty)
        
        else:
            return self._normal_sleep_strategy(duty, previous_duty)
    
    # ========================================================================
    # CORE SLEEP QUALITY CALCULATION
    # ========================================================================
    
    def calculate_sleep_quality(
        self,
        sleep_start: datetime,
        sleep_end: datetime,
        location: str,
        previous_duty_end: Optional[datetime],
        next_event: datetime,
        is_nap: bool = False,
        location_timezone: str = 'UTC'
    ) -> SleepQualityAnalysis:
        """
        Calculate realistic sleep quality with ALL factors
        
        BUG FIX #1: Now passes location_timezone to _calculate_wocl_overlap()
        """
        
        # 1. Calculate raw duration
        total_hours = (sleep_end - sleep_start).total_seconds() / 3600
        
        # 2. Apply biological sleep limit
        if total_hours > self.MAX_REALISTIC_SLEEP and not is_nap:
            actual_duration = self.MAX_REALISTIC_SLEEP
        else:
            actual_duration = total_hours
        
        # 3. Base efficiency by location
        base_efficiency = self.LOCATION_EFFICIENCY.get(location, 0.85)
        if is_nap:
            base_efficiency *= 0.88
        
        # 4. WOCL overlap penalty - BUG FIX #1: Pass timezone
        wocl_overlap = self._calculate_wocl_overlap(sleep_start, sleep_end, location_timezone)
        
        if wocl_overlap > 0:
            wocl_penalty = 1.0 - (wocl_overlap * 0.05)
            wocl_penalty = max(0.75, wocl_penalty)
        else:
            wocl_penalty = 1.0
        
        # 5. Late sleep onset penalty - use local time
        tz = pytz.timezone(location_timezone)
        sleep_start_local = sleep_start.astimezone(tz)
        sleep_start_hour = sleep_start_local.hour + sleep_start_local.minute / 60.0
        
        if sleep_start_hour >= 1 and sleep_start_hour < 4:
            late_onset_penalty = 0.93
        elif sleep_start_hour >= 0 and sleep_start_hour < 1:
            late_onset_penalty = 0.97
        else:
            late_onset_penalty = 1.0
        
        # 6. Recovery sleep boost
        if previous_duty_end:
            hours_since_duty = (sleep_start - previous_duty_end).total_seconds() / 3600
            if hours_since_duty < 3:
                recovery_boost = 1.10 if not is_nap else 1.05
            else:
                recovery_boost = 1.0
        else:
            recovery_boost = 1.0
            hours_since_duty = None
        
        # 7. Time pressure factor
        hours_until_duty = (next_event - sleep_end).total_seconds() / 3600
        
        if hours_until_duty < 1.5:
            time_pressure_factor = 0.88
        elif hours_until_duty < 3:
            time_pressure_factor = 0.93
        elif hours_until_duty < 6:
            time_pressure_factor = 0.97
        else:
            time_pressure_factor = 1.03
        
        # 8. Insufficient sleep penalty
        if actual_duration < 4 and not is_nap:
            insufficient_penalty = 0.75
        elif actual_duration < 6 and not is_nap:
            insufficient_penalty = 0.88
        else:
            insufficient_penalty = 1.0
        
        # 9. Combine all factors
        combined_efficiency = (
            base_efficiency
            * wocl_penalty
            * late_onset_penalty
            * recovery_boost
            * time_pressure_factor
            * insufficient_penalty
        )
        combined_efficiency = max(0.50, min(1.0, combined_efficiency))
        
        # 10. Calculate effective sleep
        effective_sleep_hours = actual_duration * combined_efficiency
        
        # 11. Generate warnings
        warnings = self._generate_sleep_warnings(
            effective_sleep_hours, actual_duration, wocl_overlap, hours_until_duty, is_nap
        )
        
        return SleepQualityAnalysis(
            total_sleep_hours=total_hours,
            actual_sleep_hours=actual_duration,
            effective_sleep_hours=effective_sleep_hours,
            sleep_efficiency=combined_efficiency,
            base_efficiency=base_efficiency,
            wocl_penalty=wocl_penalty,
            late_onset_penalty=late_onset_penalty,
            recovery_boost=recovery_boost,
            time_pressure_factor=time_pressure_factor,
            insufficient_penalty=insufficient_penalty,
            wocl_overlap_hours=wocl_overlap,
            sleep_start_hour=sleep_start_hour,
            hours_since_duty=hours_since_duty,
            hours_until_duty=hours_until_duty,
            warnings=warnings
        )
    
    def _calculate_wocl_overlap(
        self,
        sleep_start: datetime,
        sleep_end: datetime,
        location_timezone: str = 'UTC'
    ) -> float:
        """
        Calculate hours of sleep overlapping WOCL (02:00-06:00)
        
        BUG FIX #1: Now converts to local timezone FIRST before extracting hours.
        This fixes the Feb 23rd bug where UTC hours were incorrectly used as local.
        
        Example:
        - Sleep 20:00-05:00 UTC = 23:00-08:00 DOH (Asia/Qatar +3)
        - OLD (broken): Used 20:00-05:00 hours → incorrect WOCL overlap
        - NEW (fixed): Convert to 23:00-08:00 local → correct WOCL calculation
        """
        
        # BUG FIX #1: Convert to local time FIRST before extracting hours
        tz = pytz.timezone(location_timezone)
        sleep_start_local = sleep_start.astimezone(tz)
        sleep_end_local = sleep_end.astimezone(tz)
        
        # NOW extract local hour (not UTC hour)
        sleep_start_hour = sleep_start_local.hour + sleep_start_local.minute / 60.0
        sleep_end_hour = sleep_end_local.hour + sleep_end_local.minute / 60.0
        
        overlap_hours = 0.0
        
        # Handle overnight sleep (crosses midnight)
        if sleep_end_hour < sleep_start_hour or sleep_end_local.date() > sleep_start_local.date():
            # Sleep crosses midnight - check both days
            
            # Day 1: From sleep_start to end of day (24:00)
            if sleep_start_hour < self.WOCL_END:
                day1_overlap_start = max(sleep_start_hour, self.WOCL_START)
                day1_overlap_end = min(24.0, self.WOCL_END)
                if day1_overlap_start < day1_overlap_end:
                    overlap_hours += day1_overlap_end - day1_overlap_start
            
            # Day 2: From start of day (00:00) to sleep_end
            if sleep_end_hour > self.WOCL_START:
                day2_overlap_start = max(0.0, self.WOCL_START)
                day2_overlap_end = min(sleep_end_hour, self.WOCL_END)
                if day2_overlap_start < day2_overlap_end:
                    overlap_hours += day2_overlap_end - day2_overlap_start
        else:
            # Same-day sleep (no midnight crossing)
            if sleep_start_hour < self.WOCL_END and sleep_end_hour > self.WOCL_START:
                overlap_start = max(sleep_start_hour, self.WOCL_START)
                overlap_end = min(sleep_end_hour, self.WOCL_END)
                overlap_hours = max(0.0, overlap_end - overlap_start)
        
        return overlap_hours
    
    def _generate_sleep_warnings(
        self,
        effective_sleep: float,
        actual_duration: float,
        wocl_overlap: float,
        hours_until_duty: float,
        is_nap: bool
    ) -> List[Dict[str, str]]:
        """Generate user-facing warnings about sleep quality"""
        
        warnings = []
        
        if not is_nap:
            if effective_sleep < 5:
                warnings.append({
                    'severity': 'critical',
                    'message': f'Critically insufficient sleep: {effective_sleep:.1f}h effective',
                    'recommendation': 'Consider fatigue mitigation or duty adjustment'
                })
            elif effective_sleep < 6:
                warnings.append({
                    'severity': 'high',
                    'message': f'Insufficient sleep: {effective_sleep:.1f}h effective',
                    'recommendation': 'Extra vigilance required on next duty'
                })
            elif effective_sleep < 7:
                warnings.append({
                    'severity': 'moderate',
                    'message': f'Below optimal sleep: {effective_sleep:.1f}h effective',
                    'recommendation': 'Monitor fatigue levels during duty'
                })
        
        if wocl_overlap > 2.5:
            warnings.append({
                'severity': 'moderate',
                'message': f'{wocl_overlap:.1f}h sleep during WOCL (02:00-06:00)',
                'recommendation': 'Sleep quality may be reduced due to circadian low'
            })
        
        if hours_until_duty and hours_until_duty < 2 and actual_duration < 5:
            warnings.append({
                'severity': 'critical',
                'message': 'Very short turnaround with minimal sleep',
                'recommendation': 'Report fatigue concerns to operations'
            })
        
        return warnings
    
    # ========================================================================
    # STRATEGY 1: Night Departure (Afternoon Nap)
    # ========================================================================
    
    def _night_departure_strategy(
        self,
        duty: Duty,
        previous_duty: Optional[Duty]
    ) -> SleepStrategy:
        """
        Night flight strategy with afternoon nap
        
        For departures at 20:00+ (BUG FIX #2: threshold now 20, not 22)
        """
        
        report_local = duty.report_time_utc.astimezone(self.home_tz)
        
        # Morning sleep
        morning_sleep_start = report_local.replace(
            hour=self.NORMAL_BEDTIME_HOUR, minute=0
        ) - timedelta(days=1)
        morning_sleep_end = report_local.replace(hour=8, minute=0)
        
        if previous_duty:
            release_local = previous_duty.release_time_utc.astimezone(self.home_tz)
            earliest_sleep = release_local + timedelta(hours=1.5)
            if morning_sleep_start < earliest_sleep:
                morning_sleep_start = earliest_sleep
        
        morning_quality = self.calculate_sleep_quality(
            sleep_start=morning_sleep_start,
            sleep_end=morning_sleep_end,
            location='home',
            previous_duty_end=previous_duty.release_time_utc if previous_duty else None,
            next_event=report_local,
            location_timezone=self.home_tz.zone
        )
        
        morning_sleep = SleepBlock(
            start_utc=morning_sleep_start.astimezone(pytz.utc),
            end_utc=morning_sleep_end.astimezone(pytz.utc),
            location_timezone=self.home_tz.zone,
            duration_hours=morning_quality.actual_sleep_hours,
            quality_factor=morning_quality.sleep_efficiency,
            effective_sleep_hours=morning_quality.effective_sleep_hours,
            environment='home'
        )
        
        # Afternoon nap
        nap_end = report_local - timedelta(hours=1.5)
        nap_start = nap_end - timedelta(hours=3.5)
        
        nap_quality = self.calculate_sleep_quality(
            sleep_start=nap_start,
            sleep_end=nap_end,
            location='home',
            previous_duty_end=morning_sleep_end.astimezone(pytz.utc),
            next_event=report_local,
            is_nap=True,
            location_timezone=self.home_tz.zone
        )
        
        afternoon_nap = SleepBlock(
            start_utc=nap_start.astimezone(pytz.utc),
            end_utc=nap_end.astimezone(pytz.utc),
            location_timezone=self.home_tz.zone,
            duration_hours=nap_quality.actual_sleep_hours,
            quality_factor=nap_quality.sleep_efficiency,
            effective_sleep_hours=nap_quality.effective_sleep_hours,
            is_anchor_sleep=False,
            environment='home'
        )
        
        total_effective = morning_quality.effective_sleep_hours + nap_quality.effective_sleep_hours
        
        return SleepStrategy(
            strategy_type='afternoon_nap',
            sleep_blocks=[morning_sleep, afternoon_nap],
            confidence=0.70,
            explanation=f"Night departure: {morning_quality.actual_sleep_hours:.1f}h + "
                       f"{nap_quality.actual_sleep_hours:.1f}h nap = {total_effective:.1f}h effective",
            quality_analysis=[morning_quality, nap_quality]
        )
    
    # ========================================================================
    # STRATEGY 2: Early Morning Report
    # ========================================================================
    
    def _early_morning_strategy(
        self,
        duty: Duty,
        previous_duty: Optional[Duty]
    ) -> SleepStrategy:
        """Early report strategy (<07:00) - early bedtime"""
        
        report_local = duty.report_time_utc.astimezone(self.home_tz)
        
        wake_time = report_local - timedelta(hours=1)
        sleep_duration = 8.0
        sleep_end = wake_time
        sleep_start = sleep_end - timedelta(hours=sleep_duration)
        
        if previous_duty:
            release_local = previous_duty.release_time_utc.astimezone(self.home_tz)
            earliest_sleep = release_local + timedelta(hours=1.5)
            if sleep_start < earliest_sleep:
                sleep_start = earliest_sleep
                sleep_duration = (sleep_end - sleep_start).total_seconds() / 3600
        
        sleep_quality = self.calculate_sleep_quality(
            sleep_start=sleep_start,
            sleep_end=sleep_end,
            location='home',
            previous_duty_end=previous_duty.release_time_utc if previous_duty else None,
            next_event=report_local,
            location_timezone=self.home_tz.zone
        )
        
        early_sleep = SleepBlock(
            start_utc=sleep_start.astimezone(pytz.utc),
            end_utc=sleep_end.astimezone(pytz.utc),
            location_timezone=self.home_tz.zone,
            duration_hours=sleep_quality.actual_sleep_hours,
            quality_factor=sleep_quality.sleep_efficiency,
            effective_sleep_hours=sleep_quality.effective_sleep_hours,
            environment='home'
        )
        
        return SleepStrategy(
            strategy_type='early_bedtime',
            sleep_blocks=[early_sleep],
            confidence=0.60,
            explanation=f"Early report: Early bedtime = {sleep_quality.effective_sleep_hours:.1f}h effective",
            quality_analysis=[sleep_quality]
        )
    
    # ========================================================================
    # STRATEGY 3: WOCL Duty (Split Sleep)
    # ========================================================================
    
    def _wocl_duty_strategy(
        self,
        duty: Duty,
        previous_duty: Optional[Duty]
    ) -> SleepStrategy:
        """WOCL duty strategy - anchor sleep before duty"""
        
        report_local = duty.report_time_utc.astimezone(self.home_tz)
        
        anchor_end = report_local - timedelta(hours=1.5)
        anchor_start = anchor_end - timedelta(hours=4.5)
        
        anchor_quality = self.calculate_sleep_quality(
            sleep_start=anchor_start,
            sleep_end=anchor_end,
            location='home',
            previous_duty_end=previous_duty.release_time_utc if previous_duty else None,
            next_event=report_local,
            location_timezone=self.home_tz.zone
        )
        
        anchor_sleep = SleepBlock(
            start_utc=anchor_start.astimezone(pytz.utc),
            end_utc=anchor_end.astimezone(pytz.utc),
            location_timezone=self.home_tz.zone,
            duration_hours=anchor_quality.actual_sleep_hours,
            quality_factor=anchor_quality.sleep_efficiency,
            effective_sleep_hours=anchor_quality.effective_sleep_hours,
            environment='home'
        )
        
        return SleepStrategy(
            strategy_type='split_sleep',
            sleep_blocks=[anchor_sleep],
            confidence=0.50,
            explanation=f"WOCL duty: Split sleep = {anchor_quality.effective_sleep_hours:.1f}h effective",
            quality_analysis=[anchor_quality]
        )
    
    # ========================================================================
    # STRATEGY 4: Normal Daytime
    # ========================================================================
    
    def _normal_sleep_strategy(
        self,
        duty: Duty,
        previous_duty: Optional[Duty]
    ) -> SleepStrategy:
        """Normal daytime duty - standard sleep"""
        
        report_local = duty.report_time_utc.astimezone(self.home_tz)
        
        wake_time = report_local - timedelta(hours=2.5)
        sleep_duration = self.NORMAL_SLEEP_DURATION
        sleep_end = wake_time
        sleep_start = sleep_end - timedelta(hours=sleep_duration)
        
        if previous_duty:
            release_local = previous_duty.release_time_utc.astimezone(self.home_tz)
            earliest_sleep = release_local + timedelta(hours=1.5)
            if sleep_start < earliest_sleep:
                sleep_start = earliest_sleep
                sleep_duration = (sleep_end - sleep_start).total_seconds() / 3600
        
        sleep_quality = self.calculate_sleep_quality(
            sleep_start=sleep_start,
            sleep_end=sleep_end,
            location='home',
            previous_duty_end=previous_duty.release_time_utc if previous_duty else None,
            next_event=report_local,
            location_timezone=self.home_tz.zone
        )
        
        normal_sleep = SleepBlock(
            start_utc=sleep_start.astimezone(pytz.utc),
            end_utc=sleep_end.astimezone(pytz.utc),
            location_timezone=self.home_tz.zone,
            duration_hours=sleep_quality.actual_sleep_hours,
            quality_factor=sleep_quality.sleep_efficiency,
            effective_sleep_hours=sleep_quality.effective_sleep_hours,
            environment='home'
        )
        
        return SleepStrategy(
            strategy_type='normal',
            sleep_blocks=[normal_sleep],
            confidence=0.90,
            explanation=f"Daytime duty: Normal sleep = {sleep_quality.effective_sleep_hours:.1f}h effective",
            quality_analysis=[sleep_quality]
        )
    
    # ========================================================================
    # HELPER METHODS
    # ========================================================================
    
    def _duty_crosses_wocl(self, duty: Duty) -> bool:
        """Check if duty encroaches on WOCL (02:00-06:00)"""
        start_local = duty.report_time_utc.astimezone(self.home_tz)
        end_local = duty.release_time_utc.astimezone(self.home_tz)
        
        current = start_local
        while current <= end_local:
            if self.WOCL_START <= current.hour < self.WOCL_END:
                return True
            current += timedelta(hours=1)
        
        return False


# ============================================================================
# SECTION 4: BORBÉLY MODEL IMPLEMENTATION
# ============================================================================
# See class BorbelyFatigueModel below (at end of file for organization)


# ============================================================================
# SECTION 5: EASA COMPLIANCE VALIDATION
# ============================================================================

class EASAComplianceValidator:
    """
    Validate duties against EASA FTL regulations
    Legal compliance layer (separate from fatigue prediction)
    """
    
    def __init__(self, framework: EASAFatigueFramework = None):
        self.framework = framework or EASAFatigueFramework()
    
    def calculate_fdp_limits(self, duty: Duty) -> Dict[str, float]:
        """Calculate EASA FDP limits based on ORO.FTL.205"""
        tz = pytz.timezone(duty.home_base_timezone)
        report_local = duty.report_time_utc.astimezone(tz)
        report_hour = report_local.hour
        sectors = len(duty.segments)
        
        # EASA ORO.FTL.205 Table 1 - Basic FDP limits
        fdp_table = {
            6: {1: 13.0, 2: 12.5, 3: 12.0, 4: 11.5, 5: 11.0, 6: 10.5, 7: 10.0, 8: 10.0, 9: 9.5},
            7: {1: 13.0, 2: 12.5, 3: 12.0, 4: 11.5, 5: 11.0, 6: 10.5, 7: 10.0, 8: 10.0, 9: 9.5},
            8: {1: 13.0, 2: 12.5, 3: 12.0, 4: 11.5, 5: 11.0, 6: 10.5, 7: 10.0, 8: 10.0, 9: 9.5},
            9: {1: 13.0, 2: 13.0, 3: 12.5, 4: 12.0, 5: 11.5, 6: 11.0, 7: 10.5, 8: 10.0, 9: 10.0},
            10: {1: 13.0, 2: 13.0, 3: 13.0, 4: 12.5, 5: 12.0, 6: 11.5, 7: 11.0, 8: 10.5, 9: 10.0},
            11: {1: 13.0, 2: 13.0, 3: 13.0, 4: 13.0, 5: 12.5, 6: 12.0, 7: 11.5, 8: 11.0, 9: 10.5},
            12: {1: 13.0, 2: 13.0, 3: 13.0, 4: 13.0, 5: 12.5, 6: 12.0, 7: 11.5, 8: 11.0, 9: 10.5},
            13: {1: 12.5, 2: 12.5, 3: 13.0, 4: 13.0, 5: 12.5, 6: 12.0, 7: 11.5, 8: 11.0, 9: 10.5},
            14: {1: 12.0, 2: 12.0, 3: 12.5, 4: 12.5, 5: 12.5, 6: 12.0, 7: 11.5, 8: 11.0, 9: 10.5},
            15: {1: 11.5, 2: 11.5, 3: 12.0, 4: 12.0, 5: 12.0, 6: 11.5, 7: 11.0, 8: 10.5, 9: 10.0},
            16: {1: 11.0, 2: 11.0, 3: 11.5, 4: 11.5, 5: 11.5, 6: 11.0, 7: 10.5, 8: 10.0, 9: 10.0},
            17: {1: 10.5, 2: 10.5, 3: 11.0, 4: 11.0, 5: 11.0, 6: 10.5, 7: 10.0, 8: 10.0, 9: 9.5},
            0: {1: 10.0, 2: 10.0, 3: 10.5, 4: 10.5, 5: 10.5, 6: 10.0, 7: 10.0, 8: 9.5, 9: 9.5},
            1: {1: 10.0, 2: 10.0, 3: 10.0, 4: 10.0, 5: 10.0, 6: 10.0, 7: 9.5, 8: 9.5, 9: 9.5},
            2: {1: 10.0, 2: 10.0, 3: 10.0, 4: 10.0, 5: 10.0, 6: 10.0, 7: 9.5, 8: 9.5, 9: 9.5},
            3: {1: 10.0, 2: 10.0, 3: 10.0, 4: 10.0, 5: 10.0, 6: 10.0, 7: 9.5, 8: 9.5, 9: 9.5},
            4: {1: 11.0, 2: 11.0, 3: 10.5, 4: 10.0, 5: 10.0, 6: 10.0, 7: 9.5, 8: 9.5, 9: 9.5},
            5: {1: 12.0, 2: 12.0, 3: 11.5, 4: 11.0, 5: 10.5, 6: 10.0, 7: 10.0, 8: 9.5, 9: 9.5},
        }
        
        sectors_capped = min(sectors, 9)
        max_fdp = fdp_table.get(report_hour, {}).get(sectors_capped, 13.0)
        extended_fdp = max_fdp + 2.0
        actual_fdp = (duty.release_time_utc - duty.report_time_utc).total_seconds() / 3600
        used_discretion = actual_fdp > max_fdp
        
        return {
            'max_fdp': max_fdp,
            'extended_fdp': extended_fdp,
            'actual_fdp': actual_fdp,
            'used_discretion': used_discretion,
            'exceeds_discretion': actual_fdp > extended_fdp
        }
    
    def calculate_wocl_encroachment(
        self,
        duty_start: datetime,
        duty_end: datetime,
        reference_timezone: str
    ) -> timedelta:
        """Calculate overlap with WOCL (02:00-05:59 reference time)"""
        tz = pytz.timezone(reference_timezone)
        duty_start_local = duty_start.astimezone(tz)
        duty_end_local = duty_end.astimezone(tz)
        
        total_encroachment = timedelta()
        current_day = duty_start_local.date()
        end_day = duty_end_local.date()
        
        while current_day <= end_day:
            wocl_start = datetime.combine(
                current_day, time(self.framework.wocl_start_hour, 0, 0)
            ).replace(tzinfo=tz)
            
            wocl_end = datetime.combine(
                current_day, time(self.framework.wocl_end_hour, self.framework.wocl_end_minute, 59)
            ).replace(tzinfo=tz)
            
            overlap_start = max(duty_start_local, wocl_start)
            overlap_end = min(duty_end_local, wocl_end)
            
            if overlap_start < overlap_end:
                total_encroachment += (overlap_end - overlap_start)
            
            current_day += timedelta(days=1)
        
        return total_encroachment
    
    def is_early_start(self, report_time_local: datetime) -> bool:
        return report_time_local.hour < self.framework.early_start_threshold_hour
    
    def is_late_finish(self, release_time_local: datetime) -> bool:
        hour = release_time_local.hour
        return (self.framework.late_finish_threshold_hour <= hour < 
                self.framework.local_night_end_hour)
    
    def is_disruptive_duty(self, duty: Duty) -> Dict[str, any]:
        wocl_encroachment = self.calculate_wocl_encroachment(
            duty.report_time_utc, duty.release_time_utc, duty.home_base_timezone
        )
        wocl_hours = wocl_encroachment.total_seconds() / 3600
        
        return {
            'wocl_encroachment': wocl_hours > 0,
            'wocl_hours': wocl_hours,
            'early_start': self.is_early_start(duty.report_time_local),
            'late_finish': self.is_late_finish(duty.release_time_local),
            'is_disruptive': (
                wocl_hours > 0 or
                self.is_early_start(duty.report_time_local) or
                self.is_late_finish(duty.release_time_local)
            )
        }


# ============================================================================
# SECTION 6: WORKLOAD INTEGRATION
# ============================================================================

@dataclass
class WorkloadParameters:
    """
    Workload multipliers derived from aviation research
    
    SCIENTIFIC REFERENCES:
    - Bourgeois-Bougrine S, Carbon P, Gounelle C, Mollard R, Coblentz A (2003).
      Perceived fatigue for short- and long-haul flights. Aviation, Space, and
      Environmental Medicine, 74(11), 1154-1160.
    - Cabon P, Coblentz A, Mollard R, Fouillot JP (1993). Human vigilance in
      railway and long-haul flight operation. Ergonomics, 36(9), 1019-1033.
    - Gander PH, Graeber RC, Foushee HC, Lauber JK, Connell LJ (1994). Crew
      factors in flight operations II: Psychophysiological responses to short-haul
      air transport operations. NASA Technical Memorandum 108856.
    - Desmond PA, Hancock PA (2001). Active and passive fatigue states.
      In: Stress, Workload, and Fatigue (pp. 455-465). CRC Press.
    """
    
    # Workload multipliers by flight phase
    # Derived from Bourgeois-Bougrine et al. (2003) and Cabon et al. (1993)
    # Values represent relative cognitive/attentional demand vs baseline cruise
    WORKLOAD_MULTIPLIERS: Dict[FlightPhase, float] = field(default_factory=lambda: {
        FlightPhase.PREFLIGHT: 1.1,    # Moderate - checklists, briefings
        FlightPhase.TAXI_OUT: 1.0,     # Baseline - routine
        FlightPhase.TAKEOFF: 1.8,      # High - critical phase, Gander et al. (1994)
        FlightPhase.CLIMB: 1.3,        # Elevated - active control
        FlightPhase.CRUISE: 0.8,       # Below baseline - monitoring task
        FlightPhase.DESCENT: 1.2,      # Elevated - planning, configuration
        FlightPhase.APPROACH: 1.5,     # High - precision required
        FlightPhase.LANDING: 2.0,      # Highest - critical phase, Gander et al. (1994)
        FlightPhase.TAXI_IN: 1.0,      # Baseline - routine
        FlightPhase.GROUND_TURNAROUND: 1.2,  # Elevated - time pressure
    })
    
    # Sector penalty - Bourgeois-Bougrine et al. (2003)
    # Cumulative fatigue increases ~15% per additional sector
    SECTOR_PENALTY_RATE: float = 0.15
    
    # Recovery parameters - Desmond & Hancock (2001)
    RECOVERY_THRESHOLD_HOURS: float = 2.0   # Minimum for meaningful recovery
    TURNAROUND_RECOVERY_RATE: float = 0.3   # Partial recovery factor


class WorkloadModel:
    """Integrates aviation workload into fatigue model"""
    
    def __init__(self, params: WorkloadParameters = None):
        self.params = params or WorkloadParameters()
    
    def get_phase_multiplier(self, phase: FlightPhase) -> float:
        return self.params.WORKLOAD_MULTIPLIERS.get(phase, 1.0)
    
    def get_sector_multiplier(self, sector_number: int) -> float:
        return 1.0 + (sector_number - 1) * self.params.SECTOR_PENALTY_RATE
    
    def get_combined_multiplier(self, phase: FlightPhase, sector_number: int) -> float:
        phase_mult = self.get_phase_multiplier(phase)
        sector_mult = self.get_sector_multiplier(sector_number)
        return phase_mult * sector_mult
    
    def calculate_effective_wake_time(
        self,
        actual_duration_hours: float,
        phase: FlightPhase,
        sector_number: int
    ) -> float:
        multiplier = self.get_combined_multiplier(phase, sector_number)
        return actual_duration_hours * multiplier
    
    def calculate_turnaround_recovery(
        self,
        turnaround_duration_hours: float,
        current_S: float,
        tau_d: float = 4.2
    ) -> float:
        """Calculate partial recovery during turnaround - Desmond & Hancock (2001)"""
        if turnaround_duration_hours < self.params.RECOVERY_THRESHOLD_HOURS:
            return current_S
        
        recovery_time_constant = tau_d / self.params.TURNAROUND_RECOVERY_RATE
        recovery_fraction = 1 - math.exp(-turnaround_duration_hours / recovery_time_constant)
        S_after = current_S * (1 - recovery_fraction)
        
        return max(0.0, S_after)


# ============================================================================
# SECTION 7: TIMELINE SIMULATION (included in BorbelyFatigueModel)
# ============================================================================
# See simulate_duty() method in BorbelyFatigueModel


# ============================================================================
# SECTION 8: ROSTER ANALYSIS ENGINE (included in BorbelyFatigueModel)
# ============================================================================
# See simulate_roster() method in BorbelyFatigueModel


# ============================================================================
# MAIN BORBÉLY FATIGUE MODEL CLASS
# ============================================================================

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
    - Aviation workload integration
    
    Uses the UNIFIED UnifiedSleepCalculator for all sleep estimation.
    """
    
    def __init__(self, config: ModelConfig = None):
        self.config = config or ModelConfig.default_easa_config()
        self.params = self.config.borbely_params
        self.adaptation_rates = self.config.adaptation_rates
        
        # UNIFIED: Use UnifiedSleepCalculator instead of external estimator
        self.sleep_calculator = UnifiedSleepCalculator(self.config)
        
        # EASA Compliance Validator
        self.validator = EASAComplianceValidator(self.config.easa_framework)
        
        # Workload Integration Model
        self.workload_model = WorkloadModel()
        
        # Use centralized parameters from config (avoid duplication)
        # All values sourced from BorbelyParameters with scientific citations
        self.s_upper = self.params.S_max       # Borbély (1982)
        self.s_lower = self.params.S_min + 0.1 # Small offset to prevent zero
        self.tau_i = self.params.tau_i         # Jewett & Kronauer (1999): 18.2h
        self.tau_d = self.params.tau_d         # Jewett & Kronauer (1999): 4.2h
        
        # Circadian parameters - from config
        self.c_amplitude = self.params.circadian_amplitude + 0.05  # Slight adjustment for operational context
        self.c_peak_hour = self.params.circadian_acrophase_hours - 1.0  # 16:00 for operational model
        
        # Time-on-duty surge - Dinges DF, Pack F, Williams K, et al. (1997)
        # Cumulative sleepiness, mood disturbance, and psychomotor vigilance.
        # Sleep, 20(4), 267-277.
        # Brief alertness increase at shift start due to arousal
        self.tod_surge_val = 0.05  # 5% surge - Dinges et al. (1997)
        
        # Light-based phase shift - Czeisler CA, et al. (1989)
        # Bright light induction of strong resetting of the human circadian pacemaker.
        # Science, 244(4910), 1328-1333.
        # Bright light can shift circadian phase by ~0.5h per exposure
        self.light_shift_rate = 0.5  # Hours per light exposure event
        
        # Fallback defaults when no prior data available
        self.default_wake_hour = 8   # Conservative assumption
        self.default_initial_s = 0.3 # Moderate initial sleep pressure
        
        # Storage for API access
        self.sleep_strategies = {}
    
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
        """Dynamic circadian phase shift adaptation"""
        elapsed_seconds = (current_utc - last_state.last_update_utc).total_seconds()
        if elapsed_seconds <= 0:
            return last_state
        
        elapsed_days = elapsed_seconds / 86400
        
        current_tz = pytz.timezone(current_tz_str)
        home_tz = pytz.timezone(home_base_tz_str)
        
        naive_time = current_utc.replace(tzinfo=None)
        home_offset = home_tz.localize(naive_time).utcoffset().total_seconds() / 3600
        current_offset = current_tz.localize(naive_time).utcoffset().total_seconds() / 3600
        
        target_shift = current_offset - home_offset
        diff = target_shift - last_state.current_phase_shift_hours
        rate = self.adaptation_rates.get_rate(diff)
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
        """Simplified Process S: Evolve from wake time"""
        hours_awake = (current_time - last_sleep_end).total_seconds() / 3600
        
        if hours_awake < 0:
            return s_at_wake
        
        s_current = self.params.S_max - (self.params.S_max - s_at_wake) * \
                    math.exp(-hours_awake / self.params.tau_i)
        
        return max(self.params.S_min, min(self.params.S_max, s_current))
    
    def compute_process_c(
        self,
        time_utc: datetime,
        reference_timezone: str,
        circadian_phase_shift: float = 0.0
    ) -> float:
        """Process C: Circadian alertness"""
        tz = pytz.timezone(reference_timezone)
        local_time = time_utc.astimezone(tz)
        hour_of_day = local_time.hour + local_time.minute / 60.0
        
        effective_hour = (hour_of_day - circadian_phase_shift) % 24
        angle = 2 * math.pi * (effective_hour - self.params.circadian_acrophase_hours) / 24
        c_value = (
            self.params.circadian_mesor +
            self.params.circadian_amplitude * math.cos(angle)
        )
        
        return max(0.0, min(1.0, c_value))
    
    def compute_sleep_inertia(self, time_since_wake: timedelta) -> float:
        """Process W: Sleep inertia"""
        minutes_awake = time_since_wake.total_seconds() / 60
        
        if minutes_awake > self.params.inertia_duration_minutes:
            return 0.0
        
        inertia = self.params.inertia_max_magnitude * math.exp(
            -minutes_awake / (self.params.inertia_duration_minutes / 3)
        )
        
        return inertia
    
    def update_s_process_corrected(self, s_current: float, delta_t: float, is_sleeping: bool) -> float:
        """CORRECTED Process S: Properly handles sleep vs wake states"""
        if is_sleeping:
            s_target = self.s_lower
            tau = self.tau_d
            return s_target + (s_current - s_target) * math.exp(-delta_t / tau)
        else:
            s_target = self.s_upper
            tau = self.tau_i
            return s_target - (s_target - s_current) * math.exp(-delta_t / tau)
    
    def integrate_s_and_c_multiplicative(self, s: float, c: float) -> float:
        """Weighted average integration"""
        s_alertness = 1.0 - s
        c_alertness = (c + 1.0) / 2.0
        base_alertness = s_alertness * 0.6 + c_alertness * 0.4
        return base_alertness
    
    def integrate_performance(self, c: float, s: float, w: float) -> float:
        """
        Integrate three processes into performance (0-100 scale)
        
        SCIENTIFIC REFERENCES:
        - Åkerstedt T, Folkard S (1997). The three-process model of alertness.
          Ergonomics, 40(3), 313-334.
        - Dawson D, Reid K (1997). Fatigue, alcohol and performance impairment.
          Nature, 388(6639), 235. (BAC equivalence for performance floor)
        """
        # Input validation with graceful clamping (not assertions)
        if not (0 <= c <= 1):
            logger.warning(f"Circadian component out of range: {c}, clamping to [0,1]")
            c = max(0.0, min(1.0, c))
        if not (0 <= s <= 1):
            logger.warning(f"Homeostatic component out of range: {s}, clamping to [0,1]")
            s = max(0.0, min(1.0, s))
        if not (0 <= w <= 1):
            logger.warning(f"Sleep inertia component out of range: {w}, clamping to [0,1]")
            w = max(0.0, min(1.0, w))
        
        c_phase = (c * 2.0) - 1.0
        base_alertness = self.integrate_s_and_c_multiplicative(s, c_phase)
        alertness_with_tot = base_alertness * (1.0 - w)
        
        # Performance floor of 20 represents severe impairment
        # Dawson & Reid (1997): 17-19h awake ≈ 0.05% BAC impairment
        # Below 20 would represent unsafe-to-operate levels
        MIN_PERFORMANCE_FLOOR = 20.0
        performance = MIN_PERFORMANCE_FLOOR + (alertness_with_tot * (100.0 - MIN_PERFORMANCE_FLOOR))
        performance = max(MIN_PERFORMANCE_FLOOR, min(100.0, performance))
        
        return performance
    
    # ========================================================================
    # SLEEP EXTRACTION
    # ========================================================================
    
    def extract_sleep_from_roster(
        self,
        roster: Roster,
        body_clock_timeline: List[Tuple[datetime, CircadianState]]
    ) -> Tuple[List[SleepBlock], Dict[str, Any]]:
        """
        Auto-generate sleep opportunities from duty gaps
        
        Uses UNIFIED UnifiedSleepCalculator for all sleep estimation.
        """
        sleep_blocks = []
        sleep_strategies = {}
        home_tz = pytz.timezone(roster.home_base_timezone)
        
        for i, duty in enumerate(roster.duties):
            previous_duty = roster.duties[i - 1] if i > 0 else None
            
            # Use UNIFIED sleep calculator
            strategy = self.sleep_calculator.estimate_sleep_for_duty(
                duty=duty,
                previous_duty=previous_duty,
                home_timezone=roster.home_base_timezone
            )
            
            for sleep_block in strategy.sleep_blocks:
                sleep_blocks.append(sleep_block)
            
            # Store strategy data for API exposure
            if strategy.quality_analysis:
                quality = strategy.quality_analysis[0]
                sleep_blocks_response = []
                
                if strategy.sleep_blocks:
                    for idx, block in enumerate(strategy.sleep_blocks):
                        sleep_start_local = block.start_utc.astimezone(home_tz)
                        sleep_end_local = block.end_utc.astimezone(home_tz)
                        
                        sleep_type = 'main'
                        if hasattr(block, 'is_anchor_sleep') and not block.is_anchor_sleep:
                            sleep_type = 'nap'
                        elif hasattr(block, 'is_inflight_rest') and block.is_inflight_rest:
                            sleep_type = 'inflight'
                        
                        sleep_blocks_response.append({
                            'sleep_start_time': sleep_start_local.strftime('%H:%M'),
                            'sleep_end_time': sleep_end_local.strftime('%H:%M'),
                            'sleep_start_iso': sleep_start_local.isoformat(),
                            'sleep_end_iso': sleep_end_local.isoformat(),
                            'sleep_type': sleep_type,
                            'duration_hours': block.duration_hours,
                            'effective_hours': block.effective_sleep_hours,
                            'quality_factor': block.quality_factor,
                            # Pre-computed positioning for frontend chronogram (avoids browser timezone issues)
                            'sleep_start_day': sleep_start_local.day,
                            'sleep_start_hour': sleep_start_local.hour + sleep_start_local.minute / 60.0,
                            'sleep_end_day': sleep_end_local.day,
                            'sleep_end_hour': sleep_end_local.hour + sleep_end_local.minute / 60.0
                        })
                    
                    first_block = strategy.sleep_blocks[0]
                    sleep_start_local = first_block.start_utc.astimezone(home_tz)
                    sleep_end_local = first_block.end_utc.astimezone(home_tz)
                    sleep_start_time = sleep_start_local.strftime('%H:%M')
                    sleep_end_time = sleep_end_local.strftime('%H:%M')
                else:
                    sleep_start_time = None
                    sleep_end_time = None
                
                sleep_strategies[duty.duty_id] = {
                    'strategy_type': strategy.strategy_type,
                    'confidence': strategy.confidence,
                    'total_sleep_hours': quality.total_sleep_hours,
                    'effective_sleep_hours': quality.effective_sleep_hours,
                    'sleep_efficiency': quality.sleep_efficiency,
                    'wocl_overlap_hours': quality.wocl_overlap_hours,
                    'warnings': [w['message'] for w in quality.warnings],
                    'sleep_start_time': sleep_start_time,
                    'sleep_end_time': sleep_end_time,
                    'sleep_blocks': sleep_blocks_response
                }
            
            # Generate rest day sleep for gap between this duty and next
            if i < len(roster.duties) - 1:
                next_duty = roster.duties[i + 1]
                duty_release = duty.release_time_utc.astimezone(home_tz)
                next_duty_report = next_duty.report_time_utc.astimezone(home_tz)
                
                gap_days = (next_duty_report.date() - duty_release.date()).days
                
                for rest_day_offset in range(1, gap_days):
                    rest_date = duty_release.date() + timedelta(days=rest_day_offset)
                    rest_day_key = f"rest_{rest_date.isoformat()}"
                    
                    sleep_start = home_tz.localize(
                        datetime.combine(rest_date - timedelta(days=1), time(23, 0))
                    )
                    sleep_end = home_tz.localize(
                        datetime.combine(rest_date, time(7, 0))
                    )
                    
                    recovery_block = SleepBlock(
                        start_utc=sleep_start.astimezone(pytz.utc),
                        end_utc=sleep_end.astimezone(pytz.utc),
                        location_timezone=home_tz.zone,
                        duration_hours=8.0,
                        quality_factor=0.95,
                        effective_sleep_hours=7.6,
                        environment='home'
                    )
                    
                    sleep_blocks.append(recovery_block)
                    
                    sleep_strategies[rest_day_key] = {
                        'strategy_type': 'recovery',
                        'confidence': 0.95,
                        'total_sleep_hours': 8.0,
                        'effective_sleep_hours': 7.6,
                        'sleep_efficiency': 0.95,
                        'wocl_overlap_hours': 0.0,
                        'warnings': [],
                        'sleep_start_time': '23:00',
                        'sleep_end_time': '07:00',
                        'sleep_blocks': [{
                            'sleep_start_time': '23:00',
                            'sleep_end_time': '07:00',
                            'sleep_start_iso': sleep_start.isoformat(),
                            'sleep_end_iso': sleep_end.isoformat(),
                            'sleep_type': 'main',
                            'duration_hours': 8.0,
                            'effective_hours': 7.6,
                            'quality_factor': 0.95
                        }]
                    }
        
        return sleep_blocks, sleep_strategies
    
    def _get_phase_shift_at_time(
        self,
        target_time: datetime,
        body_clock_timeline: List[Tuple[datetime, CircadianState]]
    ) -> float:
        for timestamp, state in reversed(body_clock_timeline):
            if timestamp <= target_time:
                return state.current_phase_shift_hours
        return 0.0
    
    # ========================================================================
    # FLIGHT PHASES
    # ========================================================================
    
    def get_flight_phase(self, segments: List[FlightSegment], current_time: datetime) -> FlightPhase:
        """Determine phase from segment schedule"""
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
        """Simulate single duty with high-resolution timeline"""
        
        timeline = []
        duty_duration = (duty.release_time_utc - duty.report_time_utc).total_seconds() / 3600
        logger.debug(f"[{duty.duty_id}] Timeline sim: Duration={duty_duration:.1f}h, Sleep blocks={len(sleep_history)}")
        
        # Find last sleep and calculate S_0
        last_sleep = None
        for sleep in reversed(sleep_history):
            if sleep.end_utc <= duty.report_time_utc:
                last_sleep = sleep
                break
        
        if last_sleep:
            sleep_quality_ratio = last_sleep.effective_sleep_hours / 8.0
            s_at_wake = max(0.1, 0.7 - (sleep_quality_ratio * 0.6))
            wake_time = last_sleep.end_utc
        else:
            s_at_wake = initial_s
            wake_time = duty.report_time_utc - timedelta(hours=8)
        
        def get_current_sector(current_time: datetime) -> int:
            sector = 1
            for seg in duty.segments:
                if current_time >= seg.scheduled_departure_utc:
                    if seg == duty.segments[0]:
                        sector = 1
                    else:
                        prev_seg = duty.segments[duty.segments.index(seg) - 1]
                        if seg.scheduled_departure_utc > prev_seg.scheduled_arrival_utc:
                            sector += 1
            return sector
        
        effective_wake_hours = 0.0
        s_current = s_at_wake
        current_time = duty.report_time_utc
        
        # Ensure minimum duty length
        if duty_duration <= 0:
            logger.warning(f"[{duty.duty_id}] Invalid time range. Using 8-hour minimum.")
            duty.release_time_utc = duty.report_time_utc + timedelta(hours=8)
        
        while current_time <= duty.release_time_utc:
            current_sector = get_current_sector(current_time)
            phase = self.get_flight_phase(duty.segments, current_time)
            step_duration_hours = resolution_minutes / 60.0
            
            workload_multiplier = self.workload_model.get_combined_multiplier(phase, current_sector)
            effective_step_duration = step_duration_hours * workload_multiplier
            effective_wake_hours += effective_step_duration
            
            s_current = self.params.S_max - (self.params.S_max - s_at_wake) * \
                        math.exp(-effective_wake_hours / self.params.tau_i)
            s_current = max(self.params.S_min, min(self.params.S_max, s_current))
            
            c = self.compute_process_c(current_time, duty.home_base_timezone, circadian_phase_shift)
            current_wake = current_time - wake_time
            w = self.compute_sleep_inertia(current_wake)
            performance = self.integrate_performance(c, s_current, w)
            
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
            current_time += timedelta(minutes=resolution_minutes)
        
        duty_timeline = self._build_duty_timeline(duty, timeline, sleep_history, circadian_phase_shift)
        duty_timeline.final_process_s = s_current
        
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
            logger.warning(f"[{duty.duty_id}] Empty timeline - using fallback calculation")
            tz = pytz.timezone(duty.home_base_timezone)
            mid_duty_time = duty.report_time_utc + (duty.release_time_utc - duty.report_time_utc) / 2
            
            s_estimate = 0.3
            for sleep in reversed(sleep_history):
                if sleep.end_utc <= duty.report_time_utc:
                    sleep_quality_ratio = sleep.effective_sleep_hours / 8.0
                    s_estimate = max(0.1, 0.7 - (sleep_quality_ratio * 0.6))
                    break
            
            c_estimate = self.compute_process_c(mid_duty_time, duty.home_base_timezone, phase_shift)
            default_performance = self.integrate_performance(c_estimate, s_estimate, 0.0)
            
            return DutyTimeline(
                duty_id=duty.duty_id,
                duty_date=duty.date,
                timeline=[],
                min_performance=default_performance,
                average_performance=default_performance,
                landing_performance=default_performance,
                prior_sleep_hours=sum(s.effective_sleep_hours for s in sleep_history[-3:] if s.end_utc <= duty.report_time_utc),
                wocl_encroachment_hours=self.validator.is_disruptive_duty(duty).get('wocl_hours', 0.0)
            )
        
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
        """Process entire roster with cumulative tracking"""
        if not roster.duties or len(roster.duties) == 0:
            raise ValueError("Cannot simulate roster: No duties found.")
        
        duty_timelines = []
        current_s = roster.initial_sleep_pressure
        cumulative_sleep_debt = roster.initial_sleep_debt
        
        body_clock = CircadianState(
            current_phase_shift_hours=0.0,
            last_update_utc=roster.duties[0].report_time_utc - timedelta(days=1),
            reference_timezone=roster.home_base_timezone
        )
        
        body_clock_timeline = [(body_clock.last_update_utc, body_clock)]
        
        for duty in roster.duties:
            departure_tz = duty.segments[0].departure_airport.timezone
            body_clock = self.calculate_adaptation(
                duty.report_time_utc, body_clock, departure_tz, roster.home_base_timezone
            )
            body_clock_timeline.append((duty.report_time_utc, body_clock))
        
        all_sleep, sleep_strategies = self.extract_sleep_from_roster(roster, body_clock_timeline)
        self.sleep_strategies = sleep_strategies
        
        previous_duty = None
        previous_timeline = None
        
        for i, duty in enumerate(roster.duties):
            phase_shift = self._get_phase_shift_at_time(duty.report_time_utc, body_clock_timeline)
            
            relevant_sleep = [
                s for s in all_sleep
                if s.end_utc <= duty.report_time_utc and
                   s.end_utc >= duty.report_time_utc - timedelta(hours=48)
            ]
            
            cached_s_value = None
            if previous_timeline and previous_timeline.final_process_s > 0:
                cached_s_value = previous_timeline.final_process_s
            
            timeline_obj = self.simulate_duty(
                duty, relevant_sleep, phase_shift, 
                initial_s=current_s,
                cached_s=cached_s_value
            )
            previous_timeline = timeline_obj
            
            fdp_limits = self.validator.calculate_fdp_limits(duty)
            duty.max_fdp_hours = fdp_limits['max_fdp']
            duty.extended_fdp_hours = fdp_limits['extended_fdp']
            duty.used_discretion = fdp_limits['used_discretion']
            
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
            
            if duty.duty_id in sleep_strategies:
                strategy_data = sleep_strategies[duty.duty_id]
                timeline_obj.sleep_strategy_type = strategy_data.get('strategy_type')
                timeline_obj.sleep_confidence = strategy_data.get('confidence')
                timeline_obj.sleep_quality_data = strategy_data
            
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


# ============================================================================
# MODULE EXPORTS
# ============================================================================

__all__ = [
    # Configuration
    'EASAFatigueFramework',
    'BorbelyParameters',
    'SleepQualityParameters',
    'AdaptationRates',
    'RiskThresholds',
    'ModelConfig',
    
    # Sleep Calculation (UNIFIED)
    'UnifiedSleepCalculator',
    'SleepQualityAnalysis',
    'SleepStrategy',
    
    # EASA Compliance
    'EASAComplianceValidator',
    
    # Workload
    'WorkloadParameters',
    'WorkloadModel',
    
    # Main Model
    'BorbelyFatigueModel',
]
