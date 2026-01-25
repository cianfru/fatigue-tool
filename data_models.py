"""
data_models.py - Core Data Structures
======================================

Data models for roster analysis, duties, sleep, and performance tracking.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Tuple
from enum import Enum
import pytz


# ============================================================================
# ENUMS
# ============================================================================

class AcclimatizationState(Enum):
    """EASA ORO.FTL.105 acclimatization states"""
    ACCLIMATIZED = "acclimatized"
    UNKNOWN = "unknown"


class FlightPhase(Enum):
    """Flight phases for task-weighted performance"""
    PREFLIGHT = "preflight"
    TAXI_OUT = "taxi_out"
    TAKEOFF = "takeoff"
    CLIMB = "climb"
    CRUISE = "cruise"
    DESCENT = "descent"
    APPROACH = "approach"
    LANDING = "landing"
    TAXI_IN = "taxi_in"
    GROUND_TURNAROUND = "ground_turnaround"


# ============================================================================
# ROSTER & DUTY STRUCTURES
# ============================================================================

@dataclass
class Airport:
    """Airport with timezone information"""
    code: str           # IATA (e.g., "LHR")
    timezone: str       # IANA (e.g., "Europe/London")
    latitude: float = 0.0
    longitude: float = 0.0
    
    def great_circle_distance(self, other: 'Airport') -> float:
        """
        Calculate great circle distance to another airport (km)
        Uses Haversine formula
        
        Useful for:
        - Determining if timezone shift is rapid (long-haul) vs slow (regional)
        - EASA acclimatization context (short vs long sectors)
        """
        import math
        
        # Convert to radians
        lat1, lon1 = math.radians(self.latitude), math.radians(self.longitude)
        lat2, lon2 = math.radians(other.latitude), math.radians(other.longitude)
        
        # Haversine formula
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
        c = 2 * math.asin(math.sqrt(a))
        
        # Earth radius in km
        r = 6371
        
        return c * r
    
    def timezone_difference_hours(self, other: 'Airport', reference_time: datetime) -> float:
        """
        Calculate timezone difference in hours (accounting for DST)
        
        Args:
            other: Destination airport
            reference_time: When the comparison is made (for DST)
        
        Returns:
            Hours difference (positive = eastward, negative = westward)
        """
        tz1 = pytz.timezone(self.timezone)
        tz2 = pytz.timezone(other.timezone)
        
        offset1 = tz1.utcoffset(reference_time).total_seconds() / 3600
        offset2 = tz2.utcoffset(reference_time).total_seconds() / 3600
        
        return offset2 - offset1


@dataclass
class FlightSegment:
    """Single flight segment"""
    flight_number: str
    departure_airport: Airport
    arrival_airport: Airport
    scheduled_departure_utc: datetime
    scheduled_arrival_utc: datetime
    
    @property
    def block_time_hours(self) -> float:
        return (self.scheduled_arrival_utc - self.scheduled_departure_utc).total_seconds() / 3600


@dataclass
class Duty:
    """Complete duty period"""
    duty_id: str
    date: datetime
    report_time_utc: datetime
    release_time_utc: datetime
    segments: List[FlightSegment]
    home_base_timezone: str
    
    @property
    def duty_hours(self) -> float:
        """Total duty period (report to release)"""
        return (self.release_time_utc - self.report_time_utc).total_seconds() / 3600
    
    @property
    def fdp_hours(self) -> float:
        """
        Flight Duty Period per EASA ORO.FTL.205
        
        FDP = Report time to end of last flight + 30 minutes post-flight
        
        Note: This is different from duty period which includes 
        additional time after FDP ends (typically 30-60 min for debriefing, 
        transport to release point, etc.)
        """
        if not self.segments:
            return 0.0
        
        fdp_start = self.report_time_utc
        # FDP ends 30 minutes after last flight lands
        fdp_end = self.segments[-1].scheduled_arrival_utc + timedelta(minutes=30)
        
        return (fdp_end - fdp_start).total_seconds() / 3600
    
    @property
    def post_fdp_time_hours(self) -> float:
        """Time between FDP end and duty release (typically debriefing, etc.)"""
        if not self.segments:
            return self.duty_hours
        
        fdp_end = self.segments[-1].scheduled_arrival_utc + timedelta(minutes=30)
        return (self.release_time_utc - fdp_end).total_seconds() / 3600
    
    @property
    def report_time_local(self) -> datetime:
        tz = pytz.timezone(self.segments[0].departure_airport.timezone)
        return self.report_time_utc.astimezone(tz)
    
    @property
    def release_time_local(self) -> datetime:
        tz = pytz.timezone(self.segments[-1].arrival_airport.timezone)
        return self.release_time_utc.astimezone(tz)


@dataclass
class Roster:
    """
    Sequence of duties for cumulative fatigue analysis
    V2.1: Added roster-level helper methods
    """
    roster_id: str
    pilot_id: str
    month: str  # YYYY-MM
    duties: List[Duty]
    home_base_timezone: str
    
    # Initial conditions
    initial_sleep_pressure: float = 0.3
    initial_sleep_debt: float = 0.0
    
    @property
    def total_duties(self) -> int:
        return len(self.duties)
    
    @property
    def total_block_hours(self) -> float:
        return sum(seg.block_time_hours for duty in self.duties for seg in duty.segments)
    
    @property
    def total_duty_hours(self) -> float:
        """Total duty hours for the month"""
        return sum(duty.duty_hours for duty in self.duties)
    
    @property
    def total_sectors(self) -> int:
        """Total flight segments"""
        return sum(len(duty.segments) for duty in self.duties)
    
    # NEW in V2.1: Helper methods for duty relationships
    
    def get_duty_by_id(self, duty_id: str) -> Optional[Duty]:
        """Find duty by ID"""
        return next((d for d in self.duties if d.duty_id == duty_id), None)
    
    def get_duty_index(self, duty_id: str) -> Optional[int]:
        """Get index of duty in roster"""
        for i, duty in enumerate(self.duties):
            if duty.duty_id == duty_id:
                return i
        return None
    
    def get_previous_duty(self, duty_id: str) -> Optional[Duty]:
        """Get duty immediately before the specified duty"""
        idx = self.get_duty_index(duty_id)
        if idx is not None and idx > 0:
            return self.duties[idx - 1]
        return None
    
    def get_next_duty(self, duty_id: str) -> Optional[Duty]:
        """Get duty immediately after the specified duty"""
        idx = self.get_duty_index(duty_id)
        if idx is not None and idx < len(self.duties) - 1:
            return self.duties[idx + 1]
        return None
    
    def get_rest_period_before(self, duty_id: str) -> Optional[timedelta]:
        """
        Calculate rest period before specified duty
        
        Returns:
            timedelta from previous duty release to this duty report
            None if this is the first duty
        """
        duty = self.get_duty_by_id(duty_id)
        prev_duty = self.get_previous_duty(duty_id)
        
        if duty and prev_duty:
            return duty.report_time_utc - prev_duty.release_time_utc
        return None
    
    def get_rest_period_after(self, duty_id: str) -> Optional[timedelta]:
        """
        Calculate rest period after specified duty
        
        Returns:
            timedelta from this duty release to next duty report
            None if this is the last duty
        """
        duty = self.get_duty_by_id(duty_id)
        next_duty = self.get_next_duty(duty_id)
        
        if duty and next_duty:
            return next_duty.report_time_utc - duty.release_time_utc
        return None
    
    def get_gap_between_duties(self, duty1_id: str, duty2_id: str) -> timedelta:
        """
        Calculate rest opportunity between two specific duties
        
        Returns:
            timedelta between duty1 release and duty2 report
            timedelta(0) if duties not found or not in order
        """
        d1 = self.get_duty_by_id(duty1_id)
        d2 = self.get_duty_by_id(duty2_id)
        
        if d1 and d2 and d2.report_time_utc > d1.release_time_utc:
            return d2.report_time_utc - d1.release_time_utc
        return timedelta(0)
    
    def get_duties_in_range(self, start_date: datetime, end_date: datetime) -> List[Duty]:
        """Get all duties within a date range"""
        return [
            duty for duty in self.duties
            if start_date <= duty.date <= end_date
        ]
    
    def get_disruptive_duties(self) -> List[Duty]:
        """
        Get all duties classified as disruptive
        
        Requires EASAComplianceValidator to be initialized
        Use this for pattern analysis
        """
        from easa_utils import EASAComplianceValidator
        validator = EASAComplianceValidator()
        
        disruptive = []
        for duty in self.duties:
            classification = validator.is_disruptive_duty(duty)
            if classification['is_disruptive']:
                disruptive.append(duty)
        
        return disruptive
    
    def get_consecutive_disruptive_sequences(self) -> List[List[Duty]]:
        """
        Identify sequences of consecutive disruptive duties
        
        Returns:
            List of sequences, where each sequence is a list of consecutive disruptive duties
        """
        from easa_utils import EASAComplianceValidator
        validator = EASAComplianceValidator()
        
        sequences = []
        current_sequence = []
        
        for duty in self.duties:
            classification = validator.is_disruptive_duty(duty)
            
            if classification['is_disruptive']:
                current_sequence.append(duty)
            else:
                if len(current_sequence) >= 2:
                    sequences.append(current_sequence)
                current_sequence = []
        
        # Catch final sequence
        if len(current_sequence) >= 2:
            sequences.append(current_sequence)
        
        return sequences
    
    def get_summary_statistics(self) -> Dict[str, any]:
        """
        Get roster-level summary statistics
        
        Returns comprehensive overview for reporting
        """
        return {
            'roster_id': self.roster_id,
            'pilot_id': self.pilot_id,
            'month': self.month,
            'total_duties': self.total_duties,
            'total_sectors': self.total_sectors,
            'total_block_hours': self.total_block_hours,
            'total_duty_hours': self.total_duty_hours,
            'average_duty_hours': self.total_duty_hours / self.total_duties if self.total_duties > 0 else 0,
            'disruptive_duties': len(self.get_disruptive_duties()),
            'consecutive_disruptive_sequences': len(self.get_consecutive_disruptive_sequences()),
            'first_duty_date': self.duties[0].date if self.duties else None,
            'last_duty_date': self.duties[-1].date if self.duties else None
        }


# ============================================================================
# CIRCADIAN & SLEEP STRUCTURES
# ============================================================================

@dataclass
class CircadianState:
    """
    Biological clock phase shift tracking
    NEW in V2: Dynamic adaptation over time
    """
    current_phase_shift_hours: float  # Offset from home base
    last_update_utc: datetime
    reference_timezone: str
    
    def __post_init__(self):
        assert -12 <= self.current_phase_shift_hours <= 12, \
            f"Phase shift out of range: {self.current_phase_shift_hours}"


@dataclass
class SleepBlock:
    """Sleep period with quality assessment"""
    start_utc: datetime
    end_utc: datetime
    location_timezone: str
    
    # Sleep quality
    duration_hours: float
    quality_factor: float              # 0-1
    effective_sleep_hours: float       # duration × quality
    circadian_misalignment_hours: float = 0.0
    
    # Classification
    is_anchor_sleep: bool = True       # Main sleep vs nap
    is_inflight_rest: bool = False     # NEW: Bunk rest during flight
    environment: str = "unknown"       # home, hotel, layover, crew_rest
    
    @property
    def recovery_value(self) -> float:
        """
        Homeostatic recovery potential
        
        SWS-rich sleep (well-aligned, stationary) has higher value
        Inflight rest has reduced recovery due to:
        - Noise and vibration
        - Frequent disturbances
        - Suboptimal sleep stages
        """
        # Base alignment bonus
        alignment_bonus = 1.0 if self.circadian_misalignment_hours < 2 else 0.85
        
        # Inflight rest penalty (NASA studies show ~70% effectiveness)
        inflight_penalty = 0.7 if self.is_inflight_rest else 1.0
        
        return self.effective_sleep_hours * alignment_bonus * inflight_penalty
    
    @property
    def is_restorative(self) -> bool:
        """
        Determines if this sleep is restorative enough to reduce sleep debt
        
        Criteria:
        - Duration ≥ 2 hours (minimum for meaningful recovery)
        - Quality ≥ 0.5 (not severely degraded)
        - Effective sleep ≥ 1.5 hours
        """
        return (
            self.duration_hours >= 2.0 and
            self.quality_factor >= 0.5 and
            self.effective_sleep_hours >= 1.5
        )
    
    def __post_init__(self):
        assert 0 <= self.quality_factor <= 1, f"Quality out of range: {self.quality_factor}"
        assert self.effective_sleep_hours <= self.duration_hours, \
            "Effective sleep cannot exceed duration"
        
        # Validate inflight rest assumptions
        if self.is_inflight_rest:
            # Inflight rest should be classified as crew_rest environment
            if self.environment not in ['crew_rest', 'unknown']:
                import warnings
                warnings.warn(
                    f"Inflight rest marked with environment '{self.environment}', "
                    "expected 'crew_rest'"
                )


# ============================================================================
# PERFORMANCE & ANALYSIS STRUCTURES
# ============================================================================

@dataclass
class PerformancePoint:
    """Single point in fatigue timeline"""
    timestamp_utc: datetime
    timestamp_local: datetime
    
    # Three-process components (0-1)
    circadian_component: float      # Process C
    homeostatic_component: float    # Process S
    sleep_inertia_component: float  # Process W
    
    # Integrated performance (0-100)
    raw_performance: float
    
    # Context
    current_flight_phase: Optional[FlightPhase] = None
    is_critical_phase: bool = False
    risk_level: str = "unknown"
    
    def __post_init__(self):
        """Validation"""
        assert 0 <= self.circadian_component <= 1, f"C out of range: {self.circadian_component}"
        assert 0 <= self.homeostatic_component <= 1, f"S out of range: {self.homeostatic_component}"
        assert 0 <= self.sleep_inertia_component <= 1, f"W out of range: {self.sleep_inertia_component}"
        assert 0 <= self.raw_performance <= 100, f"Performance out of range: {self.raw_performance}"
    
    # V2.1.1: Convenience properties for visualization and export
    
    @property
    def total_impairment(self) -> float:
        """
        Total impairment from sleep pressure + inertia (0-2 range)
        Higher = worse. Used for visualization.
        """
        return self.homeostatic_component + self.sleep_inertia_component
    
    @property
    def circadian_alertness(self) -> float:
        """Circadian component as percentage (0-100)"""
        return self.circadian_component * 100
    
    @property
    def sleep_pressure_percentage(self) -> float:
        """Homeostatic sleep pressure as percentage (0-100)"""
        return self.homeostatic_component * 100
    
    @property
    def sleep_inertia_percentage(self) -> float:
        """Sleep inertia as percentage (0-100)"""
        return self.sleep_inertia_component * 100
    
    def get_component_breakdown(self) -> Dict[str, float]:
        """
        Get detailed breakdown of all components
        Useful for CSV export or debugging
        
        Returns:
            Dict with percentage values and raw components
        """
        return {
            'timestamp_utc': self.timestamp_utc.isoformat(),
            'timestamp_local': self.timestamp_local.isoformat(),
            'circadian_alertness_pct': self.circadian_alertness,
            'sleep_pressure_pct': self.sleep_pressure_percentage,
            'sleep_inertia_pct': self.sleep_inertia_percentage,
            'total_impairment': self.total_impairment,
            'raw_performance': self.raw_performance,
            'flight_phase': self.current_flight_phase.value if self.current_flight_phase else None,
            'is_critical_phase': self.is_critical_phase,
            'risk_level': self.risk_level
        }


@dataclass
@dataclass
class PinchEvent:
    """
    'Pinch' event: High sleep pressure during circadian minimum
    NEW in V2: Dangerous state combination detection
    """
    time_utc: datetime
    time_local: datetime
    flight_phase: FlightPhase
    performance: float
    circadian: float
    sleep_pressure: float
    severity: str  # 'high' or 'critical'
    
    def __str__(self):
        return (f"PINCH at {self.time_local.strftime('%H:%M')} during {self.flight_phase.value}: "
                f"Performance {self.performance:.1f} (C={self.circadian:.2f}, S={self.sleep_pressure:.2f})")


@dataclass
class DutyTimeline:
    """Complete performance timeline for a duty"""
    duty_id: str
    duty_date: datetime
    timeline: List[PerformancePoint]
    
    # Summary statistics
    min_performance: float = 0.0
    min_performance_time: Optional[datetime] = None
    average_performance: float = 0.0
    
    # Critical phases
    landing_performance: Optional[float] = None
    landing_time: Optional[datetime] = None
    
    # Sleep context
    prior_sleep_hours: float = 0.0
    cumulative_sleep_debt: float = 0.0
    
    # EASA compliance
    easa_compliant: bool = True
    wocl_encroachment_hours: float = 0.0
    
    # NEW in V2
    pinch_events: List[PinchEvent] = field(default_factory=list)
    circadian_phase_shift: float = 0.0
    
    # OPTIMIZATION: Cache final state to avoid recomputation in next duty
    final_circadian_state: Optional['CircadianState'] = None
    final_process_s: float = 0.0


@dataclass
class MonthlyAnalysis:
    """
    Complete roster analysis
    NEW in V2: Roster-level insights
    """
    roster: Roster
    duty_timelines: List[DutyTimeline]
    
    # Monthly statistics
    high_risk_duties: int = 0
    critical_risk_duties: int = 0
    total_pinch_events: int = 0
    
    # Sleep statistics
    average_sleep_per_night: float = 0.0
    max_sleep_debt: float = 0.0
    
    # Worst events
    lowest_performance_duty: Optional[str] = None
    lowest_performance_value: float = 100.0
