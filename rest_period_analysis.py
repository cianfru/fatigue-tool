"""
rest_period_analysis.py - EASA Rest Period Compliance & Sleep Quality Analysis
===============================================================================

Critical improvement: Distinguish between:
1. Full OFF days (24+ hours)
2. Minimum rest periods (12-36 hours between duties)
3. Quick turns (<12 hours - illegal)
4. Disruptive rest (legal but poor sleep quality)

Example scenarios:
- Fly 08:00-20:00, next duty 08:00+1 day = 12h rest (legal, minimal)
- Land 06:00, report 23:00 same day = 17h rest (legal but disruptive!)
- Land 14:00, report 20:00 same day = 6h rest (ILLEGAL)
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Tuple
from enum import Enum
import pytz

from data_models import Duty, Airport


class RestPeriodType(Enum):
    """Classification of rest periods per EASA ORO.FTL.235"""
    ILLEGAL = "illegal"                    # <12h (ORO.FTL.235(c))
    MINIMUM = "minimum"                    # 12-24h (bare minimum)
    ADEQUATE = "adequate"                  # 24-36h (standard rest)
    RECURRENT = "recurrent"                # 36h+ with 2 local nights (ORO.FTL.235(e))
    EXTENDED = "extended"                  # Multiple days off


class SleepDisruptionType(Enum):
    """Why sleep might be disrupted even if rest is legal"""
    NONE = "none"
    QUICK_TURN = "quick_turn"              # <18h rest (tight but legal)
    EARLY_REPORT_AFTER_LATE_ARRIVAL = "early_report_after_late"  # Land 23:00, report 06:00
    LATE_REPORT_AFTER_EARLY_ARRIVAL = "late_report_after_early"  # Land 06:00, report 23:00
    TIMEZONE_SHIFT = "timezone_shift"      # Layover in different timezone
    SPLIT_SLEEP_REQUIRED = "split_sleep"   # Need to sleep before AND after
    HOTEL_TRANSIT_TIME = "hotel_transit"   # Arrival/departure airports far from hotel


@dataclass
class RestPeriod:
    """
    Period between two duties - the CRITICAL analysis unit
    
    This is what EASA regulates and what determines fatigue!
    """
    # Basic info
    rest_id: str
    previous_duty_id: str
    next_duty_id: str
    
    # Timing (UTC)
    start_utc: datetime  # Previous duty release
    end_utc: datetime    # Next duty report
    
    # Location context
    location_airport: Airport
    location_timezone: str
    is_home_base: bool
    
    # Computed properties
    duration_hours: float = 0.0
    
    # EASA Classification
    rest_type: RestPeriodType = RestPeriodType.MINIMUM
    is_easa_compliant: bool = True
    easa_violations: List[str] = field(default_factory=list)
    
    # Sleep disruption analysis
    sleep_disruption_type: SleepDisruptionType = SleepDisruptionType.NONE
    sleep_disruption_severity: str = "none"  # "none", "minor", "moderate", "severe"
    sleep_disruption_reasons: List[str] = field(default_factory=list)
    
    # Sleep opportunity analysis
    estimated_sleep_windows: List['SleepOpportunity'] = field(default_factory=list)
    total_effective_sleep_hours: float = 0.0
    sleep_quality_rating: str = "unknown"  # "excellent", "good", "fair", "poor", "critical"
    
    # Additional context
    requires_hotel: bool = False
    estimated_hotel_checkin_time: Optional[datetime] = None
    estimated_hotel_checkout_time: Optional[datetime] = None
    
    def __post_init__(self):
        """Calculate duration"""
        self.duration_hours = (self.end_utc - self.start_utc).total_seconds() / 3600
    
    @property
    def start_local(self) -> datetime:
        tz = pytz.timezone(self.location_timezone)
        return self.start_utc.astimezone(tz)
    
    @property
    def end_local(self) -> datetime:
        tz = pytz.timezone(self.location_timezone)
        return self.end_utc.astimezone(tz)
    
    @property
    def local_night_count(self) -> int:
        """
        Count local nights (22:00-08:00 periods) in this rest
        Required for recurrent rest (ORO.FTL.235(e))
        """
        count = 0
        current = self.start_local.replace(hour=22, minute=0, second=0)
        
        while current < self.end_local:
            night_end = current + timedelta(hours=10)  # 22:00 to 08:00
            
            # Does this night overlap with rest period?
            if current >= self.start_local and night_end <= self.end_local:
                count += 1
            
            current += timedelta(days=1)
        
        return count


@dataclass
class SleepOpportunity:
    """
    Potential sleep window within a rest period
    
    Key insight: Rest ≠ Sleep
    - 12h rest might only allow 6h sleep (transit, eating, shower, etc)
    - Sleep timing matters (land 06:00 = circadian misalignment)
    """
    start_utc: datetime
    end_utc: datetime
    location_timezone: str
    
    # Sleep timing quality
    circadian_alignment_score: float = 0.5  # 0-1, higher = better aligned
    is_primary_sleep: bool = True           # vs nap/secondary sleep
    
    # Practical constraints
    estimated_transit_before_minutes: int = 60   # Getting to hotel
    estimated_prep_after_minutes: int = 60       # Shower, breakfast, commute
    
    @property
    def opportunity_hours(self) -> float:
        """Raw time available"""
        return (self.end_utc - self.start_utc).total_seconds() / 3600
    
    @property
    def practical_sleep_hours(self) -> float:
        """Actual sleep possible (minus transit/prep)"""
        total_minutes = self.opportunity_hours * 60
        sleep_minutes = total_minutes - self.estimated_transit_before_minutes - self.estimated_prep_after_minutes
        return max(0, sleep_minutes / 60)
    
    @property
    def start_local(self) -> datetime:
        tz = pytz.timezone(self.location_timezone)
        return self.start_utc.astimezone(tz)
    
    @property
    def end_local(self) -> datetime:
        tz = pytz.timezone(self.location_timezone)
        return self.end_utc.astimezone(tz)


class RestPeriodAnalyzer:
    """
    Comprehensive rest period analysis
    
    Answers:
    1. Is this rest legal per EASA?
    2. How much sleep can actually be obtained?
    3. What disruptions will affect sleep quality?
    """
    
    def __init__(self):
        # EASA limits (ORO.FTL.235)
        self.minimum_rest_hours = 12.0
        self.recurrent_rest_hours = 36.0
        self.recurrent_rest_local_nights = 2
        
        # Practical thresholds
        self.quick_turn_threshold = 18.0  # <18h = tight turn
        self.adequate_rest_threshold = 24.0
        
        # Sleep timing thresholds (local time)
        self.early_morning_hour = 6   # Before 06:00 = early
        self.late_night_hour = 23     # After 23:00 = late
        self.optimal_bedtime_start = 22
        self.optimal_bedtime_end = 24
        self.optimal_wake_start = 6
        self.optimal_wake_end = 8
    
    def analyze_rest_period(
        self,
        previous_duty: Duty,
        next_duty: Duty
    ) -> RestPeriod:
        """
        Complete analysis of rest period between two duties
        """
        # Determine location (where are you during this rest?)
        location_airport = previous_duty.segments[-1].arrival_airport
        is_home_base = (location_airport.timezone == previous_duty.home_base_timezone)
        
        rest = RestPeriod(
            rest_id=f"{previous_duty.duty_id}_to_{next_duty.duty_id}",
            previous_duty_id=previous_duty.duty_id,
            next_duty_id=next_duty.duty_id,
            start_utc=previous_duty.release_time_utc,
            end_utc=next_duty.report_time_utc,
            location_airport=location_airport,
            location_timezone=location_airport.timezone,
            is_home_base=is_home_base,
            requires_hotel=not is_home_base
        )
        
        # 1. EASA compliance check
        self._check_easa_compliance(rest)
        
        # 2. Sleep disruption analysis
        self._analyze_sleep_disruptions(rest, previous_duty, next_duty)
        
        # 3. Sleep opportunity estimation
        self._estimate_sleep_opportunities(rest, previous_duty, next_duty)
        
        # 4. Overall sleep quality rating
        self._rate_sleep_quality(rest)
        
        return rest
    
    def _check_easa_compliance(self, rest: RestPeriod):
        """
        Check against EASA ORO.FTL.235 rest requirements
        """
        duration = rest.duration_hours
        local_nights = rest.local_night_count
        
        # Check minimum rest (ORO.FTL.235(c))
        if duration < self.minimum_rest_hours:
            rest.is_easa_compliant = False
            rest.rest_type = RestPeriodType.ILLEGAL
            rest.easa_violations.append(
                f"ORO.FTL.235(c): Rest {duration:.1f}h < minimum {self.minimum_rest_hours}h"
            )
            return
        
        # Classify rest type
        if duration >= self.recurrent_rest_hours and local_nights >= self.recurrent_rest_local_nights:
            rest.rest_type = RestPeriodType.RECURRENT
        elif duration >= 72:  # 3+ days
            rest.rest_type = RestPeriodType.EXTENDED
        elif duration >= self.adequate_rest_threshold:
            rest.rest_type = RestPeriodType.ADEQUATE
        else:
            rest.rest_type = RestPeriodType.MINIMUM
        
        rest.is_easa_compliant = True
    
    def _analyze_sleep_disruptions(
        self,
        rest: RestPeriod,
        previous_duty: Duty,
        next_duty: Duty
    ):
        """
        Identify factors that disrupt sleep quality
        
        Key insight: Legal ≠ Good sleep!
        """
        disruptions = []
        severity_scores = []
        
        # Get local times
        arrival_local = previous_duty.release_time_utc.astimezone(
            pytz.timezone(rest.location_timezone)
        )
        departure_local = next_duty.report_time_utc.astimezone(
            pytz.timezone(rest.location_timezone)
        )
        
        arrival_hour = arrival_local.hour
        departure_hour = departure_local.hour
        
        # 1. Quick turn (legal but tight)
        if rest.duration_hours < self.quick_turn_threshold:
            disruptions.append("Quick turn: Limited time for full sleep cycle")
            severity_scores.append(2)
            rest.sleep_disruption_type = SleepDisruptionType.QUICK_TURN
        
        # 2. Early report after late arrival
        # Example: Land 23:00, report 06:00 next day (7h rest)
        # Problem: By the time you get to hotel (00:00), need to wake at 04:00
        if arrival_hour >= self.late_night_hour and departure_hour <= self.early_morning_hour:
            disruptions.append(
                f"Late arrival ({arrival_hour:02d}:00) → Early report ({departure_hour:02d}:00): "
                f"Insufficient time for restorative sleep"
            )
            severity_scores.append(3)  # SEVERE
            rest.sleep_disruption_type = SleepDisruptionType.EARLY_REPORT_AFTER_LATE_ARRIVAL
        
        # 3. Late report after early arrival
        # Example: Land 06:00, report 23:00 same day (17h rest)
        # Problem: Arrived during normal sleep time, now need to stay up late
        elif arrival_hour <= self.early_morning_hour and departure_hour >= self.late_night_hour:
            disruptions.append(
                f"Early arrival ({arrival_hour:02d}:00) → Late report ({departure_hour:02d}:00): "
                f"Disrupted circadian rhythm (arrived during sleep time)"
            )
            severity_scores.append(2)  # MODERATE
            rest.sleep_disruption_type = SleepDisruptionType.LATE_REPORT_AFTER_EARLY_ARRIVAL
        
        # 4. Split sleep required
        # Example: 30h rest but departure at 14:00 means you might need sleep before AND after noon
        if rest.duration_hours > 24 and not (
            self.optimal_bedtime_start <= departure_hour <= 24 or
            0 <= departure_hour <= self.optimal_wake_end
        ):
            disruptions.append(
                f"Awkward timing may require split sleep pattern"
            )
            severity_scores.append(1)  # MINOR
            rest.sleep_disruption_type = SleepDisruptionType.SPLIT_SLEEP_REQUIRED
        
        # 5. Timezone adaptation issues
        if not rest.is_home_base:
            # Calculate timezone shift
            home_tz = pytz.timezone(previous_duty.home_base_timezone)
            local_tz = pytz.timezone(rest.location_timezone)
            
            ref_time = rest.start_utc
            home_offset = home_tz.localize(ref_time.replace(tzinfo=None)).utcoffset().total_seconds() / 3600
            local_offset = local_tz.localize(ref_time.replace(tzinfo=None)).utcoffset().total_seconds() / 3600
            
            tz_shift = abs(local_offset - home_offset)
            
            if tz_shift >= 4:
                disruptions.append(
                    f"Significant timezone shift ({tz_shift:.0f}h): Body clock misalignment"
                )
                severity_scores.append(2)
                rest.sleep_disruption_type = SleepDisruptionType.TIMEZONE_SHIFT
        
        # Determine overall severity
        if not severity_scores:
            rest.sleep_disruption_severity = "none"
        else:
            max_severity = max(severity_scores)
            if max_severity >= 3:
                rest.sleep_disruption_severity = "severe"
            elif max_severity >= 2:
                rest.sleep_disruption_severity = "moderate"
            else:
                rest.sleep_disruption_severity = "minor"
        
        rest.sleep_disruption_reasons = disruptions
    
    def _estimate_sleep_opportunities(
        self,
        rest: RestPeriod,
        previous_duty: Duty,
        next_duty: Duty
    ):
        """
        Estimate when sleep can actually occur
        
        Account for:
        - Hotel check-in time
        - Meals, shower, preparation
        - Optimal circadian timing
        """
        # Hotel transit time (if needed)
        if rest.requires_hotel:
            checkin_delay = 1.0  # 1 hour to get to hotel
            checkout_advance = 2.0  # 2 hours before report
        else:
            checkin_delay = 0.5  # 30 min to get home
            checkout_advance = 1.5  # 1.5 hours before report
        
        # Earliest possible sleep start
        sleep_earliest = rest.start_utc + timedelta(hours=checkin_delay)
        
        # Latest possible sleep end
        sleep_latest = rest.end_utc - timedelta(hours=checkout_advance)
        
        # Create sleep opportunity
        if sleep_latest > sleep_earliest:
            opportunity = SleepOpportunity(
                start_utc=sleep_earliest,
                end_utc=sleep_latest,
                location_timezone=rest.location_timezone,
                estimated_transit_before_minutes=int(checkin_delay * 60),
                estimated_prep_after_minutes=int(checkout_advance * 60)
            )
            
            # Assess circadian alignment
            sleep_start_local = opportunity.start_local
            sleep_start_hour = sleep_start_local.hour
            
            # Best: 22:00-02:00 start
            if self.optimal_bedtime_start <= sleep_start_hour <= 24:
                opportunity.circadian_alignment_score = 1.0
            elif 0 <= sleep_start_hour <= 2:
                opportunity.circadian_alignment_score = 0.9
            # OK: 20:00-22:00 or 02:00-04:00
            elif 20 <= sleep_start_hour < self.optimal_bedtime_start:
                opportunity.circadian_alignment_score = 0.7
            elif 2 < sleep_start_hour <= 4:
                opportunity.circadian_alignment_score = 0.6
            # Poor: Daytime sleep
            elif 8 <= sleep_start_hour <= 20:
                opportunity.circadian_alignment_score = 0.4
            # Terrible: Early morning (4-8)
            else:
                opportunity.circadian_alignment_score = 0.3
            
            rest.estimated_sleep_windows.append(opportunity)
            
            # Estimate effective sleep
            # Formula: practical_hours * circadian_alignment * environment_quality
            environment_quality = 0.9 if rest.is_home_base else 0.75
            rest.total_effective_sleep_hours = (
                opportunity.practical_sleep_hours *
                opportunity.circadian_alignment_score *
                environment_quality
            )
        else:
            # No sleep possible (illegal rest)
            rest.total_effective_sleep_hours = 0.0
    
    def _rate_sleep_quality(self, rest: RestPeriod):
        """
        Overall rating of sleep quality for this rest period
        """
        effective_sleep = rest.total_effective_sleep_hours
        severity = rest.sleep_disruption_severity
        
        # Base rating on sleep hours
        if effective_sleep >= 8:
            base_rating = "excellent"
        elif effective_sleep >= 7:
            base_rating = "good"
        elif effective_sleep >= 6:
            base_rating = "fair"
        elif effective_sleep >= 4:
            base_rating = "poor"
        else:
            base_rating = "critical"
        
        # Downgrade based on disruptions
        if severity == "severe":
            if base_rating == "excellent":
                base_rating = "fair"
            elif base_rating == "good":
                base_rating = "poor"
            elif base_rating == "fair":
                base_rating = "critical"
        elif severity == "moderate":
            if base_rating == "excellent":
                base_rating = "good"
            elif base_rating == "good":
                base_rating = "fair"
        
        rest.sleep_quality_rating = base_rating
    
    def generate_rest_report(self, rest: RestPeriod) -> str:
        """
        Human-readable report for a rest period
        """
        lines = []
        lines.append("=" * 70)
        lines.append(f"REST PERIOD ANALYSIS: {rest.rest_id}")
        lines.append("=" * 70)
        lines.append("")
        
        # Timing
        lines.append(f"Duration: {rest.duration_hours:.1f} hours")
        lines.append(f"Start:    {rest.start_local.strftime('%Y-%m-%d %H:%M %Z')}")
        lines.append(f"End:      {rest.end_local.strftime('%Y-%m-%d %H:%M %Z')}")
        lines.append(f"Location: {rest.location_airport.code} ({rest.location_timezone})")
        lines.append(f"Home base: {'Yes' if rest.is_home_base else 'No (layover)'}")
        lines.append("")
        
        # EASA Compliance
        lines.append("EASA COMPLIANCE:")
        lines.append(f"  Type: {rest.rest_type.value.upper()}")
        if rest.is_easa_compliant:
            lines.append(f"  Status: ✓ COMPLIANT")
        else:
            lines.append(f"  Status: ✗ NON-COMPLIANT")
            for violation in rest.easa_violations:
                lines.append(f"    - {violation}")
        lines.append(f"  Local nights: {rest.local_night_count}")
        lines.append("")
        
        # Sleep Disruptions
        lines.append("SLEEP DISRUPTION ANALYSIS:")
        lines.append(f"  Severity: {rest.sleep_disruption_severity.upper()}")
        if rest.sleep_disruption_reasons:
            for reason in rest.sleep_disruption_reasons:
                lines.append(f"    ⚠️  {reason}")
        else:
            lines.append(f"    ✓ No significant disruptions identified")
        lines.append("")
        
        # Sleep Opportunities
        lines.append("SLEEP OPPORTUNITY:")
        if rest.estimated_sleep_windows:
            for opp in rest.estimated_sleep_windows:
                lines.append(f"  Window: {opp.start_local.strftime('%H:%M')} - {opp.end_local.strftime('%H:%M')}")
                lines.append(f"  Opportunity: {opp.opportunity_hours:.1f}h")
                lines.append(f"  Practical sleep: {opp.practical_sleep_hours:.1f}h")
                lines.append(f"  Circadian alignment: {opp.circadian_alignment_score:.0%}")
        else:
            lines.append(f"  ✗ No sleep opportunity (insufficient rest)")
        lines.append("")
        
        # Overall Rating
        lines.append("OVERALL SLEEP QUALITY:")
        emoji_map = {
            "excellent": "🟢",
            "good": "🟡",
            "fair": "🟠",
            "poor": "🔴",
            "critical": "🔴"
        }
        emoji = emoji_map.get(rest.sleep_quality_rating, "❓")
        lines.append(f"  {emoji} {rest.sleep_quality_rating.upper()}")
        lines.append(f"  Estimated effective sleep: {rest.total_effective_sleep_hours:.1f}h")
        lines.append("")
        
        return "\n".join(lines)
