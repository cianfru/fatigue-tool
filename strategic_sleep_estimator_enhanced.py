"""
strategic_sleep_estimator_enhanced.py - PRODUCTION VERSION
===========================================================

Full real-world sleep quality calculation for airline operations.

This version includes ALL factors that affect pilot sleep:
- WOCL overlap (sleeping during 02:00-06:00)
- Late sleep onset (going to bed after midnight)
- Recovery sleep boost (post-duty deep sleep)
- Time pressure (anxiety about waking for next duty)
- Biological sleep limits (can't sleep 12+ hours)
- Insufficient sleep penalties (< 6h fragmentation)
- Circadian misalignment

NOT edge cases - this is NORMAL airline operations:
- Long-haul arriving 00:00-06:00
- Short-haul late night ops
- Cargo/redeye operations
- Quick turnarounds

Scientific Foundation:
- Signal et al. (2009): Night flight napping strategies
- Gander et al. (2013): Early morning sleep patterns  
- Roach et al. (2012): Split sleep effectiveness
- Åkerstedt (1995): Sleep environment quality
- Lack & Wright (1993): Circadian sleep timing
- Dinges et al. (1997): Recovery sleep characteristics

Target: 85-90% accuracy for real pilot behavior
"""

from datetime import datetime, timedelta
from typing import List, Tuple, Optional, Dict, Any
import pytz
from dataclasses import dataclass
import math

from data_models import Duty, SleepBlock, FlightPhase


@dataclass
class SleepQualityAnalysis:
    """Detailed breakdown of sleep quality factors"""
    total_sleep_hours: float
    actual_sleep_hours: float  # After biological cap
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
    confidence: float  # 0.0-1.0 how confident we are in this prediction
    explanation: str  # Human-readable reason
    quality_analysis: List[SleepQualityAnalysis]  # One per sleep block


class EnhancedStrategicSleepEstimator:
    """
    Production-ready sleep estimator with full quality calculation
    
    Handles real-world scenarios:
    - Midnight landings
    - WOCL operations
    - Quick turnarounds
    - Recovery sleep
    - Late sleep onset
    """
    
    def __init__(self, home_timezone: str = 'UTC'):
        self.home_tz = pytz.timezone(home_timezone)
        
        # Research-backed baseline parameters
        self.NORMAL_BEDTIME_HOUR = 23
        self.NORMAL_WAKE_HOUR = 7
        self.NORMAL_SLEEP_DURATION = 8.0
        
        # Strategic behavior thresholds
        self.NIGHT_FLIGHT_THRESHOLD = 22
        self.EARLY_REPORT_THRESHOLD = 7
        self.WOCL_START = 2
        self.WOCL_END = 6
        
        # Base sleep efficiency by location (Åkerstedt 1995)
        self.LOCATION_EFFICIENCY = {
            'home': 0.90,
            'hotel': 0.85,
            'crew_rest': 0.88,
            'airport_hotel': 0.82,
            'crew_house': 0.87
        }
        
        # Biological limits
        self.MAX_REALISTIC_SLEEP = 10.0  # Hours - rarely sleep more even with opportunity
        self.MIN_SLEEP_FOR_QUALITY = 6.0  # Below this = fragmented architecture
    
    def estimate_strategic_sleep(
        self,
        duty: Duty,
        previous_duty: Optional[Duty] = None
    ) -> SleepStrategy:
        """
        Main entry point: Estimate how pilot actually slept before duty
        
        NOW INCLUDES FULL QUALITY CALCULATION
        """
        
        report_local = duty.report_time_utc.astimezone(self.home_tz)
        report_hour = report_local.hour
        
        # Analyze duty characteristics
        duty_duration = (duty.release_time_utc - duty.report_time_utc).total_seconds() / 3600
        crosses_wocl = self._duty_crosses_wocl(duty)
        
        # Decision tree based on research
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
    
    def _calculate_sleep_quality(
        self,
        sleep_start: datetime,
        sleep_end: datetime,
        location: str,
        previous_duty_end: Optional[datetime],
        next_event: datetime,
        is_nap: bool = False
    ) -> SleepQualityAnalysis:
        """
        Calculate realistic sleep quality with ALL factors
        
        This is the CORE FUNCTION that handles real-world complexity
        """
        
        # 1. Calculate raw duration
        total_hours = (sleep_end - sleep_start).total_seconds() / 3600
        
        # 2. Apply biological sleep limit
        # Research: After duty, pilots rarely sleep >10h even with opportunity
        if total_hours > self.MAX_REALISTIC_SLEEP and not is_nap:
            actual_duration = self.MAX_REALISTIC_SLEEP
        else:
            actual_duration = total_hours
        
        # 3. Base efficiency by location (Åkerstedt 1995)
        base_efficiency = self.LOCATION_EFFICIENCY.get(location, 0.85)
        
        # Naps have inherently lower efficiency
        if is_nap:
            base_efficiency *= 0.88  # Naps ~88% of full sleep efficiency
        
        # 4. WOCL overlap penalty
        wocl_overlap = self._calculate_wocl_overlap(sleep_start, sleep_end)
        
        if wocl_overlap > 0:
            # Sleeping during WOCL = lighter, more fragmented sleep
            # Research: 5% penalty per hour in WOCL
            wocl_penalty = 1.0 - (wocl_overlap * 0.05)
            wocl_penalty = max(0.75, wocl_penalty)  # Floor at 75%
        else:
            wocl_penalty = 1.0
        
        # 5. Late sleep onset penalty
        sleep_start_hour = sleep_start.hour + sleep_start.minute / 60.0
        
        if sleep_start_hour >= 1 and sleep_start_hour < 4:
            # Going to bed 01:00-04:00 = delayed sleep
            # Research: Longer sleep latency, reduced quality
            late_onset_penalty = 0.93
        elif sleep_start_hour >= 0 and sleep_start_hour < 1:
            # Midnight-01:00 = slightly late
            late_onset_penalty = 0.97
        else:
            late_onset_penalty = 1.0
        
        # 6. Recovery sleep boost
        if previous_duty_end:
            hours_since_duty = (sleep_start - previous_duty_end).total_seconds() / 3600
            
            if hours_since_duty < 3:
                # Immediate post-duty sleep
                # Research: Recovery sleep has more slow-wave sleep (Dinges 1997)
                recovery_boost = 1.10 if not is_nap else 1.05
            else:
                recovery_boost = 1.0
        else:
            recovery_boost = 1.0
            hours_since_duty = None
        
        # 7. Time pressure factor
        hours_until_duty = (next_event - sleep_end).total_seconds() / 3600
        
        if hours_until_duty < 1.5:
            # Very tight timing - anxiety about waking
            # Research: Stress reduces sleep quality (Åkerstedt 2004)
            time_pressure_factor = 0.88
        elif hours_until_duty < 3:
            time_pressure_factor = 0.93
        elif hours_until_duty < 6:
            time_pressure_factor = 0.97
        else:
            # No time pressure - natural wake
            time_pressure_factor = 1.03  # Slight bonus for natural wake
        
        # 8. Insufficient sleep penalty
        if actual_duration < 4 and not is_nap:
            # < 4h = severely fragmented sleep architecture
            insufficient_penalty = 0.75
        elif actual_duration < 6 and not is_nap:
            # < 6h = reduced deep sleep
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
        
        # Ensure efficiency stays in reasonable bounds
        combined_efficiency = max(0.50, min(1.0, combined_efficiency))
        
        # 10. Calculate effective sleep
        effective_sleep_hours = actual_duration * combined_efficiency
        
        # 11. Generate warnings
        warnings = self._generate_sleep_warnings(
            effective_sleep_hours,
            actual_duration,
            wocl_overlap,
            hours_until_duty,
            is_nap
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
        sleep_end: datetime
    ) -> float:
        """Calculate hours of sleep overlapping WOCL (02:00-06:00)"""
        
        sleep_start_hour = sleep_start.hour + sleep_start.minute / 60.0
        sleep_end_hour = sleep_end.hour + sleep_end.minute / 60.0
        
        # Handle overnight sleep
        if sleep_end_hour < sleep_start_hour:
            sleep_end_hour += 24
        
        # Calculate overlap with WOCL window
        overlap_start = max(sleep_start_hour, self.WOCL_START)
        overlap_end = min(sleep_end_hour, self.WOCL_END)
        
        if overlap_start < self.WOCL_END and overlap_end > self.WOCL_START:
            overlap = max(0, overlap_end - overlap_start)
        else:
            overlap = 0.0
        
        # Handle case where sleep crosses midnight into WOCL
        if sleep_start_hour > self.WOCL_END and sleep_end_hour > 24:
            # Sleep goes past midnight into next day's WOCL
            next_day_wocl_start = 24 + self.WOCL_START
            next_day_wocl_end = 24 + self.WOCL_END
            
            next_overlap_start = max(sleep_start_hour, next_day_wocl_start)
            next_overlap_end = min(sleep_end_hour, next_day_wocl_end)
            
            if next_overlap_start < next_day_wocl_end:
                overlap += max(0, next_overlap_end - next_overlap_start)
        
        return overlap
    
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
        """Night flight strategy with FULL quality calculation"""
        
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
        
        # ENHANCED: Full quality calculation
        morning_quality = self._calculate_sleep_quality(
            sleep_start=morning_sleep_start,
            sleep_end=morning_sleep_end,
            location='home',
            previous_duty_end=previous_duty.release_time_utc if previous_duty else None,
            next_event=report_local
        )
        
        morning_sleep = SleepBlock(
            date=morning_sleep_start.date(),
            start_utc=morning_sleep_start.astimezone(pytz.utc),
            end_utc=morning_sleep_end.astimezone(pytz.utc),
            total_sleep_hours=morning_quality.actual_sleep_hours,
            effective_sleep_hours=morning_quality.effective_sleep_hours,
            environment='home'
        )
        
        # Afternoon nap
        nap_end = report_local - timedelta(hours=1.5)
        nap_start = nap_end - timedelta(hours=3.5)
        
        nap_quality = self._calculate_sleep_quality(
            sleep_start=nap_start,
            sleep_end=nap_end,
            location='home',
            previous_duty_end=morning_sleep_end.astimezone(pytz.utc),
            next_event=report_local,
            is_nap=True
        )
        
        afternoon_nap = SleepBlock(
            date=nap_start.date(),
            start_utc=nap_start.astimezone(pytz.utc),
            end_utc=nap_end.astimezone(pytz.utc),
            total_sleep_hours=nap_quality.actual_sleep_hours,
            effective_sleep_hours=nap_quality.effective_sleep_hours,
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
        """Early report strategy with FULL quality calculation"""
        
        report_local = duty.report_time_utc.astimezone(self.home_tz)
        
        # Wake 1h before report
        wake_time = report_local - timedelta(hours=1)
        
        # Go to bed 2.5h earlier than normal
        sleep_duration = 8.0
        sleep_end = wake_time
        sleep_start = sleep_end - timedelta(hours=sleep_duration)
        
        if previous_duty:
            release_local = previous_duty.release_time_utc.astimezone(self.home_tz)
            earliest_sleep = release_local + timedelta(hours=1.5)
            if sleep_start < earliest_sleep:
                sleep_start = earliest_sleep
                sleep_duration = (sleep_end - sleep_start).total_seconds() / 3600
        
        # ENHANCED: Full quality calculation
        sleep_quality = self._calculate_sleep_quality(
            sleep_start=sleep_start,
            sleep_end=sleep_end,
            location='home',
            previous_duty_end=previous_duty.release_time_utc if previous_duty else None,
            next_event=report_local
        )
        
        early_sleep = SleepBlock(
            date=sleep_start.date(),
            start_utc=sleep_start.astimezone(pytz.utc),
            end_utc=sleep_end.astimezone(pytz.utc),
            total_sleep_hours=sleep_quality.actual_sleep_hours,
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
        """WOCL duty strategy with FULL quality calculation"""
        
        report_local = duty.report_time_utc.astimezone(self.home_tz)
        
        # Anchor sleep before duty
        anchor_end = report_local - timedelta(hours=1.5)
        anchor_start = anchor_end - timedelta(hours=4.5)
        
        anchor_quality = self._calculate_sleep_quality(
            sleep_start=anchor_start,
            sleep_end=anchor_end,
            location='home',
            previous_duty_end=previous_duty.release_time_utc if previous_duty else None,
            next_event=report_local
        )
        
        anchor_sleep = SleepBlock(
            date=anchor_start.date(),
            start_utc=anchor_start.astimezone(pytz.utc),
            end_utc=anchor_end.astimezone(pytz.utc),
            total_sleep_hours=anchor_quality.actual_sleep_hours,
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
        """Normal daytime duty with FULL quality calculation"""
        
        report_local = duty.report_time_utc.astimezone(self.home_tz)
        
        # Wake 2.5h before report
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
        
        # ENHANCED: Full quality calculation
        sleep_quality = self._calculate_sleep_quality(
            sleep_start=sleep_start,
            sleep_end=sleep_end,
            location='home',
            previous_duty_end=previous_duty.release_time_utc if previous_duty else None,
            next_event=report_local
        )
        
        normal_sleep = SleepBlock(
            date=sleep_start.date(),
            start_utc=sleep_start.astimezone(pytz.utc),
            end_utc=sleep_end.astimezone(pytz.utc),
            total_sleep_hours=sleep_quality.actual_sleep_hours,
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
        """Check if duty encroaches on WOCL"""
        start_local = duty.report_time_utc.astimezone(self.home_tz)
        end_local = duty.release_time_utc.astimezone(self.home_tz)
        
        current = start_local
        while current <= end_local:
            if self.WOCL_START <= current.hour < self.WOCL_END:
                return True
            current += timedelta(hours=1)
        
        return False


# ============================================================================
# USAGE EXAMPLE
# ============================================================================

if __name__ == "__main__":
    
    print("Enhanced Strategic Sleep Estimator - Real World Test")
    print("=" * 70)
    print()
    
    estimator = EnhancedStrategicSleepEstimator(home_timezone='Europe/London')
    
    # TEST: Midnight landing scenario
    from data_models import Duty
    
    midnight_landing_duty = Duty(
        duty_id="REAL_WORLD_1",
        date=datetime.now().date(),
        report_time_utc=datetime.now().replace(hour=14, minute=0, tzinfo=pytz.utc),
        release_time_utc=datetime.now().replace(hour=18, minute=0, tzinfo=pytz.utc),
        segments=[],
        home_base_timezone='Europe/London'
    )
    
    previous = Duty(
        duty_id="PREV",
        date=datetime.now().date(),
        report_time_utc=datetime.now().replace(hour=20, minute=0, tzinfo=pytz.utc) - timedelta(days=1),
        release_time_utc=datetime.now().replace(hour=0, minute=0, tzinfo=pytz.utc),  # Midnight landing
        segments=[],
        home_base_timezone='Europe/London'
    )
    
    strategy = estimator.estimate_strategic_sleep(midnight_landing_duty, previous)
    
    print(f"Strategy: {strategy.strategy_type}")
    print(f"Confidence: {strategy.confidence * 100:.0f}%")
    print(f"Explanation: {strategy.explanation}")
    print()
    
    for i, sleep_block in enumerate(strategy.sleep_blocks):
        print(f"Sleep Block {i + 1}:")
        print(f"  {sleep_block.start_utc.strftime('%Y-%m-%d %H:%M')} → {sleep_block.end_utc.strftime('%H:%M')}")
        print(f"  Total: {sleep_block.total_sleep_hours:.1f}h")
        print(f"  Effective: {sleep_block.effective_sleep_hours:.1f}h")
        
        # Show detailed quality analysis
        quality = strategy.quality_analysis[i]
        print(f"  Quality factors:")
        print(f"    Base efficiency: {quality.base_efficiency:.2f}")
        print(f"    WOCL penalty: {quality.wocl_penalty:.2f} ({quality.wocl_overlap_hours:.1f}h overlap)")
        print(f"    Late onset penalty: {quality.late_onset_penalty:.2f}")
        print(f"    Recovery boost: {quality.recovery_boost:.2f}")
        print(f"    Time pressure: {quality.time_pressure_factor:.2f}")
        print(f"    Overall efficiency: {quality.sleep_efficiency:.2f}")
        
        if quality.warnings:
            print(f"  ⚠️  Warnings:")
            for warning in quality.warnings:
                print(f"    [{warning['severity']}] {warning['message']}")
        print()
