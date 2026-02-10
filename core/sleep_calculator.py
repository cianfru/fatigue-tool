"""
Sleep Calculation Engine
=======================

Unified sleep estimation for airline pilots with quality analysis.

References: Signal et al. (2009), Gander et al. (2013), Roach et al. (2012)
"""

from datetime import datetime, timedelta, time
from typing import List, Tuple, Optional, Dict, Any
from dataclasses import dataclass
import math
import pytz
import logging

logger = logging.getLogger(__name__)

# Import data models
from models.data_models import (
    Duty, Roster, FlightSegment, SleepBlock, CircadianState,
    PerformancePoint, PinchEvent, DutyTimeline, MonthlyAnalysis, FlightPhase
)
from core.parameters import ModelConfig


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
        
        # Minimum pre-duty preparation buffer (hours).
        # Conservative estimate: pilots need time for commute, briefing,
        # personal preparation.  1 h was unrealistic for early-morning
        # starts; 2 h gives a more representative wakefulness-at-report.
        self.MIN_WAKE_BEFORE_REPORT = 2.0

        # Operational thresholds
        self.NIGHT_FLIGHT_THRESHOLD = 20  # EASA late-type duty
        self.EARLY_REPORT_THRESHOLD = 6   # Before 06:00 local → early_bedtime
        self.AFTERNOON_REPORT_THRESHOLD = 14  # After 14:00 local → afternoon_nap
        self.ANCHOR_TIMEZONE_SHIFT = 3.0  # ≥3h timezone crossing → anchor strategy
        self.RESTRICTED_REST_HOURS = 9.0  # <9h rest → restricted strategy
        self.SPLIT_REST_HOURS = 10.0      # <10h rest → split strategy
        self.EXTENDED_REST_HOURS = 14.0   # >14h rest → extended strategy
        
        # WOCL definition — aligned with EASAFatigueFramework (02:00-05:59)
        # per EASA ORO.FTL.105(28). Using 6.0 as float boundary so that
        # hour < 6.0 covers 02:00-05:59 correctly in overlap calculations.
        self.WOCL_START = self.config.easa_framework.wocl_start_hour  # 2
        self.WOCL_END = self.config.easa_framework.wocl_end_hour + 1  # 6 (exclusive upper bound)
        
        # Base efficiency by location — aligned with SleepQualityParameters.
        # Values updated per Signal et al. (2013) PSG data and sleep research.
        # These represent sleep quality multipliers, not TST/TIB ratios.
        self.LOCATION_EFFICIENCY = {
            'home': 0.95,            # Near-optimal: Åkerstedt (2003), Van Dongen (2003)
            'hotel': 0.88,           # Signal et al. (2013) PSG: 88% measured
            'crew_rest': 0.70,       # Signal et al. (2013) PSG: 70% inflight bunk
            'airport_hotel': 0.85,   # Slightly below regular hotel due to noise
            'crew_house': 0.90       # Similar to home environment
        }
        
        # Biological limits
        self.MAX_REALISTIC_SLEEP = 10.0
        self.MIN_SLEEP_FOR_QUALITY = 6.0
        
        self.home_tz = None
        self.home_base = None

    def _detect_layover(
        self,
        duty: Duty,
        previous_duty: Optional[Duty],
        home_base: str
    ) -> Tuple[bool, Optional[str], str]:
        """
        Detect if pilot is at a layover location vs. home base

        Returns:
            (is_layover, layover_timezone, environment)
            - is_layover: True if pilot slept at layover location
            - layover_timezone: Timezone of layover location (None if at home)
            - environment: 'hotel' if layover, 'home' if at home base
        """
        if not previous_duty or not previous_duty.segments:
            return False, None, 'home'

        # Where did previous duty end?
        prev_arrival = previous_duty.segments[-1].arrival_airport

        # Where does current duty start?
        curr_departure = duty.segments[0].departure_airport

        # Check if pilot is at layover:
        # 1. Previous duty ended at location X
        # 2. Current duty starts at same location X
        # 3. Location X is NOT the home base
        if (prev_arrival.code == curr_departure.code and
            prev_arrival.code != home_base):
            # LAYOVER SCENARIO
            return True, prev_arrival.timezone, 'hotel'

        return False, None, 'home'

    def estimate_sleep_for_duty(
        self,
        duty: Duty,
        previous_duty: Optional[Duty] = None,
        home_timezone: str = 'UTC',
        home_base: Optional[str] = None
    ) -> SleepStrategy:
        """
        Main entry point: Estimate how pilot actually slept before duty

        Args:
            duty: Current duty to estimate sleep for
            previous_duty: Previous duty (for layover detection)
            home_timezone: Pilot's home base timezone
            home_base: Pilot's home base airport code (e.g., 'DOH')
        """

        self.home_tz = pytz.timezone(home_timezone)
        # Use provided home_base, or infer from first departure if not provided
        self.home_base = home_base or (duty.segments[0].departure_airport.code if duty.segments else None)

        # Detect layover scenario
        is_layover, layover_tz, sleep_env = self._detect_layover(
            duty, previous_duty, self.home_base
        )

        # Store layover info for strategy methods to use
        self.is_layover = is_layover
        self.layover_timezone = layover_tz
        self.sleep_environment = sleep_env

        # Use layover timezone for strategy selection when pilot is at layover.
        # The pilot's sleep behavior is governed by local clock time where they
        # physically are, not their home base timezone. A 05:00 home-time report
        # might be 08:00 local at the layover — completely different strategy.
        if is_layover and layover_tz:
            strategy_tz = pytz.timezone(layover_tz)
        else:
            strategy_tz = self.home_tz
        report_local = duty.report_time_utc.astimezone(strategy_tz)
        report_hour = report_local.hour

        # Calculate duty characteristics
        duty_duration = (duty.release_time_utc - duty.report_time_utc).total_seconds() / 3600
        crosses_wocl = self._duty_crosses_wocl(duty)

        # Calculate rest period before this duty
        rest_hours = None
        if previous_duty:
            rest_hours = (duty.report_time_utc - previous_duty.release_time_utc).total_seconds() / 3600

        # Calculate timezone crossing from home base
        timezone_shift = 0.0
        if duty.segments:
            dep_airport = duty.segments[0].departure_airport
            home_airport_tz = pytz.timezone(duty.home_base_timezone)
            dep_tz = pytz.timezone(dep_airport.timezone)
            # Correctly convert UTC time to each timezone to get the offset
            home_offset = duty.report_time_utc.astimezone(home_airport_tz).utcoffset().total_seconds() / 3600
            dep_offset = duty.report_time_utc.astimezone(dep_tz).utcoffset().total_seconds() / 3600
            timezone_shift = abs(dep_offset - home_offset)

        # Decision tree: match pilot behavior patterns
        # Priority order: most constrained/specific scenarios first.

        # 1. Anchor sleep — large timezone shift from home base (≥3h).
        #    Pilot's circadian clock is misaligned; maintain home-base
        #    sleep window to preserve circadian anchor.
        if timezone_shift >= self.ANCHOR_TIMEZONE_SHIFT:
            return self._anchor_strategy(duty, previous_duty, timezone_shift)

        # 2. Restricted sleep — very short rest (<9h) forces truncated sleep.
        #    Takes priority because the rest period physically constrains
        #    available sleep regardless of report time.
        if rest_hours is not None and rest_hours < self.RESTRICTED_REST_HOURS:
            return self._restricted_strategy(duty, previous_duty, rest_hours)

        # 3. Split sleep — short layover (<10h) where one consolidated
        #    block is impossible. Pilot splits sleep around the gap.
        if rest_hours is not None and rest_hours < self.SPLIT_REST_HOURS:
            return self._split_strategy(duty, previous_duty, rest_hours)

        # 4. Early bedtime — report before 06:00 local.
        #    Pilot goes to bed earlier; circadian opposition limits advance.
        if report_hour < self.EARLY_REPORT_THRESHOLD:
            return self._early_morning_strategy(duty, previous_duty)

        # 5. Nap — night departure (report ≥20:00 or <04:00).
        #    Morning sleep + pre-duty nap before evening/night flight.
        if report_hour >= self.NIGHT_FLIGHT_THRESHOLD or report_hour < 4:
            return self._night_departure_strategy(duty, previous_duty)

        # 6. Afternoon nap — late report (14:00-20:00 local).
        #    Normal previous-night sleep + afternoon nap before duty.
        if report_hour >= self.AFTERNOON_REPORT_THRESHOLD:
            return self._afternoon_nap_strategy(duty, previous_duty)

        # 7. Extended sleep — long rest period (>14h) allows extra sleep.
        if rest_hours is not None and rest_hours > self.EXTENDED_REST_HOURS:
            return self._extended_strategy(duty, previous_duty, rest_hours)

        # 8. WOCL duty — crosses Window of Circadian Low with long duty.
        if crosses_wocl and duty_duration > 6:
            return self._wocl_duty_strategy(duty, previous_duty)

        # 9. Normal — standard overnight rest, no special constraints.
        return self._normal_sleep_strategy(duty, previous_duty)
    
    def calculate_sleep_quality(
        self,
        sleep_start: datetime,
        sleep_end: datetime,
        location: str,
        previous_duty_end: Optional[datetime],
        next_event: datetime,
        is_nap: bool = False,
        location_timezone: str = 'UTC',
        biological_timezone: str = None
    ) -> SleepQualityAnalysis:
        """Calculate realistic sleep quality with all factors.

        Args:
            biological_timezone: The timezone representing the pilot's current
                circadian phase.  For home-base sleep this equals
                ``location_timezone``; for layovers it is the home-base TZ
                (short layovers) or partially adapted TZ (longer layovers).
                When ``None``, defaults to ``location_timezone``.
        """
        
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
        
        # 4. Circadian alignment factor
        # Dijk & Czeisler (1995) J Neurosci 15:3526 showed that SWA is
        # primarily homeostatic — circadian modulation of SWS amplitude
        # is low.  However, sleep *consolidation* (fewer awakenings,
        # higher efficiency) is strongly circadian: sleep efficiency is
        # ~95 % during the biological night vs ~80-85 % during circadian
        # day (Dijk & Czeisler 1994, J Neurosci 14:3522).
        #
        # The base LOCATION_EFFICIENCY values already assume normal
        # night-time sleep; adding a boost on top would double-count.
        # Instead, we apply a PENALTY when sleep falls outside the
        # biological night (WOCL window), reflecting reduced consolidation.
        #
        # Penalty: up to 8% for fully daytime sleep (0 h WOCL overlap).
        # WOCL window is ~6 h; full overlap → no penalty (1.0).
        # Reduced from 15% based on research: circadian affects sleep consolidation
        # and onset, but quality per hour slept remains stable (Dijk & Czeisler 1995).
        wocl_overlap = self._calculate_wocl_overlap(sleep_start, sleep_end, location_timezone, biological_timezone)
        wocl_window_hours = float(self.WOCL_END - self.WOCL_START)
        # Fraction of sleep that aligns with WOCL (0 = fully daytime, 1 = fully nighttime)
        alignment_ratio = min(1.0, wocl_overlap / max(1.0, min(actual_duration, wocl_window_hours)))
        # Max 8% penalty for fully misaligned sleep (reduced from 15%)
        wocl_boost = 1.0 - 0.08 * (1.0 - alignment_ratio) if actual_duration > 0.5 else 1.0
        
        # 5. Late sleep onset penalty
        # Evaluate against the biological clock — during layovers the pilot's
        # circadian wake-maintenance zone (WMZ, ~18:00-21:00 biological time)
        # is the hardest window to fall asleep in, regardless of local time.
        # Dijk & Czeisler (1995): sleep latency is maximal in the 2-3 h
        # preceding the temperature minimum's mirror (the evening WMZ).
        tz = pytz.timezone(location_timezone)
        bio_tz_for_onset = pytz.timezone(biological_timezone) if biological_timezone else tz
        sleep_start_bio_local = sleep_start.astimezone(bio_tz_for_onset)
        sleep_start_hour = sleep_start_bio_local.hour + sleep_start_bio_local.minute / 60.0

        if sleep_start_hour >= 1 and sleep_start_hour < 4:
            late_onset_penalty = 0.93
        elif sleep_start_hour >= 0 and sleep_start_hour < 1:
            late_onset_penalty = 0.97
        else:
            late_onset_penalty = 1.0

        # Additional penalty for attempting sleep during the circadian
        # wake-maintenance zone (WMZ, ~17:00-21:00 biological time).
        # This is the hardest time to fall asleep — the SCN is actively
        # promoting wakefulness. Sleep onset latency roughly doubles,
        # and sleep efficiency drops ~5-10% (Dijk & Czeisler 1994;
        # Strogatz et al. 1987).
        if 17 <= sleep_start_hour < 21:
            # Peak difficulty at ~19:00 biological time
            wmz_center = 19.0
            wmz_distance = abs(sleep_start_hour - wmz_center) / 2.0
            wmz_penalty = 0.93 + 0.07 * min(1.0, wmz_distance)  # 0.93-1.0
            late_onset_penalty = min(late_onset_penalty, wmz_penalty)
        
        # 6. Recovery sleep boost — graded by recency of duty.
        # Post-duty sleep with high homeostatic drive shows enhanced SWA
        # rebound (Borbély 1982) and shorter onset latency. The effect
        # is graded, not binary: strongest immediately post-duty,
        # diminishing as the interval grows. Capped at 5 % to avoid
        # inflating combined efficiency above 1.0 after multiplication.
        # Reference: Borbély (1982) Human Neurobiol 1:195-204
        if previous_duty_end:
            hours_since_duty = (sleep_start - previous_duty_end).total_seconds() / 3600
            if hours_since_duty < 2 and not is_nap:
                recovery_boost = 1.05
            elif hours_since_duty < 4 and not is_nap:
                recovery_boost = 1.03
            else:
                recovery_boost = 1.0
        else:
            recovery_boost = 1.0
            hours_since_duty = None
        
        # 7. Time pressure factor — penalties only
        # Anticipatory stress affects sleep onset latency and may cause
        # awakenings, but quality per hour of sleep obtained remains stable.
        # Kecklund & Åkerstedt (2004) J Sleep Res 13:1-6 documented reduced
        # sleep before early shifts, but effect is on duration, not quality.
        # Reduced penalties to avoid double-counting with duration effects.
        hours_until_duty = (next_event - sleep_end).total_seconds() / 3600

        if hours_until_duty < 1.5:
            time_pressure_factor = 0.93  # 7% penalty (was 12%)
        elif hours_until_duty < 3:
            time_pressure_factor = 0.96  # 4% penalty (was 7%)
        elif hours_until_duty < 6:
            time_pressure_factor = 0.98  # 2% penalty (was 3%)
        else:
            time_pressure_factor = 1.0
        
        # 8. Insufficient sleep penalty — REMOVED
        # Research (Belenky et al. 2003, Van Dongen et al. 2003) shows that
        # sleep quality per hour remains stable even during restriction.
        # Short sleep is already penalized by duration; applying efficiency
        # penalty double-counts the effect. Quality per hour slept is consistent.
        insufficient_penalty = 1.0  # No penalty - removed to avoid double-counting
        
        # 9. Combine all factors
        combined_efficiency = (
            base_efficiency
            * wocl_boost
            * late_onset_penalty
            * recovery_boost
            * time_pressure_factor
            * insufficient_penalty
        )
        combined_efficiency = max(0.70, min(1.0, combined_efficiency))  # Raised floor from 0.65 to 0.70
        
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
            wocl_penalty=wocl_boost,  # circadian alignment factor (0.85-1.0)
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
        location_timezone: str = 'UTC',
        biological_timezone: str = None
    ) -> float:
        """
        Calculate hours of sleep overlapping WOCL (02:00-06:00)

        The WOCL window is evaluated in the pilot's **biological timezone**
        (home-base clock adjusted for circadian adaptation), not the local
        timezone of the sleep location.  For short layovers (< 48 h) the
        circadian clock remains essentially on home time (SKYbrary; EASA
        AMC1 ORO.FTL.105).  ``biological_timezone`` defaults to
        ``location_timezone`` when the pilot is at home base (no shift).

        References:
            Dijk & Czeisler (1995) J Neurosci 15:3526 — circadian gating
            Roach et al. (2025) PMC11879054 — layover start time predicts sleep
        """

        # Use biological (home-base) timezone for WOCL evaluation when provided,
        # falling back to location timezone (correct when pilot is at home base).
        wocl_tz_str = biological_timezone or location_timezone
        wocl_tz = pytz.timezone(wocl_tz_str)

        # Sleep times are still converted to local timezone for onset/offset
        # calculations (the pilot physically sleeps in the local timezone),
        # but the *WOCL window* is anchored to the biological clock.
        tz = pytz.timezone(location_timezone)
        sleep_start_local = sleep_start.astimezone(tz)
        sleep_end_local = sleep_end.astimezone(tz)

        # Compute the WOCL window boundaries in UTC using the biological TZ,
        # then compare against sleep times in UTC for accurate overlap.
        sleep_start_bio = sleep_start.astimezone(wocl_tz)
        sleep_end_bio = sleep_end.astimezone(wocl_tz)
        
        # Use biological-clock hours for WOCL overlap evaluation.
        # The WOCL (02:00-06:00) is defined relative to the pilot's adapted
        # circadian rhythm, which during short layovers remains on home time.
        sleep_start_hour = sleep_start_bio.hour + sleep_start_bio.minute / 60.0
        sleep_end_hour = sleep_end_bio.hour + sleep_end_bio.minute / 60.0

        overlap_hours = 0.0

        # Handle overnight sleep (crosses midnight in biological TZ)
        if sleep_end_hour < sleep_start_hour or sleep_end_bio.date() > sleep_start_bio.date():
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
            # Same-day sleep (in biological TZ)
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

        NEW: Detects layover scenarios and calculates sleep at layover location.
        """

        # Determine sleep location timezone
        if self.is_layover and self.layover_timezone:
            sleep_tz = pytz.timezone(self.layover_timezone)
            sleep_location = self.sleep_environment  # 'hotel'
        else:
            sleep_tz = self.home_tz
            sleep_location = 'home'

        report_local = duty.report_time_utc.astimezone(sleep_tz)

        # Morning sleep (23:00-07:00, standard 8h window)
        morning_sleep_start = report_local.replace(hour=self.NORMAL_BEDTIME_HOUR, minute=0) - timedelta(days=1)
        morning_sleep_end = report_local.replace(hour=7, minute=0)

        morning_sleep_start_utc, morning_sleep_end_utc, morning_warnings = self._validate_sleep_no_overlap(
            morning_sleep_start.astimezone(pytz.utc), morning_sleep_end.astimezone(pytz.utc), duty, previous_duty
        )
        morning_sleep_start = morning_sleep_start_utc.astimezone(sleep_tz)
        morning_sleep_end = morning_sleep_end_utc.astimezone(sleep_tz)

        # Use home-base TZ as biological clock reference during layovers.
        # For short layovers (< 48 h) the circadian clock does not adapt
        # to local time (SKYbrary; EASA AMC1 ORO.FTL.105).
        bio_tz = self.home_tz.zone if self.is_layover else None

        morning_quality = self.calculate_sleep_quality(
            sleep_start=morning_sleep_start,
            sleep_end=morning_sleep_end,
            location=sleep_location,  # 'home' or 'hotel'
            previous_duty_end=previous_duty.release_time_utc if previous_duty else None,
            next_event=report_local,
            location_timezone=sleep_tz.zone,
            biological_timezone=bio_tz
        )

        morning_sleep = SleepBlock(
            start_utc=morning_sleep_start.astimezone(pytz.utc),
            end_utc=morning_sleep_end.astimezone(pytz.utc),
            location_timezone=sleep_tz.zone,
            duration_hours=morning_quality.actual_sleep_hours,
            quality_factor=morning_quality.sleep_efficiency,
            effective_sleep_hours=morning_quality.effective_sleep_hours,
            environment=sleep_location,  # 'home' or 'hotel'
            sleep_start_day=morning_sleep_start.day,
            sleep_start_hour=morning_sleep_start.hour + morning_sleep_start.minute / 60.0,
            sleep_end_day=morning_sleep_end.day,
            sleep_end_hour=morning_sleep_end.hour + morning_sleep_end.minute / 60.0
        )

        # Pre-duty nap: 2h duration (Signal 2014 found typical naps 1-2h;
        # only 54% of crew napped, so confidence is reduced accordingly)
        nap_end = report_local - timedelta(hours=self.MIN_WAKE_BEFORE_REPORT)
        nap_start = nap_end - timedelta(hours=2.0)

        nap_start_utc, nap_end_utc, nap_warnings = self._validate_sleep_no_overlap(
            nap_start.astimezone(pytz.utc), nap_end.astimezone(pytz.utc), duty, previous_duty
        )
        nap_start = nap_start_utc.astimezone(sleep_tz)
        nap_end = nap_end_utc.astimezone(sleep_tz)

        nap_quality = self.calculate_sleep_quality(
            sleep_start=nap_start,
            sleep_end=nap_end,
            location=sleep_location,  # 'home' or 'hotel'
            previous_duty_end=morning_sleep_end.astimezone(pytz.utc),
            next_event=report_local,
            is_nap=True,
            location_timezone=sleep_tz.zone,
            biological_timezone=bio_tz
        )

        afternoon_nap = SleepBlock(
            start_utc=nap_start.astimezone(pytz.utc),
            end_utc=nap_end.astimezone(pytz.utc),
            location_timezone=sleep_tz.zone,
            duration_hours=nap_quality.actual_sleep_hours,
            quality_factor=nap_quality.sleep_efficiency,
            effective_sleep_hours=nap_quality.effective_sleep_hours,
            is_anchor_sleep=False,
            environment=sleep_location,  # 'home' or 'hotel'
            sleep_start_day=nap_start.day,
            sleep_start_hour=nap_start.hour + nap_start.minute / 60.0,
            sleep_end_day=nap_end.day,
            sleep_end_hour=nap_end.hour + nap_end.minute / 60.0
        )

        total_effective = morning_quality.effective_sleep_hours + nap_quality.effective_sleep_hours
        # Confidence lowered: Signal (2014) found only 54% of crew nap
        confidence = 0.60 if not (morning_warnings or nap_warnings) else 0.45

        # Lower confidence for layover sleep (more variability)
        if self.is_layover:
            confidence *= 0.90

        location_desc = f"{sleep_location} (layover)" if self.is_layover else sleep_location
        return SleepStrategy(
            strategy_type='nap',
            sleep_blocks=[morning_sleep, afternoon_nap],
            confidence=confidence,
            explanation=f"Night departure at {location_desc}: {morning_quality.actual_sleep_hours:.1f}h + "
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

        NEW: Detects layover scenarios and calculates sleep at layover location.
        """

        # Determine sleep location timezone
        if self.is_layover and self.layover_timezone:
            sleep_tz = pytz.timezone(self.layover_timezone)
            sleep_location = self.sleep_environment  # 'hotel'
        else:
            sleep_tz = self.home_tz
            sleep_location = 'home'

        report_local = duty.report_time_utc.astimezone(sleep_tz)

        # Roach et al. (2012): pilots lose ~15 min sleep per hour of duty
        # advance before 09:00. Baseline 6.6h at 09:00 report.
        # Formula: sleep_hours ≈ 6.6 - 0.25 * max(0, 9 - report_hour)
        report_hour = report_local.hour + report_local.minute / 60.0
        sleep_duration = max(4.0, 6.6 - 0.25 * max(0, 9.0 - report_hour))

        # Earliest realistic bedtime is ~21:30 (circadian opposition before this)
        # Arsintescu et al. (2022): pilots do not sufficiently advance bedtime
        wake_time = report_local - timedelta(hours=self.MIN_WAKE_BEFORE_REPORT)
        sleep_end = wake_time
        earliest_bedtime = report_local.replace(hour=21, minute=30) - timedelta(days=1)
        sleep_start = max(earliest_bedtime, sleep_end - timedelta(hours=sleep_duration))

        sleep_start_utc, sleep_end_utc, sleep_warnings = self._validate_sleep_no_overlap(
            sleep_start.astimezone(pytz.utc), sleep_end.astimezone(pytz.utc), duty, previous_duty
        )
        sleep_start = sleep_start_utc.astimezone(sleep_tz)
        sleep_end = sleep_end_utc.astimezone(sleep_tz)

        bio_tz = self.home_tz.zone if self.is_layover else None

        sleep_quality = self.calculate_sleep_quality(
            sleep_start=sleep_start,
            sleep_end=sleep_end,
            location=sleep_location,  # 'home' or 'hotel'
            previous_duty_end=previous_duty.release_time_utc if previous_duty else None,
            next_event=report_local,
            location_timezone=sleep_tz.zone,
            biological_timezone=bio_tz
        )

        early_sleep = SleepBlock(
            start_utc=sleep_start.astimezone(pytz.utc),
            end_utc=sleep_end.astimezone(pytz.utc),
            location_timezone=sleep_tz.zone,
            duration_hours=sleep_quality.actual_sleep_hours,
            quality_factor=sleep_quality.sleep_efficiency,
            effective_sleep_hours=sleep_quality.effective_sleep_hours,
            environment=sleep_location,  # 'home' or 'hotel'
            sleep_start_day=sleep_start.day,
            sleep_start_hour=sleep_start.hour + sleep_start.minute / 60.0,
            sleep_end_day=sleep_end.day,
            sleep_end_hour=sleep_end.hour + sleep_end.minute / 60.0
        )

        # Lower confidence reflects Roach (2012) finding of high variability
        # in early-start sleep; individual differences in circadian tolerance
        confidence = 0.55 if not sleep_warnings else 0.40

        # Lower confidence for layover sleep (more variability)
        if self.is_layover:
            confidence *= 0.90

        location_desc = f"{sleep_location} (layover)" if self.is_layover else sleep_location
        return SleepStrategy(
            strategy_type='early_bedtime',
            sleep_blocks=[early_sleep],
            confidence=confidence,
            explanation=f"Early report at {location_desc}: Constrained bedtime = {sleep_quality.effective_sleep_hours:.1f}h effective "
                       f"(Roach 2012 regression: {sleep_duration:.1f}h predicted)",
            quality_analysis=[sleep_quality]
        )
    
    def _wocl_duty_strategy(
        self,
        duty: Duty,
        previous_duty: Optional[Duty]
    ) -> SleepStrategy:
        """
        WOCL duty strategy: anchor sleep before duty

        NEW: Detects layover scenarios and calculates sleep at layover location.
        """

        # Determine sleep location timezone
        if self.is_layover and self.layover_timezone:
            sleep_tz = pytz.timezone(self.layover_timezone)
            sleep_location = self.sleep_environment  # 'hotel'
        else:
            sleep_tz = self.home_tz
            sleep_location = 'home'

        report_local = duty.report_time_utc.astimezone(sleep_tz)

        anchor_end = report_local - timedelta(hours=self.MIN_WAKE_BEFORE_REPORT)
        anchor_start = anchor_end - timedelta(hours=4.5)

        anchor_start_utc, anchor_end_utc, anchor_warnings = self._validate_sleep_no_overlap(
            anchor_start.astimezone(pytz.utc), anchor_end.astimezone(pytz.utc), duty, previous_duty
        )
        anchor_start = anchor_start_utc.astimezone(sleep_tz)
        anchor_end = anchor_end_utc.astimezone(sleep_tz)

        bio_tz = self.home_tz.zone if self.is_layover else None

        anchor_quality = self.calculate_sleep_quality(
            sleep_start=anchor_start,
            sleep_end=anchor_end,
            location=sleep_location,  # 'home' or 'hotel'
            previous_duty_end=previous_duty.release_time_utc if previous_duty else None,
            next_event=report_local,
            location_timezone=sleep_tz.zone,
            biological_timezone=bio_tz
        )

        anchor_sleep = SleepBlock(
            start_utc=anchor_start.astimezone(pytz.utc),
            end_utc=anchor_end.astimezone(pytz.utc),
            location_timezone=sleep_tz.zone,
            duration_hours=anchor_quality.actual_sleep_hours,
            quality_factor=anchor_quality.sleep_efficiency,
            effective_sleep_hours=anchor_quality.effective_sleep_hours,
            environment=sleep_location,  # 'home' or 'hotel'
            sleep_start_day=anchor_start.day,
            sleep_start_hour=anchor_start.hour + anchor_start.minute / 60.0,
            sleep_end_day=anchor_end.day,
            sleep_end_hour=anchor_end.hour + anchor_end.minute / 60.0
        )

        confidence = 0.50 if not anchor_warnings else 0.35

        # Lower confidence for layover sleep (more variability)
        if self.is_layover:
            confidence *= 0.90

        location_desc = f"{sleep_location} (layover)" if self.is_layover else sleep_location
        return SleepStrategy(
            strategy_type='split',
            sleep_blocks=[anchor_sleep],
            confidence=confidence,
            explanation=f"WOCL duty at {location_desc}: Split sleep = {anchor_quality.effective_sleep_hours:.1f}h effective",
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

        NEW: Detects layover scenarios and calculates sleep at layover location.
        """

        # Determine sleep location timezone
        if self.is_layover and self.layover_timezone:
            sleep_tz = pytz.timezone(self.layover_timezone)
            sleep_location = self.sleep_environment  # 'hotel'
        else:
            sleep_tz = self.home_tz
            sleep_location = 'home'

        # Use sleep location timezone for report time (where pilot wakes up)
        report_local = duty.report_time_utc.astimezone(sleep_tz)

        # All normal duties: sleep previous night, wake at normal time.
        # Ensure at least MIN_WAKE_BEFORE_REPORT hours before report —
        # if report is 07:30 and normal wake is 07:00, that's only 30 min
        # which is unrealistic for commute + briefing.
        normal_wake = report_local.replace(hour=self.NORMAL_WAKE_HOUR, minute=0)
        latest_wake = report_local - timedelta(hours=self.MIN_WAKE_BEFORE_REPORT)
        sleep_end = min(normal_wake, latest_wake)
        sleep_start = report_local.replace(hour=self.NORMAL_BEDTIME_HOUR, minute=0) - timedelta(days=1)

        sleep_start_utc, sleep_end_utc, sleep_warnings = self._validate_sleep_no_overlap(
            sleep_start.astimezone(pytz.utc), sleep_end.astimezone(pytz.utc), duty, previous_duty
        )
        sleep_start = sleep_start_utc.astimezone(sleep_tz)
        sleep_end = sleep_end_utc.astimezone(sleep_tz)

        bio_tz = self.home_tz.zone if self.is_layover else None

        sleep_quality = self.calculate_sleep_quality(
            sleep_start=sleep_start,
            sleep_end=sleep_end,
            location=sleep_location,  # 'home' or 'hotel'
            previous_duty_end=previous_duty.release_time_utc if previous_duty else None,
            next_event=report_local,
            location_timezone=sleep_tz.zone,
            biological_timezone=bio_tz
        )

        normal_sleep = SleepBlock(
            start_utc=sleep_start.astimezone(pytz.utc),
            end_utc=sleep_end.astimezone(pytz.utc),
            location_timezone=sleep_tz.zone,
            duration_hours=sleep_quality.actual_sleep_hours,
            quality_factor=sleep_quality.sleep_efficiency,
            effective_sleep_hours=sleep_quality.effective_sleep_hours,
            environment=sleep_location,  # 'home' or 'hotel'
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

        # Lower confidence for layover sleep (more variability)
        if self.is_layover:
            confidence *= 0.90

        location_desc = f"{sleep_location} (layover)" if self.is_layover else sleep_location
        return SleepStrategy(
            strategy_type='normal',
            sleep_blocks=[normal_sleep],
            confidence=confidence,
            explanation=f"Normal sleep at {location_desc} ({sleep_quality.effective_sleep_hours:.1f}h effective), {awake_hours:.1f}h awake before duty",
            quality_analysis=[sleep_quality]
        )
    
    def _anchor_strategy(
        self,
        duty: Duty,
        previous_duty: Optional[Duty],
        timezone_shift: float
    ) -> SleepStrategy:
        """
        Anchor sleep strategy: maintain home-base sleep window when crossing
        ≥3 timezones. The pilot's circadian clock has not adapted to local
        time, so sleep is anchored to the home-base biological night.

        References:
            Minors & Waterhouse (1981) Int J Chronobiol 8:165-88
            Minors & Waterhouse (1983) J Physiol 345:1-11
            Waterhouse et al. (2007) Aviat Space Environ Med 78(5):B1-B10
        """
        # Determine sleep location timezone
        if self.is_layover and self.layover_timezone:
            sleep_tz = pytz.timezone(self.layover_timezone)
            sleep_location = self.sleep_environment  # 'hotel'
        else:
            sleep_tz = self.home_tz
            sleep_location = 'home'

        # Anchor sleep to home-base biological night (23:00-07:00 home time)
        # expressed in local time at the sleep location.
        report_local = duty.report_time_utc.astimezone(sleep_tz)
        report_home = duty.report_time_utc.astimezone(self.home_tz)

        # Calculate home-base bedtime/wake in UTC, then convert to local
        home_bedtime = report_home.replace(hour=self.NORMAL_BEDTIME_HOUR, minute=0) - timedelta(days=1)
        home_wake = report_home.replace(hour=self.NORMAL_WAKE_HOUR, minute=0)

        # Ensure wake is before report
        if home_wake.astimezone(pytz.utc) > duty.report_time_utc - timedelta(hours=self.MIN_WAKE_BEFORE_REPORT):
            home_wake = (duty.report_time_utc - timedelta(hours=self.MIN_WAKE_BEFORE_REPORT)).astimezone(self.home_tz)

        sleep_start = home_bedtime.astimezone(sleep_tz)
        sleep_end = home_wake.astimezone(sleep_tz)

        sleep_start_utc, sleep_end_utc, sleep_warnings = self._validate_sleep_no_overlap(
            sleep_start.astimezone(pytz.utc), sleep_end.astimezone(pytz.utc), duty, previous_duty
        )
        sleep_start = sleep_start_utc.astimezone(sleep_tz)
        sleep_end = sleep_end_utc.astimezone(sleep_tz)

        bio_tz = self.home_tz.zone  # Always use home TZ as biological reference

        sleep_quality = self.calculate_sleep_quality(
            sleep_start=sleep_start,
            sleep_end=sleep_end,
            location=sleep_location,
            previous_duty_end=previous_duty.release_time_utc if previous_duty else None,
            next_event=report_local,
            location_timezone=sleep_tz.zone,
            biological_timezone=bio_tz
        )

        anchor_sleep = SleepBlock(
            start_utc=sleep_start.astimezone(pytz.utc),
            end_utc=sleep_end.astimezone(pytz.utc),
            location_timezone=sleep_tz.zone,
            duration_hours=sleep_quality.actual_sleep_hours,
            quality_factor=sleep_quality.sleep_efficiency,
            effective_sleep_hours=sleep_quality.effective_sleep_hours,
            environment=sleep_location,
            sleep_start_day=sleep_start.day,
            sleep_start_hour=sleep_start.hour + sleep_start.minute / 60.0,
            sleep_end_day=sleep_end.day,
            sleep_end_hour=sleep_end.hour + sleep_end.minute / 60.0
        )

        # Confidence decreases with larger timezone shifts (harder to anchor)
        if timezone_shift < 5:
            confidence = 0.55
        elif timezone_shift < 8:
            confidence = 0.45
        else:
            confidence = 0.35

        if sleep_warnings:
            confidence *= 0.80

        if self.is_layover:
            confidence *= 0.90

        location_desc = f"{sleep_location} (layover)" if self.is_layover else sleep_location
        return SleepStrategy(
            strategy_type='anchor',
            sleep_blocks=[anchor_sleep],
            confidence=confidence,
            explanation=(
                f"Anchor sleep at {location_desc}: {timezone_shift:.1f}h timezone shift, "
                f"maintaining home-base sleep window "
                f"({sleep_quality.effective_sleep_hours:.1f}h effective)"
            ),
            quality_analysis=[sleep_quality]
        )

    def _restricted_strategy(
        self,
        duty: Duty,
        previous_duty: Optional[Duty],
        rest_hours: float
    ) -> SleepStrategy:
        """
        Restricted sleep strategy: short rest period (<9h) forces truncated
        sleep. The pilot sleeps as soon as possible after previous duty
        release and wakes for the next report.

        References:
            Belenky et al. (2003) J Sleep Res 12:1-12
            Van Dongen et al. (2003) Sleep 26(2):117-126
        """
        if self.is_layover and self.layover_timezone:
            sleep_tz = pytz.timezone(self.layover_timezone)
            sleep_location = self.sleep_environment
        else:
            sleep_tz = self.home_tz
            sleep_location = 'home'

        report_local = duty.report_time_utc.astimezone(sleep_tz)

        # Sleep starts 1h after previous duty release (transit/wind-down)
        # and ends MIN_WAKE_BEFORE_REPORT hours before next report
        if previous_duty:
            sleep_start = previous_duty.release_time_utc + timedelta(hours=1)
        else:
            sleep_start = duty.report_time_utc - timedelta(hours=rest_hours - 1)

        sleep_end = duty.report_time_utc - timedelta(hours=self.MIN_WAKE_BEFORE_REPORT)

        sleep_start_local = sleep_start.astimezone(sleep_tz)
        sleep_end_local = sleep_end.astimezone(sleep_tz)

        sleep_start_utc, sleep_end_utc, sleep_warnings = self._validate_sleep_no_overlap(
            sleep_start, sleep_end, duty, previous_duty
        )
        sleep_start_local = sleep_start_utc.astimezone(sleep_tz)
        sleep_end_local = sleep_end_utc.astimezone(sleep_tz)

        bio_tz = self.home_tz.zone if self.is_layover else None

        sleep_quality = self.calculate_sleep_quality(
            sleep_start=sleep_start_local,
            sleep_end=sleep_end_local,
            location=sleep_location,
            previous_duty_end=previous_duty.release_time_utc if previous_duty else None,
            next_event=report_local,
            location_timezone=sleep_tz.zone,
            biological_timezone=bio_tz
        )

        restricted_sleep = SleepBlock(
            start_utc=sleep_start_utc,
            end_utc=sleep_end_utc,
            location_timezone=sleep_tz.zone,
            duration_hours=sleep_quality.actual_sleep_hours,
            quality_factor=sleep_quality.sleep_efficiency,
            effective_sleep_hours=sleep_quality.effective_sleep_hours,
            environment=sleep_location,
            sleep_start_day=sleep_start_local.day,
            sleep_start_hour=sleep_start_local.hour + sleep_start_local.minute / 60.0,
            sleep_end_day=sleep_end_local.day,
            sleep_end_hour=sleep_end_local.hour + sleep_end_local.minute / 60.0
        )

        # Low confidence — severe time constraint
        confidence = 0.45 if not sleep_warnings else 0.30

        if self.is_layover:
            confidence *= 0.90

        location_desc = f"{sleep_location} (layover)" if self.is_layover else sleep_location
        return SleepStrategy(
            strategy_type='restricted',
            sleep_blocks=[restricted_sleep],
            confidence=confidence,
            explanation=(
                f"Restricted sleep at {location_desc}: only {rest_hours:.1f}h rest period, "
                f"{sleep_quality.effective_sleep_hours:.1f}h effective sleep "
                f"(truncated by schedule constraints)"
            ),
            quality_analysis=[sleep_quality]
        )

    def _split_strategy(
        self,
        duty: Duty,
        previous_duty: Optional[Duty],
        rest_hours: float
    ) -> SleepStrategy:
        """
        Split sleep strategy: short layover (9-10h rest) where one
        consolidated block is difficult. Pilot takes a main sleep block
        after previous duty release and may have a short nap before
        next report.

        References:
            Jackson et al. (2014) Accid Anal Prev 72:252-261
            Kosmadopoulos et al. (2017) Chronobiol Int 34(2):190-196
        """
        if self.is_layover and self.layover_timezone:
            sleep_tz = pytz.timezone(self.layover_timezone)
            sleep_location = self.sleep_environment
        else:
            sleep_tz = self.home_tz
            sleep_location = 'home'

        report_local = duty.report_time_utc.astimezone(sleep_tz)

        # Main sleep block: starts 1h after previous duty release
        if previous_duty:
            main_start = previous_duty.release_time_utc + timedelta(hours=1)
        else:
            main_start = duty.report_time_utc - timedelta(hours=rest_hours - 1)

        # Main sleep: use available time minus buffer for nap
        # Allocate ~70% of available sleep time to main block, rest to nap
        available_sleep_hours = rest_hours - 1.0 - self.MIN_WAKE_BEFORE_REPORT
        main_duration = min(6.0, available_sleep_hours * 0.70)
        main_end = main_start + timedelta(hours=main_duration)

        main_start_local = main_start.astimezone(sleep_tz)
        main_end_local = main_end.astimezone(sleep_tz)

        main_start_utc, main_end_utc, main_warnings = self._validate_sleep_no_overlap(
            main_start, main_end, duty, previous_duty
        )
        main_start_local = main_start_utc.astimezone(sleep_tz)
        main_end_local = main_end_utc.astimezone(sleep_tz)

        bio_tz = self.home_tz.zone if self.is_layover else None

        main_quality = self.calculate_sleep_quality(
            sleep_start=main_start_local,
            sleep_end=main_end_local,
            location=sleep_location,
            previous_duty_end=previous_duty.release_time_utc if previous_duty else None,
            next_event=report_local,
            location_timezone=sleep_tz.zone,
            biological_timezone=bio_tz
        )

        main_sleep = SleepBlock(
            start_utc=main_start_utc,
            end_utc=main_end_utc,
            location_timezone=sleep_tz.zone,
            duration_hours=main_quality.actual_sleep_hours,
            quality_factor=main_quality.sleep_efficiency,
            effective_sleep_hours=main_quality.effective_sleep_hours,
            environment=sleep_location,
            sleep_start_day=main_start_local.day,
            sleep_start_hour=main_start_local.hour + main_start_local.minute / 60.0,
            sleep_end_day=main_end_local.day,
            sleep_end_hour=main_end_local.hour + main_end_local.minute / 60.0
        )

        # Short nap before duty (remaining time)
        nap_end = duty.report_time_utc - timedelta(hours=self.MIN_WAKE_BEFORE_REPORT)
        nap_duration = min(2.0, available_sleep_hours - main_duration)
        if nap_duration < 0.5:
            # Not enough time for a nap; return single-block split
            confidence = 0.40 if not main_warnings else 0.30
            if self.is_layover:
                confidence *= 0.90
            location_desc = f"{sleep_location} (layover)" if self.is_layover else sleep_location
            return SleepStrategy(
                strategy_type='split',
                sleep_blocks=[main_sleep],
                confidence=confidence,
                explanation=(
                    f"Split sleep at {location_desc}: {rest_hours:.1f}h rest, "
                    f"{main_quality.effective_sleep_hours:.1f}h effective "
                    f"(insufficient time for nap block)"
                ),
                quality_analysis=[main_quality]
            )

        nap_start = nap_end - timedelta(hours=nap_duration)
        nap_start_local = nap_start.astimezone(sleep_tz)
        nap_end_local = nap_end.astimezone(sleep_tz)

        # Ensure nap doesn't overlap main sleep
        if nap_start < main_end_utc:
            nap_start = main_end_utc + timedelta(minutes=30)
            nap_start_local = nap_start.astimezone(sleep_tz)

        if nap_start >= nap_end:
            # No room for nap
            confidence = 0.40 if not main_warnings else 0.30
            if self.is_layover:
                confidence *= 0.90
            location_desc = f"{sleep_location} (layover)" if self.is_layover else sleep_location
            return SleepStrategy(
                strategy_type='split',
                sleep_blocks=[main_sleep],
                confidence=confidence,
                explanation=(
                    f"Split sleep at {location_desc}: {rest_hours:.1f}h rest, "
                    f"{main_quality.effective_sleep_hours:.1f}h effective "
                    f"(no room for second block)"
                ),
                quality_analysis=[main_quality]
            )

        nap_quality = self.calculate_sleep_quality(
            sleep_start=nap_start_local,
            sleep_end=nap_end_local,
            location=sleep_location,
            previous_duty_end=main_end_utc,
            next_event=report_local,
            is_nap=True,
            location_timezone=sleep_tz.zone,
            biological_timezone=bio_tz
        )

        nap_block = SleepBlock(
            start_utc=nap_start,
            end_utc=nap_end,
            location_timezone=sleep_tz.zone,
            duration_hours=nap_quality.actual_sleep_hours,
            quality_factor=nap_quality.sleep_efficiency,
            effective_sleep_hours=nap_quality.effective_sleep_hours,
            is_anchor_sleep=False,
            environment=sleep_location,
            sleep_start_day=nap_start_local.day,
            sleep_start_hour=nap_start_local.hour + nap_start_local.minute / 60.0,
            sleep_end_day=nap_end_local.day,
            sleep_end_hour=nap_end_local.hour + nap_end_local.minute / 60.0
        )

        total_effective = main_quality.effective_sleep_hours + nap_quality.effective_sleep_hours
        confidence = 0.50 if not (main_warnings) else 0.35
        if self.is_layover:
            confidence *= 0.90

        location_desc = f"{sleep_location} (layover)" if self.is_layover else sleep_location
        return SleepStrategy(
            strategy_type='split',
            sleep_blocks=[main_sleep, nap_block],
            confidence=confidence,
            explanation=(
                f"Split sleep at {location_desc}: {rest_hours:.1f}h rest, "
                f"{main_quality.effective_sleep_hours:.1f}h + "
                f"{nap_quality.effective_sleep_hours:.1f}h nap = "
                f"{total_effective:.1f}h effective"
            ),
            quality_analysis=[main_quality, nap_quality]
        )

    def _afternoon_nap_strategy(
        self,
        duty: Duty,
        previous_duty: Optional[Duty]
    ) -> SleepStrategy:
        """
        Afternoon nap strategy: late report (14:00-20:00 local) allows
        normal previous-night sleep plus an afternoon nap before duty.

        References:
            Dinges et al. (1987) Sleep 10(4):313-329
            Signal et al. (2014) Aviat Space Environ Med 85:1199-1208
        """
        if self.is_layover and self.layover_timezone:
            sleep_tz = pytz.timezone(self.layover_timezone)
            sleep_location = self.sleep_environment
        else:
            sleep_tz = self.home_tz
            sleep_location = 'home'

        report_local = duty.report_time_utc.astimezone(sleep_tz)

        # Normal previous-night sleep (23:00-07:00)
        night_start = report_local.replace(hour=self.NORMAL_BEDTIME_HOUR, minute=0) - timedelta(days=1)
        night_end = report_local.replace(hour=self.NORMAL_WAKE_HOUR, minute=0)

        night_start_utc, night_end_utc, night_warnings = self._validate_sleep_no_overlap(
            night_start.astimezone(pytz.utc), night_end.astimezone(pytz.utc), duty, previous_duty
        )
        night_start = night_start_utc.astimezone(sleep_tz)
        night_end = night_end_utc.astimezone(sleep_tz)

        bio_tz = self.home_tz.zone if self.is_layover else None

        night_quality = self.calculate_sleep_quality(
            sleep_start=night_start,
            sleep_end=night_end,
            location=sleep_location,
            previous_duty_end=previous_duty.release_time_utc if previous_duty else None,
            next_event=report_local,
            location_timezone=sleep_tz.zone,
            biological_timezone=bio_tz
        )

        night_sleep = SleepBlock(
            start_utc=night_start.astimezone(pytz.utc),
            end_utc=night_end.astimezone(pytz.utc),
            location_timezone=sleep_tz.zone,
            duration_hours=night_quality.actual_sleep_hours,
            quality_factor=night_quality.sleep_efficiency,
            effective_sleep_hours=night_quality.effective_sleep_hours,
            environment=sleep_location,
            sleep_start_day=night_start.day,
            sleep_start_hour=night_start.hour + night_start.minute / 60.0,
            sleep_end_day=night_end.day,
            sleep_end_hour=night_end.hour + night_end.minute / 60.0
        )

        # Afternoon nap: 1.5h, ending 2h before report
        nap_end = report_local - timedelta(hours=self.MIN_WAKE_BEFORE_REPORT)
        nap_start = nap_end - timedelta(hours=1.5)

        nap_start_utc, nap_end_utc, nap_warnings = self._validate_sleep_no_overlap(
            nap_start.astimezone(pytz.utc), nap_end.astimezone(pytz.utc), duty, previous_duty
        )
        nap_start = nap_start_utc.astimezone(sleep_tz)
        nap_end = nap_end_utc.astimezone(sleep_tz)

        nap_quality = self.calculate_sleep_quality(
            sleep_start=nap_start,
            sleep_end=nap_end,
            location=sleep_location,
            previous_duty_end=night_end.astimezone(pytz.utc),
            next_event=report_local,
            is_nap=True,
            location_timezone=sleep_tz.zone,
            biological_timezone=bio_tz
        )

        nap_block = SleepBlock(
            start_utc=nap_start.astimezone(pytz.utc),
            end_utc=nap_end.astimezone(pytz.utc),
            location_timezone=sleep_tz.zone,
            duration_hours=nap_quality.actual_sleep_hours,
            quality_factor=nap_quality.sleep_efficiency,
            effective_sleep_hours=nap_quality.effective_sleep_hours,
            is_anchor_sleep=False,
            environment=sleep_location,
            sleep_start_day=nap_start.day,
            sleep_start_hour=nap_start.hour + nap_start.minute / 60.0,
            sleep_end_day=nap_end.day,
            sleep_end_hour=nap_end.hour + nap_end.minute / 60.0
        )

        total_effective = night_quality.effective_sleep_hours + nap_quality.effective_sleep_hours
        confidence = 0.60 if not (night_warnings or nap_warnings) else 0.45
        if self.is_layover:
            confidence *= 0.90

        location_desc = f"{sleep_location} (layover)" if self.is_layover else sleep_location
        return SleepStrategy(
            strategy_type='afternoon_nap',
            sleep_blocks=[night_sleep, nap_block],
            confidence=confidence,
            explanation=(
                f"Afternoon nap at {location_desc}: "
                f"{night_quality.actual_sleep_hours:.1f}h night + "
                f"{nap_quality.actual_sleep_hours:.1f}h nap = "
                f"{total_effective:.1f}h effective (late {report_local.strftime('%H:%M')} report)"
            ),
            quality_analysis=[night_quality, nap_quality]
        )

    def _extended_strategy(
        self,
        duty: Duty,
        previous_duty: Optional[Duty],
        rest_hours: float
    ) -> SleepStrategy:
        """
        Extended sleep strategy: long rest period (>14h) allows extended
        sleep opportunity. Pilot can sleep a full night plus additional
        recovery time.

        References:
            Banks et al. (2010) Sleep 33(8):1013-1026
            Kitamura et al. (2016) Sci Rep 6:35812
        """
        if self.is_layover and self.layover_timezone:
            sleep_tz = pytz.timezone(self.layover_timezone)
            sleep_location = self.sleep_environment
        else:
            sleep_tz = self.home_tz
            sleep_location = 'home'

        report_local = duty.report_time_utc.astimezone(sleep_tz)

        # Extended sleep: start at normal bedtime, allow up to 9h
        # (longer than normal 8h to reflect recovery opportunity)
        sleep_start = report_local.replace(hour=self.NORMAL_BEDTIME_HOUR, minute=0) - timedelta(days=1)
        # Allow extended wake — pilot may sleep later than 07:00
        extended_duration = min(9.0, self.MAX_REALISTIC_SLEEP)
        normal_wake = sleep_start + timedelta(hours=extended_duration)
        latest_wake = report_local - timedelta(hours=self.MIN_WAKE_BEFORE_REPORT)
        sleep_end = min(normal_wake, latest_wake)

        sleep_start_utc, sleep_end_utc, sleep_warnings = self._validate_sleep_no_overlap(
            sleep_start.astimezone(pytz.utc), sleep_end.astimezone(pytz.utc), duty, previous_duty
        )
        sleep_start = sleep_start_utc.astimezone(sleep_tz)
        sleep_end = sleep_end_utc.astimezone(sleep_tz)

        bio_tz = self.home_tz.zone if self.is_layover else None

        sleep_quality = self.calculate_sleep_quality(
            sleep_start=sleep_start,
            sleep_end=sleep_end,
            location=sleep_location,
            previous_duty_end=previous_duty.release_time_utc if previous_duty else None,
            next_event=report_local,
            location_timezone=sleep_tz.zone,
            biological_timezone=bio_tz
        )

        extended_sleep = SleepBlock(
            start_utc=sleep_start.astimezone(pytz.utc),
            end_utc=sleep_end.astimezone(pytz.utc),
            location_timezone=sleep_tz.zone,
            duration_hours=sleep_quality.actual_sleep_hours,
            quality_factor=sleep_quality.sleep_efficiency,
            effective_sleep_hours=sleep_quality.effective_sleep_hours,
            environment=sleep_location,
            sleep_start_day=sleep_start.day,
            sleep_start_hour=sleep_start.hour + sleep_start.minute / 60.0,
            sleep_end_day=sleep_end.day,
            sleep_end_hour=sleep_end.hour + sleep_end.minute / 60.0
        )

        # High confidence — ample rest
        confidence = 0.85 if not sleep_warnings else 0.70

        if self.is_layover:
            confidence *= 0.90

        location_desc = f"{sleep_location} (layover)" if self.is_layover else sleep_location
        return SleepStrategy(
            strategy_type='extended',
            sleep_blocks=[extended_sleep],
            confidence=confidence,
            explanation=(
                f"Extended sleep at {location_desc}: {rest_hours:.1f}h rest period, "
                f"{sleep_quality.effective_sleep_hours:.1f}h effective "
                f"(recovery opportunity)"
            ),
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
        
        # Check overlap with current duty — enforce MIN_WAKE_BEFORE_REPORT (2h)
        # gap, not just 30 minutes. Pilots need time for commute, briefing, etc.
        min_wake_gap = timedelta(hours=self.MIN_WAKE_BEFORE_REPORT)
        if adjusted_end > duty.report_time_utc - min_wake_gap:
            adjusted_end = duty.report_time_utc - min_wake_gap
            warnings.append("Sleep truncated: enforcing minimum wake period before report")
        
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
            
            latest_sleep = duty.report_time_utc - min_wake_gap
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

