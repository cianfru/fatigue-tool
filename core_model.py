"""
Aerowake Aviation Fatigue Prediction System
Version 6.0 - Polished Unified Architecture

A biomathematical fatigue model for airline pilots based on:
- Borbély Two-Process Model (homeostatic + circadian)
- EASA FTL regulatory framework
- Aviation workload integration
- Realistic sleep behavior modeling

Scientific Foundation:
    Borbély & Achermann (1999), Jewett & Kronauer (1999), Van Dongen et al. (2003),
    Signal et al. (2009), Gander et al. (2013), Bourgeois-Bougrine et al. (2003)
"""

from datetime import datetime, timedelta, time
from typing import List, Tuple, Optional, Dict, Any
from dataclasses import dataclass, field
import math
import pytz
import logging

logger = logging.getLogger(__name__)

# Import data models
from data_models import (
    Duty, Roster, FlightSegment, SleepBlock, CircadianState,
    PerformancePoint, PinchEvent, DutyTimeline, MonthlyAnalysis, FlightPhase
)


# ============================================================================
# CONFIGURATION & PARAMETERS
# ============================================================================

@dataclass
class EASAFatigueFramework:
    """EASA FTL regulatory definitions (EU Regulation 965/2012)"""
    
    # WOCL definition - AMC1 ORO.FTL.105(10)
    wocl_start_hour: int = 2
    wocl_end_hour: int = 5
    wocl_end_minute: int = 59
    
    # Acclimatization thresholds - AMC1 ORO.FTL.105(1)
    acclimatization_timezone_band_hours: float = 2.0
    acclimatization_required_local_nights: int = 3
    
    # Duty time definitions
    local_night_start_hour: int = 22
    local_night_end_hour: int = 8
    early_start_threshold_hour: int = 6
    late_finish_threshold_hour: int = 2
    
    # Rest requirements - ORO.FTL.235
    minimum_rest_hours: float = 12.0
    minimum_sleep_opportunity_hours: float = 8.0
    
    # FDP limits - ORO.FTL.205
    max_fdp_basic_hours: float = 13.0
    max_duty_hours: float = 14.0


@dataclass
class BorbelyParameters:
    """
    Two-process sleep regulation model parameters
    References: Borbély (1982, 1999), Jewett & Kronauer (1999), Van Dongen (2003)
    """
    
    # Process S bounds
    S_max: float = 1.0
    S_min: float = 0.0
    
    # Time constants (Jewett & Kronauer 1999)
    tau_i: float = 18.2  # Buildup during wake (hours)
    tau_d: float = 4.2   # Decay during sleep (hours)
    
    # Process C parameters
    circadian_amplitude: float = 0.25
    circadian_mesor: float = 0.5
    circadian_period_hours: float = 24.0
    circadian_acrophase_hours: float = 17.0  # Peak alertness time
    
    # Performance integration — operational weighting choice.
    # The Åkerstedt-Folkard three-process model uses additive S+C
    # combination; these explicit weights are an operational adaptation,
    # not directly from the literature. Research config uses 50/50.
    weight_circadian: float = 0.4
    weight_homeostatic: float = 0.6
    interaction_exponent: float = 1.5
    
    # Sleep inertia (Tassi & Muzet 2000)
    inertia_duration_minutes: float = 30.0
    inertia_max_magnitude: float = 0.30
    
    # Sleep debt
    # Baseline 8h need: Van Dongen et al. (2003) Sleep 26(2):117-126
    # Decay rate 0.25: operational estimate for exponential debt recovery;
    # Van Dongen (2003) demonstrated cumulative deficits but did not
    # specify an exponential decay rate. Value may derive from SAFTE/FAST
    # model family (Hursh et al. 2004).
    baseline_sleep_need_hours: float = 8.0
    sleep_debt_decay_rate: float = 0.25


@dataclass
class SleepQualityParameters:
    """
    Sleep quality multipliers by environment

    Primary reference: Signal et al. (2013) Sleep 36(1):109-118
    — PSG-measured hotel efficiency 88%, inflight bunk 70%.
    Values below are operational estimates calibrated to Signal (2013).
    Note: Åkerstedt (2003) Occup Med 53:89-94 covers shift-work sleep
    disruption but does not provide hotel-specific efficiency values.
    """

    # Environment quality factors (aligned with LOCATION_EFFICIENCY in
    # UnifiedSleepCalculator to avoid duplicate definitions)
    quality_home: float = 1.0
    quality_hotel_quiet: float = 0.88   # Signal et al. (2013) PSG: 88%
    quality_hotel_typical: float = 0.85
    quality_hotel_airport: float = 0.82
    quality_crew_rest_facility: float = 0.70  # Signal et al. (2013) PSG: 70%
    
    # Circadian timing penalties
    max_circadian_quality_penalty: float = 0.25
    early_wake_penalty_per_hour: float = 0.05
    late_sleep_start_penalty_per_hour: float = 0.03


@dataclass
class AdaptationRates:
    """
    Circadian adaptation rates for timezone shifts
    Reference: Waterhouse et al. (2007)
    """
    
    westward_hours_per_day: float = 1.5  # Phase delay (easier)
    eastward_hours_per_day: float = 1.0  # Phase advance (harder)
    
    def get_rate(self, timezone_shift_hours: float) -> float:
        return self.westward_hours_per_day if timezone_shift_hours < 0 else self.eastward_hours_per_day


@dataclass
class RiskThresholds:
    """Performance score thresholds with EASA references"""
    
    thresholds: Dict[str, Tuple[float, float]] = field(default_factory=lambda: {
        'low': (75, 100),
        'moderate': (65, 75),
        'high': (55, 65),
        'critical': (45, 55),
        'extreme': (0, 45)
    })
    
    actions: Dict[str, Dict[str, str]] = field(default_factory=lambda: {
        'low': {'action': 'None required', 'description': 'Well-rested state'},
        'moderate': {'action': 'Enhanced monitoring', 'description': 'Equivalent to ~6h sleep'},
        'high': {'action': 'Mitigation required', 'description': 'Equivalent to ~5h sleep'},
        'critical': {'action': 'MANDATORY roster modification', 'description': 'Equivalent to ~4h sleep'},
        'extreme': {'action': 'UNSAFE - Do not fly', 'description': 'Severe impairment'}
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
    """Master configuration container"""
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
        """
        Stricter thresholds for safety-first analysis.
        - Faster homeostatic pressure buildup (shorter tau_i)
        - Slower recovery during sleep (longer tau_d)
        - Higher baseline sleep need
        - Stronger circadian penalties on sleep quality
        - Tighter risk thresholds (scores shift up by ~5 points)
        """
        return cls(
            easa_framework=EASAFatigueFramework(),
            borbely_params=BorbelyParameters(
                tau_i=16.0,
                tau_d=4.8,
                baseline_sleep_need_hours=8.5,
                inertia_duration_minutes=40.0,
                inertia_max_magnitude=0.35,
            ),
            risk_thresholds=RiskThresholds(thresholds={
                'low': (80, 100),
                'moderate': (70, 80),
                'high': (60, 70),
                'critical': (50, 60),
                'extreme': (0, 50)
            }),
            adaptation_rates=AdaptationRates(
                westward_hours_per_day=1.0,
                eastward_hours_per_day=0.7,
            ),
            sleep_quality_params=SleepQualityParameters(
                quality_hotel_typical=0.75,
                quality_hotel_airport=0.70,
                quality_crew_rest_facility=0.60,
                max_circadian_quality_penalty=0.30,
            )
        )

    @classmethod
    def liberal_config(cls):
        """
        Relaxed thresholds for experienced-crew / low-risk route analysis.
        - Slower homeostatic pressure buildup (longer tau_i)
        - Faster recovery during sleep (shorter tau_d)
        - Lower baseline sleep need
        - Looser risk thresholds (scores shift down by ~5 points)
        """
        return cls(
            easa_framework=EASAFatigueFramework(),
            borbely_params=BorbelyParameters(
                tau_i=20.0,
                tau_d=3.8,
                baseline_sleep_need_hours=7.5,
                inertia_duration_minutes=20.0,
                inertia_max_magnitude=0.25,
            ),
            risk_thresholds=RiskThresholds(thresholds={
                'low': (70, 100),
                'moderate': (60, 70),
                'high': (50, 60),
                'critical': (40, 50),
                'extreme': (0, 40)
            }),
            adaptation_rates=AdaptationRates(
                westward_hours_per_day=1.8,
                eastward_hours_per_day=1.2,
            ),
            sleep_quality_params=SleepQualityParameters(
                quality_hotel_typical=0.85,
                quality_hotel_airport=0.80,
                quality_crew_rest_facility=0.70,
            )
        )

    @classmethod
    def research_config(cls):
        """
        Textbook Borbély two-process parameters for academic comparison.
        Uses values from Jewett & Kronauer (1999) and Van Dongen (2003)
        without operational adjustments.
        """
        return cls(
            easa_framework=EASAFatigueFramework(),
            borbely_params=BorbelyParameters(
                tau_i=18.2,
                tau_d=4.2,
                circadian_amplitude=0.30,
                weight_circadian=0.5,
                weight_homeostatic=0.5,
                interaction_exponent=1.0,
                baseline_sleep_need_hours=8.0,
            ),
            risk_thresholds=RiskThresholds(),
            adaptation_rates=AdaptationRates(),
            sleep_quality_params=SleepQualityParameters()
        )


# ============================================================================
# SLEEP QUALITY ANALYSIS
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
    """Pilot's strategic sleep approach"""
    strategy_type: str
    sleep_blocks: List[SleepBlock]
    confidence: float
    explanation: str
    quality_analysis: List[SleepQualityAnalysis]


# ============================================================================
# UNIFIED SLEEP CALCULATOR
# ============================================================================

class UnifiedSleepCalculator:
    """
    Unified sleep estimation engine for airline pilots
    
    Estimates realistic pilot sleep patterns based on:
    - Duty timing (night flights, early reports, WOCL duties)
    - Circadian alignment (WOCL overlap)
    - Recovery needs (post-duty rest)
    - Time pressure (short turnarounds)
    
    References: Signal et al. (2009), Gander et al. (2013), Roach et al. (2012)
    """
    
    def __init__(self, config: ModelConfig = None):
        self.config = config or ModelConfig.default_easa_config()
        
        # Sleep timing parameters — operational defaults for working-age pilots.
        # Roenneberg et al. (2007) Sleep Med Rev 11:429-438 characterised
        # chronotype distributions (avg free-day mid-sleep ~04:00-05:00);
        # the 23:00 bedtime here reflects alarm-constrained workday timing,
        # consistent with pilot actigraphy in Signal et al. (2009) and
        # Gander et al. (2013).
        self.NORMAL_BEDTIME_HOUR = 23
        self.NORMAL_WAKE_HOUR = 7
        self.NORMAL_SLEEP_DURATION = 8.0
        
        # Operational thresholds
        self.NIGHT_FLIGHT_THRESHOLD = 20  # EASA late-type duty
        self.EARLY_REPORT_THRESHOLD = 7
        
        # WOCL definition — aligned with EASAFatigueFramework (02:00-05:59)
        # per EASA ORO.FTL.105(28). Using 6.0 as float boundary so that
        # hour < 6.0 covers 02:00-05:59 correctly in overlap calculations.
        self.WOCL_START = self.config.easa_framework.wocl_start_hour  # 2
        self.WOCL_END = self.config.easa_framework.wocl_end_hour + 1  # 6 (exclusive upper bound)
        
        # Base efficiency by location — aligned with SleepQualityParameters.
        # Hotel value calibrated to Signal et al. (2013) PSG data (88% layover).
        self.LOCATION_EFFICIENCY = {
            'home': 0.90,
            'hotel': 0.85,
            'crew_rest': 0.70,       # Signal et al. (2013): 70% inflight bunk
            'airport_hotel': 0.82,
            'crew_house': 0.87
        }
        
        # Biological limits
        self.MAX_REALISTIC_SLEEP = 10.0
        self.MIN_SLEEP_FOR_QUALITY = 6.0
        
        self.home_tz = None
    
    def estimate_sleep_for_duty(
        self,
        duty: Duty,
        previous_duty: Optional[Duty] = None,
        home_timezone: str = 'UTC'
    ) -> SleepStrategy:
        """Main entry point: Estimate how pilot actually slept before duty"""
        
        self.home_tz = pytz.timezone(home_timezone)
        report_local = duty.report_time_utc.astimezone(self.home_tz)
        report_hour = report_local.hour
        
        # Calculate duty characteristics
        duty_duration = (duty.release_time_utc - duty.report_time_utc).total_seconds() / 3600
        crosses_wocl = self._duty_crosses_wocl(duty)
        
        # Decision tree: match pilot behavior patterns
        if report_hour >= self.NIGHT_FLIGHT_THRESHOLD or report_hour < 4:
            return self._night_departure_strategy(duty, previous_duty)
        elif report_hour < self.EARLY_REPORT_THRESHOLD:
            return self._early_morning_strategy(duty, previous_duty)
        elif crosses_wocl and duty_duration > 6:
            return self._wocl_duty_strategy(duty, previous_duty)
        else:
            return self._normal_sleep_strategy(duty, previous_duty)
    
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
        """Calculate realistic sleep quality with all factors"""
        
        # 1. Calculate raw duration
        total_hours = (sleep_end - sleep_start).total_seconds() / 3600
        
        # 2. Apply biological sleep limit
        actual_duration = min(total_hours, self.MAX_REALISTIC_SLEEP) if not is_nap else total_hours
        
        # 3. Base efficiency by location
        base_efficiency = self.LOCATION_EFFICIENCY.get(location, 0.85)
        if is_nap:
            # Operational estimate: naps contain less SWS per unit time than
            # anchor sleep. Dinges et al. (1987) Sleep 10:313 found total sleep
            # quantity matters more than division, but brief naps are lighter
            # (Stage 1-2 dominant). The 12% penalty is a modelling choice.
            base_efficiency *= 0.88
        
        # 4. WOCL overlap boost (sleep during biological night enhances recovery)
        # Scientific basis: Dijk & Czeisler (1995), Borbély (1999)
        # Sleep during WOCL is circadian-aligned → improved sleep consolidation
        # (fewer awakenings, higher efficiency). Note: SWA is primarily
        # homeostatic, not circadian — Dijk & Czeisler (1995) J Neurosci 15:3526
        wocl_overlap = self._calculate_wocl_overlap(sleep_start, sleep_end, location_timezone)
        wocl_boost = 1.0 + (wocl_overlap * 0.03)  # 3% boost per hour
        wocl_boost = min(1.15, wocl_boost)  # Cap at 15%
        
        # 5. Late sleep onset penalty
        tz = pytz.timezone(location_timezone)
        sleep_start_local = sleep_start.astimezone(tz)
        sleep_start_hour = sleep_start_local.hour + sleep_start_local.minute / 60.0
        
        if sleep_start_hour >= 1 and sleep_start_hour < 4:
            late_onset_penalty = 0.93
        elif sleep_start_hour >= 0 and sleep_start_hour < 1:
            late_onset_penalty = 0.97
        else:
            late_onset_penalty = 1.0
        
        # 6. Recovery sleep boost — operational estimate.
        # Post-duty sleep with high homeostatic drive shows enhanced SWA
        # rebound (Borbély 1982), faster onset, and fewer awakenings.
        # The 10% boost and 3h threshold are modelling choices, not from
        # a specific published value.
        if previous_duty_end:
            hours_since_duty = (sleep_start - previous_duty_end).total_seconds() / 3600
            recovery_boost = 1.10 if hours_since_duty < 3 and not is_nap else 1.0
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
            * wocl_boost
            * late_onset_penalty
            * recovery_boost
            * time_pressure_factor
            * insufficient_penalty
        )
        combined_efficiency = max(0.65, min(1.0, combined_efficiency))  # Realistic floor
        
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
            wocl_penalty=1.0,  # Now using wocl_boost instead
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
        Converts to local timezone FIRST to avoid timezone bugs
        """
        
        tz = pytz.timezone(location_timezone)
        sleep_start_local = sleep_start.astimezone(tz)
        sleep_end_local = sleep_end.astimezone(tz)
        
        sleep_start_hour = sleep_start_local.hour + sleep_start_local.minute / 60.0
        sleep_end_hour = sleep_end_local.hour + sleep_end_local.minute / 60.0
        
        overlap_hours = 0.0
        
        # Handle overnight sleep (crosses midnight)
        if sleep_end_hour < sleep_start_hour or sleep_end_local.date() > sleep_start_local.date():
            # Day 1: From sleep_start to end of day
            if sleep_start_hour < self.WOCL_END:
                day1_overlap_start = max(sleep_start_hour, self.WOCL_START)
                day1_overlap_end = min(24.0, self.WOCL_END)
                if day1_overlap_start < day1_overlap_end:
                    overlap_hours += day1_overlap_end - day1_overlap_start
            
            # Day 2: From start of day to sleep_end
            if sleep_end_hour > self.WOCL_START:
                day2_overlap_start = max(0.0, self.WOCL_START)
                day2_overlap_end = min(sleep_end_hour, self.WOCL_END)
                if day2_overlap_start < day2_overlap_end:
                    overlap_hours += day2_overlap_end - day2_overlap_start
        else:
            # Same-day sleep
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
        
        if wocl_overlap > 2.5 and effective_sleep < 6:
            warnings.append({
                'severity': 'info',
                'message': f'{wocl_overlap:.1f}h sleep during WOCL may reduce quality',
                'recommendation': 'Circadian misalignment detected'
            })
        
        if hours_until_duty and hours_until_duty < 2 and actual_duration < 5:
            warnings.append({
                'severity': 'critical',
                'message': 'Very short turnaround with minimal sleep',
                'recommendation': 'Report fatigue concerns to operations'
            })
        
        return warnings
    
    # ========================================================================
    # SLEEP STRATEGIES
    # ========================================================================
    
    def _night_departure_strategy(
        self,
        duty: Duty,
        previous_duty: Optional[Duty]
    ) -> SleepStrategy:
        """
        Night flight strategy: morning sleep + pre-duty nap

        Signal et al. (2014) found 54% of crew napped before evening
        departures, with typical nap durations of 1-2 hours. Gander et al.
        (2014) reported ~7.8h total pre-trip sleep (including naps).

        References:
            Signal et al. (2014) Aviat Space Environ Med 85:1199-1208
            Gander et al. (2014) Aviat Space Environ Med 85(8):833-40
        """

        report_local = duty.report_time_utc.astimezone(self.home_tz)

        # Morning sleep (23:00-07:00, standard 8h window)
        morning_sleep_start = report_local.replace(hour=self.NORMAL_BEDTIME_HOUR, minute=0) - timedelta(days=1)
        morning_sleep_end = report_local.replace(hour=7, minute=0)
        
        morning_sleep_start_utc, morning_sleep_end_utc, morning_warnings = self._validate_sleep_no_overlap(
            morning_sleep_start.astimezone(pytz.utc), morning_sleep_end.astimezone(pytz.utc), duty, previous_duty
        )
        morning_sleep_start = morning_sleep_start_utc.astimezone(self.home_tz)
        morning_sleep_end = morning_sleep_end_utc.astimezone(self.home_tz)
        
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
            environment='home',
            sleep_start_day=morning_sleep_start.day,
            sleep_start_hour=morning_sleep_start.hour + morning_sleep_start.minute / 60.0,
            sleep_end_day=morning_sleep_end.day,
            sleep_end_hour=morning_sleep_end.hour + morning_sleep_end.minute / 60.0
        )
        
        # Pre-duty nap: 2h duration (Signal 2014 found typical naps 1-2h;
        # only 54% of crew napped, so confidence is reduced accordingly)
        nap_end = report_local - timedelta(hours=1.5)
        nap_start = nap_end - timedelta(hours=2.0)
        
        nap_start_utc, nap_end_utc, nap_warnings = self._validate_sleep_no_overlap(
            nap_start.astimezone(pytz.utc), nap_end.astimezone(pytz.utc), duty, previous_duty
        )
        nap_start = nap_start_utc.astimezone(self.home_tz)
        nap_end = nap_end_utc.astimezone(self.home_tz)
        
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
            environment='home',
            sleep_start_day=nap_start.day,
            sleep_start_hour=nap_start.hour + nap_start.minute / 60.0,
            sleep_end_day=nap_end.day,
            sleep_end_hour=nap_end.hour + nap_end.minute / 60.0
        )
        
        total_effective = morning_quality.effective_sleep_hours + nap_quality.effective_sleep_hours
        # Confidence lowered: Signal (2014) found only 54% of crew nap
        confidence = 0.60 if not (morning_warnings or nap_warnings) else 0.45
        
        return SleepStrategy(
            strategy_type='afternoon_nap',
            sleep_blocks=[morning_sleep, afternoon_nap],
            confidence=confidence,
            explanation=f"Night departure: {morning_quality.actual_sleep_hours:.1f}h + "
                       f"{nap_quality.actual_sleep_hours:.1f}h nap = {total_effective:.1f}h effective",
            quality_analysis=[morning_quality, nap_quality]
        )
    
    def _early_morning_strategy(
        self,
        duty: Duty,
        previous_duty: Optional[Duty]
    ) -> SleepStrategy:
        """
        Early report strategy: constrained early bedtime

        Pilots cannot fully compensate for early report times by advancing
        bedtime, due to the circadian wake maintenance zone (peak alerting
        ~17:00-19:00). Actigraphy data shows ~15 min sleep lost per hour
        of duty advance before 09:00.

        References:
            Roach et al. (2012) Accid Anal Prev 45 Suppl:22-26
            Arsintescu et al. (2022) J Sleep Res 31(3):e13521
        """

        report_local = duty.report_time_utc.astimezone(self.home_tz)

        # Roach et al. (2012): pilots lose ~15 min sleep per hour of duty
        # advance before 09:00. Baseline 6.6h at 09:00 report.
        # Formula: sleep_hours ≈ 6.6 - 0.25 * max(0, 9 - report_hour)
        report_hour = report_local.hour + report_local.minute / 60.0
        sleep_duration = max(4.0, 6.6 - 0.25 * max(0, 9.0 - report_hour))

        # Earliest realistic bedtime is ~21:30 (circadian opposition before this)
        # Arsintescu et al. (2022): pilots do not sufficiently advance bedtime
        wake_time = report_local - timedelta(hours=1)
        sleep_end = wake_time
        earliest_bedtime = report_local.replace(hour=21, minute=30) - timedelta(days=1)
        sleep_start = max(earliest_bedtime, sleep_end - timedelta(hours=sleep_duration))
        
        sleep_start_utc, sleep_end_utc, sleep_warnings = self._validate_sleep_no_overlap(
            sleep_start.astimezone(pytz.utc), sleep_end.astimezone(pytz.utc), duty, previous_duty
        )
        sleep_start = sleep_start_utc.astimezone(self.home_tz)
        sleep_end = sleep_end_utc.astimezone(self.home_tz)
        
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
            environment='home',
            sleep_start_day=sleep_start.day,
            sleep_start_hour=sleep_start.hour + sleep_start.minute / 60.0,
            sleep_end_day=sleep_end.day,
            sleep_end_hour=sleep_end.hour + sleep_end.minute / 60.0
        )
        
        # Lower confidence reflects Roach (2012) finding of high variability
        # in early-start sleep; individual differences in circadian tolerance
        confidence = 0.55 if not sleep_warnings else 0.40

        return SleepStrategy(
            strategy_type='early_bedtime',
            sleep_blocks=[early_sleep],
            confidence=confidence,
            explanation=f"Early report: Constrained bedtime = {sleep_quality.effective_sleep_hours:.1f}h effective "
                       f"(Roach 2012 regression: {sleep_duration:.1f}h predicted)",
            quality_analysis=[sleep_quality]
        )
    
    def _wocl_duty_strategy(
        self,
        duty: Duty,
        previous_duty: Optional[Duty]
    ) -> SleepStrategy:
        """WOCL duty strategy: anchor sleep before duty"""
        
        report_local = duty.report_time_utc.astimezone(self.home_tz)
        
        anchor_end = report_local - timedelta(hours=1.5)
        anchor_start = anchor_end - timedelta(hours=4.5)
        
        anchor_start_utc, anchor_end_utc, anchor_warnings = self._validate_sleep_no_overlap(
            anchor_start.astimezone(pytz.utc), anchor_end.astimezone(pytz.utc), duty, previous_duty
        )
        anchor_start = anchor_start_utc.astimezone(self.home_tz)
        anchor_end = anchor_end_utc.astimezone(self.home_tz)
        
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
            environment='home',
            sleep_start_day=anchor_start.day,
            sleep_start_hour=anchor_start.hour + anchor_start.minute / 60.0,
            sleep_end_day=anchor_end.day,
            sleep_end_hour=anchor_end.hour + anchor_end.minute / 60.0
        )
        
        confidence = 0.50 if not anchor_warnings else 0.35
        
        return SleepStrategy(
            strategy_type='split_sleep',
            sleep_blocks=[anchor_sleep],
            confidence=confidence,
            explanation=f"WOCL duty: Split sleep = {anchor_quality.effective_sleep_hours:.1f}h effective",
            quality_analysis=[anchor_quality]
        )
    
    def _normal_sleep_strategy(
        self,
        duty: Duty,
        previous_duty: Optional[Duty]
    ) -> SleepStrategy:
        """
        Normal daytime duty - standard sleep pattern
        
        Pilots maintain consistent wake times (~07:00) regardless of duty start.
        They do NOT delay wake for afternoon duties.
        Performance degradation for later duties is expected and modeled.
        """
        
        report_local = duty.report_time_utc.astimezone(self.home_tz)
        
        # All normal duties: sleep previous night, wake at normal time
        sleep_start = report_local.replace(hour=self.NORMAL_BEDTIME_HOUR, minute=0) - timedelta(days=1)
        sleep_end = report_local.replace(hour=self.NORMAL_WAKE_HOUR, minute=0)
        
        sleep_start_utc, sleep_end_utc, sleep_warnings = self._validate_sleep_no_overlap(
            sleep_start.astimezone(pytz.utc), sleep_end.astimezone(pytz.utc), duty, previous_duty
        )
        sleep_start = sleep_start_utc.astimezone(self.home_tz)
        sleep_end = sleep_end_utc.astimezone(self.home_tz)
        
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
            environment='home',
            sleep_start_day=sleep_start.day,
            sleep_start_hour=sleep_start.hour + sleep_start.minute / 60.0,
            sleep_end_day=sleep_end.day,
            sleep_end_hour=sleep_end.hour + sleep_end.minute / 60.0
        )
        
        # Calculate awake duration
        awake_hours = (report_local - sleep_end).total_seconds() / 3600
        
        # Confidence decreases with longer awake periods
        if awake_hours < 2:
            confidence = 0.95
        elif awake_hours < 6:
            confidence = 0.90
        elif awake_hours < 10:
            confidence = 0.80
        else:
            confidence = 0.70
        
        if sleep_warnings:
            confidence *= 0.8
        
        return SleepStrategy(
            strategy_type='normal',
            sleep_blocks=[normal_sleep],
            confidence=confidence,
            explanation=f"Normal sleep ({sleep_quality.effective_sleep_hours:.1f}h effective), {awake_hours:.1f}h awake before duty",
            quality_analysis=[sleep_quality]
        )
    
    # ========================================================================
    # HELPER METHODS
    # ========================================================================
    
    def _validate_sleep_no_overlap(
        self,
        sleep_start: datetime,
        sleep_end: datetime,
        duty: Duty,
        previous_duty: Optional[Duty] = None
    ) -> Tuple[datetime, datetime, List[str]]:
        """Validate sleep doesn't overlap with duty periods"""
        
        warnings = []
        adjusted_start = sleep_start
        adjusted_end = sleep_end
        
        # Check overlap with current duty
        if adjusted_end > duty.report_time_utc:
            adjusted_end = duty.report_time_utc - timedelta(minutes=30)
            warnings.append("Sleep truncated: would overlap with duty report time")
        
        # Check overlap with previous duty
        if previous_duty and adjusted_start < previous_duty.release_time_utc:
            adjusted_start = previous_duty.release_time_utc + timedelta(hours=1)
            warnings.append("Sleep delayed: previous duty not yet released")
        
        # Ensure valid sleep period
        if adjusted_start >= adjusted_end:
            if previous_duty:
                earliest_sleep = previous_duty.release_time_utc + timedelta(minutes=30)
            else:
                earliest_sleep = duty.report_time_utc - timedelta(hours=8)
            
            latest_sleep = duty.report_time_utc - timedelta(minutes=30)
            time_available = (latest_sleep - earliest_sleep).total_seconds() / 3600
            
            if time_available >= 2:
                adjusted_start = earliest_sleep
                adjusted_end = latest_sleep
                warnings.append("WARNING: Sleep severely constrained by duty schedule")
            elif time_available >= 1:
                adjusted_start = earliest_sleep
                adjusted_end = latest_sleep
                warnings.append("CRITICAL: Less than 2h rest between duties")
            else:
                adjusted_end = duty.report_time_utc - timedelta(minutes=30)
                adjusted_start = adjusted_end - timedelta(hours=1)
                warnings.append("CRITICAL: Insufficient rest period - regulatory violation likely")
        
        return adjusted_start, adjusted_end, warnings
    
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
# EASA COMPLIANCE VALIDATION
# ============================================================================

class EASAComplianceValidator:
    """Validate duties against EASA FTL regulations"""
    
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
    
    def is_disruptive_duty(self, duty: Duty) -> Dict[str, any]:
        """Check if duty qualifies as disruptive per EASA GM1 ORO.FTL.235"""
        wocl_encroachment = self.calculate_wocl_encroachment(
            duty.report_time_utc, duty.release_time_utc, duty.home_base_timezone
        )
        wocl_hours = wocl_encroachment.total_seconds() / 3600
        
        return {
            'wocl_encroachment': wocl_hours > 0,
            'wocl_hours': wocl_hours,
            'early_start': duty.report_time_local.hour < self.framework.early_start_threshold_hour,
            'late_finish': self.framework.late_finish_threshold_hour <= duty.release_time_local.hour < self.framework.local_night_end_hour,
            'is_disruptive': (
                wocl_hours > 0 or
                duty.report_time_local.hour < self.framework.early_start_threshold_hour or
                (self.framework.late_finish_threshold_hour <= duty.release_time_local.hour < self.framework.local_night_end_hour)
            )
        }


# ============================================================================
# WORKLOAD INTEGRATION
# ============================================================================

@dataclass
class WorkloadParameters:
    """
    Workload multipliers derived from aviation research
    References: Bourgeois-Bougrine et al. (2003), Cabon et al. (1993), Gander et al. (1994)
    """
    
    WORKLOAD_MULTIPLIERS: Dict[FlightPhase, float] = field(default_factory=lambda: {
        FlightPhase.PREFLIGHT: 1.1,
        FlightPhase.TAXI_OUT: 1.0,
        FlightPhase.TAKEOFF: 1.8,
        FlightPhase.CLIMB: 1.3,
        FlightPhase.CRUISE: 0.8,
        FlightPhase.DESCENT: 1.2,
        FlightPhase.APPROACH: 1.5,
        FlightPhase.LANDING: 2.0,
        FlightPhase.TAXI_IN: 1.0,
        FlightPhase.GROUND_TURNAROUND: 1.2,
    })
    
    SECTOR_PENALTY_RATE: float = 0.15  # 15% per additional sector
    RECOVERY_THRESHOLD_HOURS: float = 2.0
    TURNAROUND_RECOVERY_RATE: float = 0.3


class WorkloadModel:
    """Integrates aviation workload into fatigue model"""
    
    def __init__(self, params: WorkloadParameters = None):
        self.params = params or WorkloadParameters()
    
    def get_phase_multiplier(self, phase: FlightPhase) -> float:
        return self.params.WORKLOAD_MULTIPLIERS.get(phase, 1.0)
    
    def get_sector_multiplier(self, sector_number: int) -> float:
        return 1.0 + (sector_number - 1) * self.params.SECTOR_PENALTY_RATE
    
    def get_combined_multiplier(self, phase: FlightPhase, sector_number: int) -> float:
        return self.get_phase_multiplier(phase) * self.get_sector_multiplier(sector_number)


# ============================================================================
# MAIN BORBÉLY FATIGUE MODEL
# ============================================================================

class BorbelyFatigueModel:
    """
    Unified Biomathematical Fatigue Prediction Engine
    
    Combines:
    - Borbély two-process model (homeostatic + circadian)
    - Sleep debt vulnerability amplification
    - Sleep inertia effects
    - Dynamic circadian adaptation
    - Aviation workload integration
    """
    
    def __init__(self, config: ModelConfig = None):
        self.config = config or ModelConfig.default_easa_config()
        self.params = self.config.borbely_params
        self.adaptation_rates = self.config.adaptation_rates
        
        # Initialize subsystems
        self.sleep_calculator = UnifiedSleepCalculator(self.config)
        self.validator = EASAComplianceValidator(self.config.easa_framework)
        self.workload_model = WorkloadModel()
        
        # Model parameters
        self.s_upper = self.params.S_max
        self.s_lower = self.params.S_min + 0.1
        self.tau_i = self.params.tau_i
        self.tau_d = self.params.tau_d
        
        # Circadian parameters — operational adjustments:
        # Amplitude +0.05 increases circadian modulation for aviation context
        # (higher sensitivity to WOCL performance dips).
        # Peak shifted from configured 17:00 to 16:00 to reflect that pilot
        # duty performance peaks tend slightly earlier than CBT acrophase
        # (~17:00-19:00, Wright et al. 2002 Am J Physiol 283:R1370).
        # Note: this is an operational choice, not a literature-derived value.
        self.c_amplitude = self.params.circadian_amplitude + 0.05
        self.c_peak_hour = self.params.circadian_acrophase_hours - 1.0
        
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
        """Process S: Homeostatic sleep pressure buildup"""
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
        """Process C: Circadian alertness rhythm"""
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
        """Process W: Sleep inertia (grogginess after waking)"""
        minutes_awake = time_since_wake.total_seconds() / 60
        
        if minutes_awake > self.params.inertia_duration_minutes:
            return 0.0
        
        inertia = self.params.inertia_max_magnitude * math.exp(
            -minutes_awake / (self.params.inertia_duration_minutes / 3)
        )
        
        return inertia
    
    def integrate_s_and_c_multiplicative(self, s: float, c: float) -> float:
        """Weighted average integration of S and C"""
        s_alertness = 1.0 - s
        c_alertness = (c + 1.0) / 2.0
        base_alertness = s_alertness * 0.6 + c_alertness * 0.4
        return base_alertness
    
    def integrate_performance(self, c: float, s: float, w: float) -> float:
        """
        Integrate three processes into performance (0-100 scale)

        Inspired by Åkerstedt & Folkard (1997) three-process model and
        Dawson & Reid (1997) performance equivalence framework. The
        weighted-average integration (60/40 S/C) is an operational
        adaptation — the original models use additive combination.
        """
        # Input validation with graceful clamping
        c = max(0.0, min(1.0, c))
        s = max(0.0, min(1.0, s))
        w = max(0.0, min(1.0, w))
        
        c_phase = (c * 2.0) - 1.0
        base_alertness = self.integrate_s_and_c_multiplicative(s, c_phase)
        alertness_with_tot = base_alertness * (1.0 - w)
        
        # Performance floor of 20 (severe impairment, ~0.05% BAC equivalent)
        MIN_PERFORMANCE_FLOOR = 20.0
        performance = MIN_PERFORMANCE_FLOOR + (alertness_with_tot * (100.0 - MIN_PERFORMANCE_FLOOR))
        performance = max(MIN_PERFORMANCE_FLOOR, min(100.0, performance))
        
        return performance
    
    # ========================================================================
    # FLIGHT PHASES
    # ========================================================================
    
    def get_flight_phase(self, segments: List[FlightSegment], current_time: datetime) -> FlightPhase:
        """Determine flight phase from segment schedule"""
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
        """Build duty timeline with summary statistics"""
        
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
        """Detect high-risk moments (high S + low C during critical phases)"""
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
        
        # Initialize circadian tracking
        body_clock = CircadianState(
            current_phase_shift_hours=0.0,
            last_update_utc=roster.duties[0].report_time_utc - timedelta(days=1),
            reference_timezone=roster.home_base_timezone
        )
        
        body_clock_timeline = [(body_clock.last_update_utc, body_clock)]
        
        # Track circadian adaptation across duties
        for duty in roster.duties:
            departure_tz = duty.segments[0].departure_airport.timezone
            body_clock = self.calculate_adaptation(
                duty.report_time_utc, body_clock, departure_tz, roster.home_base_timezone
            )
            body_clock_timeline.append((duty.report_time_utc, body_clock))
        
        # Extract all sleep opportunities
        all_sleep, sleep_strategies = self._extract_sleep_from_roster(roster, body_clock_timeline)
        self.sleep_strategies = sleep_strategies
        
        previous_duty = None
        previous_timeline = None
        
        # Simulate each duty
        for i, duty in enumerate(roster.duties):
            phase_shift = self._get_phase_shift_at_time(duty.report_time_utc, body_clock_timeline)
            
            # Get relevant sleep (last 48h)
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
            
            # Calculate EASA FDP limits
            fdp_limits = self.validator.calculate_fdp_limits(duty)
            duty.max_fdp_hours = fdp_limits['max_fdp']
            duty.extended_fdp_hours = fdp_limits['extended_fdp']
            duty.used_discretion = fdp_limits['used_discretion']
            
            # Track cumulative sleep debt
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
            
            # Attach sleep strategy data
            if duty.duty_id in sleep_strategies:
                strategy_data = sleep_strategies[duty.duty_id]
                timeline_obj.sleep_strategy_type = strategy_data.get('strategy_type')
                timeline_obj.sleep_confidence = strategy_data.get('confidence')
                timeline_obj.sleep_quality_data = strategy_data
            
            # Update current S for next iteration
            if timeline_obj.timeline:
                current_s = timeline_obj.timeline[-1].homeostatic_component
            
            duty_timelines.append(timeline_obj)
            previous_duty = duty
        
        return self._build_monthly_analysis(roster, duty_timelines)
    
    def _extract_sleep_from_roster(
        self,
        roster: Roster,
        body_clock_timeline: List[Tuple[datetime, CircadianState]]
    ) -> Tuple[List[SleepBlock], Dict[str, Any]]:
        """Auto-generate sleep opportunities from duty gaps"""
        sleep_blocks = []
        sleep_strategies = {}
        home_tz = pytz.timezone(roster.home_base_timezone)
        
        for i, duty in enumerate(roster.duties):
            previous_duty = roster.duties[i - 1] if i > 0 else None
            
            # Use unified sleep calculator
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
                    'sleep_blocks': sleep_blocks_response,

                    # Scientific methodology (surfaces to frontend)
                    'explanation': strategy.explanation,
                    'confidence_basis': self._get_confidence_basis(strategy),
                    'quality_factors': {
                        'base_efficiency': quality.base_efficiency,
                        'wocl_boost': quality.wocl_penalty,  # renamed field, was 1.0 placeholder
                        'late_onset_penalty': quality.late_onset_penalty,
                        'recovery_boost': quality.recovery_boost,
                        'time_pressure_factor': quality.time_pressure_factor,
                        'insufficient_penalty': quality.insufficient_penalty,
                    },
                    'references': self._get_strategy_references(strategy.strategy_type),
                }
            
            # Generate rest day sleep for gaps between duties
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
                        }],
                        'explanation': 'Rest day: standard home sleep (23:00-07:00, 95% efficiency)',
                        'confidence_basis': 'High confidence — home environment, no duty constraints',
                        'quality_factors': {
                            'base_efficiency': 0.90,
                            'wocl_boost': 1.0,
                            'late_onset_penalty': 1.0,
                            'recovery_boost': 1.0,
                            'time_pressure_factor': 1.03,
                            'insufficient_penalty': 1.0,
                        },
                        'references': self._get_strategy_references('recovery'),
                    }
        
        return sleep_blocks, sleep_strategies

    @staticmethod
    def _get_confidence_basis(strategy: SleepStrategy) -> str:
        """Human-readable explanation of confidence value for frontend display."""
        st = strategy.strategy_type
        c = strategy.confidence

        if st == 'normal':
            if c >= 0.90:
                return 'High confidence — standard night sleep with short pre-duty wake period'
            elif c >= 0.80:
                return 'Good confidence — normal sleep pattern, moderate wake period before duty'
            else:
                return 'Moderate confidence — long wake period before duty increases uncertainty'
        elif st == 'early_bedtime':
            return (
                f'Moderate confidence ({c:.0%}) — pilots cannot fully advance bedtime '
                'for early reports due to circadian wake maintenance zone '
                '(Roach et al. 2012, Arsintescu et al. 2022)'
            )
        elif st == 'afternoon_nap':
            return (
                f'Moderate confidence ({c:.0%}) — Signal et al. (2014) found only '
                '54% of crew nap before evening departures; nap timing and '
                'duration vary between individuals'
            )
        elif st == 'split_sleep':
            return (
                f'Lower confidence ({c:.0%}) — anchor sleep concept validated '
                'in laboratory (Minors & Waterhouse 1983) but limited field '
                'data on pilot adoption of this specific pattern'
            )
        elif st == 'recovery':
            return 'High confidence — home environment, no duty constraints'
        return f'Confidence: {c:.0%}'

    @staticmethod
    def _get_strategy_references(strategy_type: str) -> list:
        """Return peer-reviewed references supporting this sleep strategy."""

        common = [
            {
                'key': 'borbely_1982',
                'short': 'Borbely (1982)',
                'full': 'Borbely AA. A two process model of sleep regulation. Hum Neurobiol 1:195-204',
            },
        ]

        strategy_refs = {
            'normal': [
                {
                    'key': 'signal_2009',
                    'short': 'Signal et al. (2009)',
                    'full': 'Signal TL et al. Flight crew sleep during multi-sector operations. J Sleep Res',
                },
                {
                    'key': 'gander_2013',
                    'short': 'Gander et al. (2013)',
                    'full': 'Gander PH et al. In-flight sleep, pilot fatigue and PVT. J Sleep Res 22(6):697-706',
                },
            ],
            'early_bedtime': [
                {
                    'key': 'roach_2012',
                    'short': 'Roach et al. (2012)',
                    'full': 'Roach GD et al. Duty periods with early start times restrict sleep. Accid Anal Prev 45 Suppl:22-26',
                },
                {
                    'key': 'arsintescu_2022',
                    'short': 'Arsintescu et al. (2022)',
                    'full': 'Arsintescu L et al. Early starts and late finishes reduce alertness. J Sleep Res 31(3):e13521',
                },
            ],
            'afternoon_nap': [
                {
                    'key': 'signal_2014',
                    'short': 'Signal et al. (2014)',
                    'full': 'Signal TL et al. Mitigating flight crew fatigue on ULR flights. Aviat Space Environ Med 85:1199-1208',
                },
                {
                    'key': 'gander_2014',
                    'short': 'Gander et al. (2014)',
                    'full': 'Gander PH et al. Pilot fatigue: departure/arrival times. Aviat Space Environ Med 85(8):833-40',
                },
                {
                    'key': 'dinges_1987',
                    'short': 'Dinges et al. (1987)',
                    'full': 'Dinges DF et al. Temporal placement of a nap for alertness. Sleep 10(4):313-329',
                },
            ],
            'split_sleep': [
                {
                    'key': 'minors_1983',
                    'short': 'Minors & Waterhouse (1983)',
                    'full': 'Minors DS, Waterhouse JM. Does anchor sleep entrain circadian rhythms? J Physiol 345:1-11',
                },
                {
                    'key': 'minors_1981',
                    'short': 'Minors & Waterhouse (1981)',
                    'full': 'Minors DS, Waterhouse JM. Anchor sleep as a synchronizer. Int J Chronobiol 8:165-88',
                },
            ],
            'recovery': [
                {
                    'key': 'gander_2014',
                    'short': 'Gander et al. (2014)',
                    'full': 'Gander PH et al. Pilot fatigue: departure/arrival times. Aviat Space Environ Med 85(8):833-40',
                },
            ],
        }

        return common + strategy_refs.get(strategy_type, [])

    def _get_phase_shift_at_time(
        self,
        target_time: datetime,
        body_clock_timeline: List[Tuple[datetime, CircadianState]]
    ) -> float:
        """Get circadian phase shift at specific time"""
        for timestamp, state in reversed(body_clock_timeline):
            if timestamp <= target_time:
                return state.current_phase_shift_hours
        return 0.0
    
    def _build_monthly_analysis(self, roster: Roster, duty_timelines: List[DutyTimeline]) -> MonthlyAnalysis:
        """Build monthly summary with aggregate statistics"""
        
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
    
    # Sleep Calculation
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
