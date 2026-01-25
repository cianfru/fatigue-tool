"""
enhanced_models.py - Improved Data Models for User-Facing Features
===================================================================

Key improvements:
1. OFF days as explicit entities (not just gaps)
2. User-editable sleep windows
3. Better sleep/wake visualization
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Optional, Dict
from enum import Enum
import pytz

from data_models import Airport, FlightSegment, SleepBlock


class DayType(Enum):
    """Type of day in roster"""
    DUTY = "duty"           # Flying day
    OFF = "off"             # Rest day
    STANDBY = "standby"     # On standby
    GROUND = "ground"       # Ground duty (sim, training)


@dataclass
class SleepWindow:
    """
    User-editable sleep window
    
    This is what the user sees and can modify in the UI
    """
    # Timing
    start_utc: datetime
    end_utc: datetime
    location_timezone: str
    
    # Classification
    window_type: str = "automatic"  # "automatic", "user_edited", "off_day"
    environment: str = "home"       # "home", "hotel", "layover"
    
    # User can override these
    user_specified_duration_hours: Optional[float] = None
    user_specified_quality: Optional[float] = None
    user_notes: str = ""
    
    # Computed (from BiomathematicalSleepEstimator)
    estimated_sleep_obtained_hours: float = 0.0
    quality_factor: float = 0.8
    effective_sleep_hours: float = 0.0
    
    @property
    def start_local(self) -> datetime:
        """Local time at sleep location"""
        tz = pytz.timezone(self.location_timezone)
        return self.start_utc.astimezone(tz)
    
    @property
    def end_local(self) -> datetime:
        tz = pytz.timezone(self.location_timezone)
        return self.end_utc.astimezone(tz)
    
    @property
    def opportunity_hours(self) -> float:
        """Total opportunity window (bed time available)"""
        return (self.end_utc - self.start_utc).total_seconds() / 3600
    
    @property
    def display_summary(self) -> str:
        """Human-readable summary for UI"""
        start = self.start_local.strftime("%H:%M")
        end = self.end_local.strftime("%H:%M") 
        effective = self.effective_sleep_hours
        
        emoji = "🏠" if self.environment == "home" else "🏨"
        
        return f"{emoji} {start}-{end} → {effective:.1f}h effective sleep"
    
    def to_sleep_block(self) -> SleepBlock:
        """Convert to SleepBlock for fatigue model"""
        return SleepBlock(
            start_utc=self.start_utc,
            end_utc=self.end_utc,
            location_timezone=self.location_timezone,
            duration_hours=self.user_specified_duration_hours or self.estimated_sleep_obtained_hours,
            quality_factor=self.user_specified_quality or self.quality_factor,
            effective_sleep_hours=self.effective_sleep_hours,
            environment=self.environment
        )


@dataclass
class RosterDay:
    """
    Single day in roster (duty, off, standby, etc)
    
    This is the fundamental unit users see:
    - Jan 15: DUTY (DOH-LHR)
    - Jan 16: OFF
    - Jan 17: OFF
    - Jan 18: DUTY (LHR-DOH)
    """
    date: datetime
    day_type: DayType
    
    # If DUTY day
    duty_id: Optional[str] = None
    report_time_utc: Optional[datetime] = None
    release_time_utc: Optional[datetime] = None
    segments: List[FlightSegment] = field(default_factory=list)
    
    # If OFF day
    location_timezone: str = "UTC"  # Where are you on this off day?
    
    # Sleep during this day/night
    sleep_windows: List[SleepWindow] = field(default_factory=list)
    
    @property
    def date_local_str(self) -> str:
        """Formatted date string"""
        return self.date.strftime("%Y-%m-%d (%a)")
    
    @property
    def is_duty(self) -> bool:
        return self.day_type == DayType.DUTY
    
    @property
    def is_off(self) -> bool:
        return self.day_type == DayType.OFF
    
    @property
    def summary_line(self) -> str:
        """One-line summary for display"""
        date_str = self.date.strftime("%b %d")
        
        if self.is_duty:
            if self.segments:
                route = f"{self.segments[0].departure_airport.code}→{self.segments[-1].arrival_airport.code}"
                return f"{date_str}: DUTY ({route})"
            return f"{date_str}: DUTY"
        elif self.is_off:
            return f"{date_str}: OFF"
        else:
            return f"{date_str}: {self.day_type.value.upper()}"
    
    def get_total_sleep_hours(self) -> float:
        """Sum of effective sleep in all windows"""
        return sum(w.effective_sleep_hours for w in self.sleep_windows)


@dataclass
class EnhancedRoster:
    """
    Roster with explicit day-by-day structure
    
    Much easier for users to understand:
    - Shows every day (duties AND offs)
    - Sleep windows clearly visible
    - Easy to modify
    """
    roster_id: str
    pilot_id: str
    month: str
    home_base_timezone: str
    
    # Day-by-day representation
    days: List[RosterDay] = field(default_factory=list)
    
    # Configuration
    typical_sleep_need_hours: float = 8.0
    typical_bedtime_local: str = "23:00"  # User's usual bedtime
    typical_wake_time_local: str = "07:00"  # User's usual wake time
    
    def add_duty_day(
        self,
        date: datetime,
        duty_id: str,
        report_time_utc: datetime,
        release_time_utc: datetime,
        segments: List[FlightSegment]
    ):
        """Add a duty day"""
        day = RosterDay(
            date=date,
            day_type=DayType.DUTY,
            duty_id=duty_id,
            report_time_utc=report_time_utc,
            release_time_utc=release_time_utc,
            segments=segments,
            location_timezone=segments[-1].arrival_airport.timezone if segments else self.home_base_timezone
        )
        self.days.append(day)
    
    def add_off_day(self, date: datetime, location_timezone: str = None):
        """Add an OFF day"""
        day = RosterDay(
            date=date,
            day_type=DayType.OFF,
            location_timezone=location_timezone or self.home_base_timezone
        )
        self.days.append(day)
    
    def auto_generate_sleep_windows(self):
        """
        Automatically create sleep windows based on duty gaps
        
        This is what the current code does, but now it's VISIBLE
        and EDITABLE by the user
        """
        self.days.sort(key=lambda d: d.date)
        
        for i in range(len(self.days)):
            current_day = self.days[i]
            
            if current_day.is_off:
                # OFF day: Assume normal sleep pattern
                self._add_off_day_sleep(current_day)
            
            elif current_day.is_duty:
                # After duty release: When can you sleep?
                if i + 1 < len(self.days):
                    next_day = self.days[i + 1]
                    self._add_post_duty_sleep(current_day, next_day)
    
    def _add_off_day_sleep(self, day: RosterDay):
        """Add typical sleep for OFF day"""
        # Parse typical bedtime/wake time
        bed_hour, bed_min = map(int, self.typical_bedtime_local.split(':'))
        wake_hour, wake_min = map(int, self.typical_wake_time_local.split(':'))
        
        # Sleep window: bedtime on this day to wake time next day
        tz = pytz.timezone(day.location_timezone)
        
        # If bedtime is before midnight
        if bed_hour < 12:
            sleep_start = tz.localize(datetime(
                day.date.year, day.date.month, day.date.day,
                bed_hour, bed_min
            ))
        else:
            sleep_start = tz.localize(datetime(
                day.date.year, day.date.month, day.date.day,
                bed_hour, bed_min
            ))
        
        sleep_end = sleep_start + timedelta(hours=self.typical_sleep_need_hours)
        
        window = SleepWindow(
            start_utc=sleep_start.astimezone(pytz.utc),
            end_utc=sleep_end.astimezone(pytz.utc),
            location_timezone=day.location_timezone,
            window_type="automatic",
            environment="home" if day.location_timezone == self.home_base_timezone else "layover",
            estimated_sleep_obtained_hours=self.typical_sleep_need_hours,
            quality_factor=0.9 if day.location_timezone == self.home_base_timezone else 0.75,
            effective_sleep_hours=self.typical_sleep_need_hours * 0.9
        )
        
        day.sleep_windows.append(window)
    
    def _add_post_duty_sleep(self, current_day: RosterDay, next_day: RosterDay):
        """Add sleep between duty release and next event"""
        
        # Sleep starts: 1h after release (travel to hotel)
        sleep_start = current_day.release_time_utc + timedelta(hours=1)
        
        # Sleep ends: 2h before next report (if duty) or normal wake time (if off)
        if next_day.is_duty:
            sleep_end = next_day.report_time_utc - timedelta(hours=2)
        else:
            # Next day is OFF: sleep until normal wake time
            wake_hour, wake_min = map(int, self.typical_wake_time_local.split(':'))
            tz = pytz.timezone(current_day.location_timezone)
            wake_time = tz.localize(datetime(
                next_day.date.year, next_day.date.month, next_day.date.day,
                wake_hour, wake_min
            ))
            sleep_end = wake_time.astimezone(pytz.utc)
        
        if sleep_end <= sleep_start:
            return  # No sleep opportunity (quick turn)
        
        opportunity_hours = (sleep_end - sleep_start).total_seconds() / 3600
        
        # Estimate actual sleep (user can override)
        is_home = (current_day.location_timezone == self.home_base_timezone)
        quality = 0.9 if is_home else 0.75
        
        # Realistic sleep: can't sleep entire opportunity window
        if opportunity_hours > 10:
            actual_sleep = min(9, opportunity_hours * 0.85)
        else:
            actual_sleep = opportunity_hours * 0.85
        
        window = SleepWindow(
            start_utc=sleep_start,
            end_utc=sleep_end,
            location_timezone=current_day.location_timezone,
            window_type="automatic",
            environment="home" if is_home else "layover",
            estimated_sleep_obtained_hours=actual_sleep,
            quality_factor=quality,
            effective_sleep_hours=actual_sleep * quality
        )
        
        current_day.sleep_windows.append(window)
    
    def get_summary(self) -> Dict:
        """Roster summary for display"""
        total_days = len(self.days)
        duty_days = sum(1 for d in self.days if d.is_duty)
        off_days = sum(1 for d in self.days if d.is_off)
        
        total_sleep = sum(d.get_total_sleep_hours() for d in self.days)
        avg_sleep = total_sleep / total_days if total_days > 0 else 0
        
        return {
            'total_days': total_days,
            'duty_days': duty_days,
            'off_days': off_days,
            'total_sleep_hours': total_sleep,
            'average_sleep_per_day': avg_sleep
        }
    
    def export_for_analysis(self):
        """
        Convert to old Roster format for backward compatibility
        with existing fatigue model
        """
        from data_models import Duty, Roster
        
        duties = []
        for day in self.days:
            if day.is_duty:
                duty = Duty(
                    duty_id=day.duty_id,
                    date=day.date,
                    report_time_utc=day.report_time_utc,
                    release_time_utc=day.release_time_utc,
                    segments=day.segments,
                    home_base_timezone=self.home_base_timezone
                )
                duties.append(duty)
        
        return Roster(
            roster_id=self.roster_id,
            pilot_id=self.pilot_id,
            month=self.month,
            duties=duties,
            home_base_timezone=self.home_base_timezone
        )
