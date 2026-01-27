"""
easa_utils.py - EASA Compliance & Risk Assessment Tools
========================================================

Utilities for:
- EASA FTL compliance validation
- Sleep opportunity estimation
- Fatigue risk scoring
"""

from datetime import datetime, timedelta, time
from typing import Dict, List, Optional, Tuple
import math
import pytz

from config import EASAFatigueFramework, BorbelyParameters, RiskThresholds
from data_models import Duty, SleepBlock, DutyTimeline


# ============================================================================
# EASA COMPLIANCE VALIDATOR
# ============================================================================

class EASAComplianceValidator:
    """
    Validate duties against EASA FTL regulations
    Legal compliance layer (separate from fatigue prediction)
    """
    
    def __init__(self, framework: EASAFatigueFramework = None):
        self.framework = framework or EASAFatigueFramework()
    
    def calculate_fdp_limits(self, duty: Duty) -> Dict[str, float]:
        """
        Calculate EASA FDP limits based on ORO.FTL.205
        
        Returns:
            - max_fdp: Base FDP limit from table (hours)
            - extended_fdp: With captain discretion (+2h max)
            - used_discretion: Whether actual duty exceeds base limit
        """
        # Get report time in home base local time
        tz = pytz.timezone(duty.home_base_timezone)
        report_local = duty.report_time_utc.astimezone(tz)
        report_hour = report_local.hour
        
        # Number of sectors (flight segments)
        sectors = len(duty.segments)
        
        # EASA ORO.FTL.205 Table 1 - Basic FDP limits (2 pilots)
        # Based on time of start (home base reference time)
        fdp_table = {
            # Hour of start: {sectors: FDP hours}
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
        
        # Cap sectors at 9+ (same limit applies)
        sectors_capped = min(sectors, 9)
        
        # Get base FDP limit
        max_fdp = fdp_table.get(report_hour, {}).get(sectors_capped, 13.0)
        
        # Captain discretion: +2 hours max (EASA ORO.FTL.205(d))
        extended_fdp = max_fdp + 2.0
        
        # Calculate actual FDP hours
        actual_fdp = (duty.release_time_utc - duty.report_time_utc).total_seconds() / 3600
        
        # Check if discretion was used
        used_discretion = actual_fdp > max_fdp
        
        return {
            'max_fdp': max_fdp,
            'extended_fdp': extended_fdp,
            'actual_fdp': actual_fdp,
            'used_discretion': used_discretion,
            'exceeds_discretion': actual_fdp > extended_fdp  # FTL violation
        }
    
    def calculate_wocl_encroachment(
        self,
        duty_start: datetime,
        duty_end: datetime,
        reference_timezone: str
    ) -> timedelta:
        """
        Calculate overlap with WOCL (02:00-05:59 reference time)
        EASA ORO.FTL.105(10)
        """
        tz = pytz.timezone(reference_timezone)
        duty_start_local = duty_start.astimezone(tz)
        duty_end_local = duty_end.astimezone(tz)
        
        total_encroachment = timedelta()
        current_day = duty_start_local.date()
        end_day = duty_end_local.date()
        
        while current_day <= end_day:
            wocl_start = datetime.combine(
                current_day,
                time(self.framework.wocl_start_hour, 0, 0)
            ).replace(tzinfo=tz)
            
            wocl_end = datetime.combine(
                current_day,
                time(self.framework.wocl_end_hour, self.framework.wocl_end_minute, 59)
            ).replace(tzinfo=tz)
            
            overlap_start = max(duty_start_local, wocl_start)
            overlap_end = min(duty_end_local, wocl_end)
            
            if overlap_start < overlap_end:
                total_encroachment += (overlap_end - overlap_start)
            
            current_day += timedelta(days=1)
        
        return total_encroachment
    
    def is_early_start(self, report_time_local: datetime) -> bool:
        """Report before 06:00 = early start"""
        return report_time_local.hour < self.framework.early_start_threshold_hour
    
    def is_late_finish(self, release_time_local: datetime) -> bool:
        """Release after 02:00 (and before 08:00) = late finish"""
        hour = release_time_local.hour
        return (self.framework.late_finish_threshold_hour <= hour < 
                self.framework.local_night_end_hour)
    
    def is_disruptive_duty(self, duty: Duty) -> Dict[str, any]:
        """Classify duty as disruptive per EASA GM1 ORO.FTL.235"""
        wocl_encroachment = self.calculate_wocl_encroachment(
            duty.report_time_utc,
            duty.release_time_utc,
            duty.home_base_timezone
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
# SLEEP ESTIMATION
# ============================================================================

class BiomathematicalSleepEstimator:
    """
    Estimate actual sleep obtained from opportunities
    More realistic than EASA's "8h opportunity = 8h sleep"
    
    V2.1: Now uses configurable SleepQualityParameters
    """
    
    def __init__(self, framework: EASAFatigueFramework = None, params: BorbelyParameters = None, 
                 sleep_quality_params: 'SleepQualityParameters' = None):
        self.framework = framework or EASAFatigueFramework()
        self.params = params or BorbelyParameters()
        
        # NEW in V2.1: Use configurable sleep quality parameters
        if sleep_quality_params is None:
            from config import SleepQualityParameters
            sleep_quality_params = SleepQualityParameters()
        self.sleep_quality = sleep_quality_params
    
    def estimate_sleep_quality(
        self,
        sleep_start_local: datetime,
        circadian_phase_shift: float = 0.0,
        environment: str = "hotel_typical",
        prior_wake_hours: float = 16.0
    ) -> float:
        """
        Calculate sleep quality factor (0-1)
        
        V2.1: Uses configurable parameters instead of hardcoded values
        
        Factors:
        1. Circadian alignment (when sleep occurs)
        2. Sleep pressure (prior wake time)
        3. Environment (home, hotel, crew rest)
        """
        
        # 1. Circadian sleep propensity
        hour_of_day = sleep_start_local.hour + sleep_start_local.minute / 60.0
        effective_hour = (hour_of_day - circadian_phase_shift) % 24
        
        # Sleep propensity peaks 23:00-07:00 (biological night)
        angle = 2 * math.pi * (effective_hour - 3.0) / 24
        circadian_propensity = 0.65 + 0.35 * math.cos(angle)
        
        # Penalty for starting outside optimal window (21:00-02:00)
        if not (21 <= effective_hour <= 24 or 0 <= effective_hour <= 2):
            # Late sleep start penalty
            if effective_hour > 2:
                hours_late = min(effective_hour - 2, 12)
                late_penalty = hours_late * self.sleep_quality.late_sleep_start_penalty_per_hour
                circadian_propensity *= (1.0 - late_penalty)
        
        # 2. Sleep pressure benefit (higher pressure = faster sleep onset)
        pressure_benefit = min(1.0, prior_wake_hours / 16.0)
        
        # 3. Environment quality (NEW: from config)
        environment_map = {
            'home': self.sleep_quality.quality_home,
            'hotel_quiet': self.sleep_quality.quality_hotel_quiet,
            'hotel_typical': self.sleep_quality.quality_hotel_typical,
            'hotel': self.sleep_quality.quality_hotel_typical,  # Alias
            'hotel_airport': self.sleep_quality.quality_hotel_airport,
            'layover': self.sleep_quality.quality_layover_unfamiliar,
            'crew_rest': self.sleep_quality.quality_crew_rest_facility
        }
        environment_quality = environment_map.get(environment, self.sleep_quality.quality_hotel_typical)
        
        # Combined quality
        overall_quality = (
            circadian_propensity * 
            environment_quality * 
            (0.7 + 0.3 * pressure_benefit)
        )
        
        return max(0.4, min(1.0, overall_quality))
    
    def estimate_sleep_block(
        self,
        opportunity_start: datetime,
        opportunity_end: datetime,
        location_timezone: str,
        circadian_phase_shift: float = 0.0,
        environment: str = "hotel",
        prior_wake_hours: float = 16.0
    ) -> SleepBlock:
        """Estimate actual sleep obtained"""
        
        duration_hours = (opportunity_end - opportunity_start).total_seconds() / 3600
        
        # Convert to local time
        tz = pytz.timezone(location_timezone)
        sleep_start_local = opportunity_start.astimezone(tz)
        
        # Calculate quality
        quality = self.estimate_sleep_quality(
            sleep_start_local,
            circadian_phase_shift,
            environment,
            prior_wake_hours
        )
        
        # Duration efficiency
        if duration_hours < 4:
            duration_efficiency = 0.75
        elif duration_hours <= 9:
            duration_efficiency = 1.0
        else:
            duration_efficiency = max(0.85, 1.0 - (duration_hours - 9) * 0.03)
        
        effective_sleep = duration_hours * quality * duration_efficiency
        
        return SleepBlock(
            start_utc=opportunity_start,
            end_utc=opportunity_end,
            location_timezone=location_timezone,
            duration_hours=duration_hours,
            quality_factor=quality * duration_efficiency,
            effective_sleep_hours=effective_sleep,
            circadian_misalignment_hours=abs(circadian_phase_shift),
            environment=environment
        )


# ============================================================================
# RISK SCORING
# ============================================================================

class FatigueRiskScorer:
    """
    Advanced risk assessment with actionable recommendations
    V2.1: EASA regulatory references + enhanced metrics
    """
    
    def __init__(self, thresholds: RiskThresholds = None):
        self.thresholds = thresholds or RiskThresholds()
    
    # NEW in V2.1: Helper methods
    
    @staticmethod
    def is_ulh_flight(segment: 'FlightSegment') -> bool:
        """
        Determine if flight qualifies as Ultra-Long-Haul (ULH)
        
        EASA typically considers >10h block time as ULH
        These flights often have crew rest facilities
        """
        return segment.block_time_hours >= 10.0
    
    @staticmethod
    def estimate_inflight_rest_opportunity(segment: 'FlightSegment', crew_complement: str = "augmented") -> Optional[Tuple[datetime, datetime]]:
        """
        Estimate inflight rest window for ULH flights
        
        Args:
            segment: Flight segment
            crew_complement: "single", "augmented", "double"
        
        Returns:
            (rest_start, rest_end) in UTC, or None if no rest expected
        
        Assumptions:
        - Rest occurs during cruise (after climb, before descent)
        - Augmented crew: 1 pilot rests for ~3-4h mid-flight
        - Double crew: 2 pilots alternate, each gets ~4-5h
        """
        if not FatigueRiskScorer.is_ulh_flight(segment):
            return None
        
        if crew_complement == "single":
            return None  # No inflight rest for single pilot ops
        
        # Estimate cruise start/end
        cruise_start = segment.scheduled_departure_utc + timedelta(minutes=45)  # After climb
        cruise_end = segment.scheduled_arrival_utc - timedelta(minutes=45)      # Before descent
        
        cruise_duration = (cruise_end - cruise_start).total_seconds() / 3600
        
        if crew_complement == "augmented":
            # One pilot gets rest mid-cruise (~3-4h)
            rest_duration_hours = min(4.0, cruise_duration * 0.4)
            rest_start = cruise_start + timedelta(hours=cruise_duration * 0.3)
            rest_end = rest_start + timedelta(hours=rest_duration_hours)
            return (rest_start, rest_end)
        
        elif crew_complement == "double":
            # Two pilots alternate - first rest gets earlier window
            rest_duration_hours = min(5.0, cruise_duration * 0.45)
            rest_start = cruise_start + timedelta(hours=cruise_duration * 0.2)
            rest_end = rest_start + timedelta(hours=rest_duration_hours)
            return (rest_start, rest_end)
        
        return None
    
    def score_duty_timeline(self, timeline: DutyTimeline) -> Dict:
        """
        Comprehensive risk assessment
        Returns actionable recommendations
        """
        
        # Classify risks
        min_risk = self.thresholds.classify(timeline.min_performance)
        landing_risk = self.thresholds.classify(timeline.landing_performance) \
                       if timeline.landing_performance else 'unknown'
        
        # Overall risk (worst of min or landing)
        if landing_risk in ['critical', 'extreme']:
            overall_risk = landing_risk
        elif landing_risk == 'high':
            overall_risk = 'high'
        else:
            overall_risk = min_risk
        
        # Get recommended action
        action_info = self.thresholds.get_action(overall_risk)
        
        # Pinch warnings
        has_pinch = len(timeline.pinch_events) > 0
        pinch_warning = None
        if has_pinch:
            critical_pinch = [p for p in timeline.pinch_events if p.severity == 'critical']
            if critical_pinch:
                pinch_warning = f"CRITICAL: {len(critical_pinch)} pinch event(s)"
            else:
                pinch_warning = f"WARNING: {len(timeline.pinch_events)} pinch event(s)"
        
        # SMS reportable?
        is_reportable = overall_risk in ['high', 'critical', 'extreme']
        
        # Additional warnings
        warnings = []
        if timeline.cumulative_sleep_debt > 10.0:
            warnings.append(f"Excessive sleep debt: {timeline.cumulative_sleep_debt:.1f}h")
        if timeline.wocl_encroachment_hours > 4.0:
            warnings.append(f"Extended WOCL exposure: {timeline.wocl_encroachment_hours:.1f}h")
        if abs(timeline.circadian_phase_shift) > 4.0:
            warnings.append(f"Significant circadian misalignment: {timeline.circadian_phase_shift:.1f}h")
        
        return {
            'overall_risk': overall_risk,
            'min_performance_risk': min_risk,
            'landing_risk': landing_risk,
            'min_performance_value': timeline.min_performance,
            'landing_performance_value': timeline.landing_performance,
            'recommended_action': action_info['action'],
            'easa_reference': action_info['easa_reference'],
            'description': action_info['description'],
            'is_reportable': is_reportable,
            'pinch_events': len(timeline.pinch_events),
            'pinch_warning': pinch_warning,
            'additional_warnings': warnings,
            'cumulative_sleep_debt': timeline.cumulative_sleep_debt
        }
