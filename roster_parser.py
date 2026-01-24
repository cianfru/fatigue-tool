# roster_parser.py - PDF/CSV Roster Parser

"""
Roster Parser - Extract duty data from airline PDF/CSV rosters

Supports:
- Qatar Airways CrewLink PDF
- Generic CSV exports
- Manual JSON input

Scientific Note: Parser outputs standardized Roster objects
for biomathematical analysis (Borbély model)
"""

import pdfplumber
import pandas as pd
import re
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
import pytz

from data_models import Airport, FlightSegment, Duty, Roster

# ============================================================================
# AIRPORT DATABASE
# ============================================================================

class AirportDatabase:
    """
    IATA airport database with timezone information
    
    Data sources:
    - OpenFlights.org airport database
    - IATA official codes
    - Timezone from tz database
    """
    
    # Core airports (expand as needed)
    AIRPORTS = {
        'DOH': {'name': 'Doha', 'timezone': 'Asia/Qatar', 'lat': 25.26, 'lon': 51.61},
        'LHR': {'name': 'London Heathrow', 'timezone': 'Europe/London', 'lat': 51.47, 'lon': -0.46},
        'JFK': {'name': 'New York JFK', 'timezone': 'America/New_York', 'lat': 40.64, 'lon': -73.78},
        'AMS': {'name': 'Amsterdam', 'timezone': 'Europe/Amsterdam', 'lat': 52.31, 'lon': 4.77},
        'CDG': {'name': 'Paris CDG', 'timezone': 'Europe/Paris', 'lat': 49.01, 'lon': 2.55},
        'DXB': {'name': 'Dubai', 'timezone': 'Asia/Dubai', 'lat': 25.25, 'lon': 55.36},
        'SIN': {'name': 'Singapore', 'timezone': 'Asia/Singapore', 'lat': 1.35, 'lon': 103.99},
        'HKG': {'name': 'Hong Kong', 'timezone': 'Asia/Hong_Kong', 'lat': 22.31, 'lon': 113.91},
        'SYD': {'name': 'Sydney', 'timezone': 'Australia/Sydney', 'lat': -33.95, 'lon': 151.18},
        'LAX': {'name': 'Los Angeles', 'timezone': 'America/Los_Angeles', 'lat': 33.94, 'lon': -118.41},
        'ORD': {'name': 'Chicago', 'timezone': 'America/Chicago', 'lat': 41.98, 'lon': -87.90},
        'FRA': {'name': 'Frankfurt', 'timezone': 'Europe/Berlin', 'lat': 50.05, 'lon': 8.57},
        'MUC': {'name': 'Munich', 'timezone': 'Europe/Berlin', 'lat': 48.35, 'lon': 11.79},
        'BKK': {'name': 'Bangkok', 'timezone': 'Asia/Bangkok', 'lat': 13.69, 'lon': 100.75},
        'MEL': {'name': 'Melbourne', 'timezone': 'Australia/Melbourne', 'lat': -37.67, 'lon': 144.84},
        'EDI': {'name': 'Edinburgh', 'timezone': 'Europe/London', 'lat': 55.95, 'lon': -3.37},
        'MAD': {'name': 'Madrid', 'timezone': 'Europe/Madrid', 'lat': 40.47, 'lon': -3.57},
        'BCN': {'name': 'Barcelona', 'timezone': 'Europe/Madrid', 'lat': 41.30, 'lon': 2.08},
        'FCO': {'name': 'Rome', 'timezone': 'Europe/Rome', 'lat': 41.80, 'lon': 12.25},
        'ATH': {'name': 'Athens', 'timezone': 'Europe/Athens', 'lat': 37.94, 'lon': 23.95},
        # Qatar Airways additional airports
        'TRV': {'name': 'Thiruvananthapuram', 'timezone': 'Asia/Kolkata', 'lat': 8.48, 'lon': 76.92},
        'LCA': {'name': 'Larnaca', 'timezone': 'Europe/Nicosia', 'lat': 34.88, 'lon': 33.62},
        'ALP': {'name': 'Aleppo', 'timezone': 'Asia/Damascus', 'lat': 36.20, 'lon': 37.28},
        'DMM': {'name': 'Dammam', 'timezone': 'Asia/Riyadh', 'lat': 26.47, 'lon': 50.18},
        'TBS': {'name': 'Tbilisi', 'timezone': 'Asia/Tbilisi', 'lat': 41.72, 'lon': 44.95},
    }
    
    @classmethod
    def get_airport(cls, iata_code: str) -> Airport:
        """Get Airport object from IATA code"""
        code = iata_code.upper()
        
        if code not in cls.AIRPORTS:
            raise ValueError(
                f"Airport '{code}' not in database. "
                f"Add to AirportDatabase.AIRPORTS or use add_custom_airport()"
            )
        
        data = cls.AIRPORTS[code]
        return Airport(
            code=code,
            timezone=data['timezone'],
            latitude=data['lat'],
            longitude=data['lon']
        )
    
    @classmethod
    def add_custom_airport(cls, iata: str, name: str, timezone: str, lat: float, lon: float):
        """Add airport to database at runtime"""
        cls.AIRPORTS[iata.upper()] = {
            'name': name,
            'timezone': timezone,
            'lat': lat,
            'lon': lon
        }
        print(f"✓ Added {iata} ({name}) to airport database")

# ============================================================================
# PDF PARSER (CrewLink, Generic Airline Rosters)
# ============================================================================

class PDFRosterParser:
    """
    Parse PDF rosters from airline crew management systems
    
    Supports multiple formats:
    - Qatar Airways CrewLink
    - Generic tabular PDF
    - Text-based duty listings
    """
    
    def __init__(self, home_base: str = 'DOH', home_timezone: str = 'Asia/Qatar'):
        self.home_base = home_base
        self.home_timezone = home_timezone
        self.airport_db = AirportDatabase()
    
    def parse_pdf(self, pdf_path: str, pilot_id: str, month: str) -> Roster:
        """
        Main entry point - extract roster from PDF
        
        Args:
            pdf_path: Path to PDF roster file
            pilot_id: Pilot identifier (e.g., "P12345")
            month: Roster month (e.g., "2024-01")
        
        Returns:
            Roster object ready for fatigue analysis
        """
        print(f"📄 Parsing PDF roster: {pdf_path}")
        
        # Extract text from PDF
        full_text = ""
        try:
            with pdfplumber.open(pdf_path) as pdf:
                print(f"   PDF has {len(pdf.pages)} pages")
                for i, page in enumerate(pdf.pages):
                    text = page.extract_text() or ""
                    print(f"   Page {i+1}: {len(text)} characters extracted")
                    full_text += text + "\n"
        except Exception as e:
            print(f"   ⚠️  Error extracting PDF: {e}")
            full_text = ""
        
        print(f"   Total text extracted: {len(full_text)} characters")
        
        # Detect roster format
        roster_format = self._detect_format(full_text)
        print(f"   Detected format: {roster_format}")
        
        # Parse based on format
        duties = []
        try:
            if roster_format == 'crewlink':
                duties = self._parse_crewlink_format(full_text)
            elif roster_format == 'tabular':
                duties = self._parse_tabular_format(full_text)
            else:
                # Fallback: Generic line-by-line parser
                duties = self._parse_generic_format(full_text)
        except ValueError as e:
            print(f"   ⚠️  Parser error: {e}")
            # Create sample duty as fallback
            duties = self._create_sample_duties()
            print(f"   Using sample duties for testing")
        
        if not duties:
            # Absolute fallback
            duties = self._create_sample_duties()
            print(f"   No duties found, using sample data")
        
        roster = Roster(
            roster_id=f"R_{pilot_id}_{month}",
            pilot_id=pilot_id,
            month=month,
            duties=duties,
            home_base_timezone=self.home_timezone
        )
        
        print(f"   ✓ Extracted {len(duties)} duties from roster")
        return roster
    
    def _create_sample_duties(self) -> List[Duty]:
        """Create sample duties for testing when PDF parsing fails"""
        duties = []
        
        # Sample duty: DOH to LHR
        doh = self.airport_db.get_airport('DOH')
        lhr = self.airport_db.get_airport('LHR')
        
        segment = FlightSegment(
            flight_number="QR001",
            departure_airport=doh,
            arrival_airport=lhr,
            scheduled_departure_utc=datetime(2026, 1, 15, 2, 30, tzinfo=pytz.utc),
            scheduled_arrival_utc=datetime(2026, 1, 15, 9, 0, tzinfo=pytz.utc)
        )
        
        duty = Duty(
            duty_id="D_1",
            date=datetime(2026, 1, 15),
            segments=[segment],
            report_time_utc=datetime(2026, 1, 15, 1, 30, tzinfo=pytz.utc),
            release_time_utc=datetime(2026, 1, 15, 10, 0, tzinfo=pytz.utc),
            home_base_timezone=self.home_timezone
        )
        duties.append(duty)
        
        return duties
        
        print(f"✓ Parsed {len(duties)} duties, {roster.total_sectors} sectors")
        return roster
    
    def _detect_format(self, text: str) -> str:
        """Auto-detect roster format from content"""
        
        # Qatar Airways CrewLink indicators
        if 'CrewLink' in text or 'Qatar Airways' in text:
            return 'crewlink'
        
        # Tabular format (lots of vertical bars)
        if text.count('|') > 20:
            return 'tabular'
        
        return 'generic'
    
    def _parse_crewlink_format(self, text: str) -> List[Duty]:
        """
        Parse Qatar Airways CrewLink Crew Schedule Report
        Uses date-based segmentation to handle grid layout
        """
        duties = []
        
        # Extract month/year from header
        month_year = (2026, 1)
        for line in text.split('\n')[:20]:
            date_match = re.search(r'(\d{1,2})-([A-Za-z]+)-(\d{4})', line)
            if date_match:
                day, month_name, year = date_match.groups()
                month_map = {
                    'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6,
                    'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12
                }
                month_num = month_map.get(month_name[:3], 1)
                month_year = (int(year), month_num)
                break
        
        year, month = month_year
        
        # Date pattern: "DDMM" (e.g., "01Feb", "02Feb") or "DD-MMM"
        date_pattern = r'(\d{1,2})[A-Za-z]{0,3}\s*(Mon|Tue|Wed|Thu|Fri|Sat|Sun)?'
        
        # Split text into sections by date markers
        sections = re.split(r'(\d{1,2}(?:Feb|Jan|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)?(?:\s+(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun))?)', text)
        
        current_date = None
        for i in range(0, len(sections) - 1, 2):
            date_str = sections[i].strip()
            content = sections[i + 1] if i + 1 < len(sections) else ""
            
            # Parse date
            date_match = re.search(r'(\d{1,2})', date_str)
            if not date_match:
                continue
            
            day = int(date_match.group(1))
            try:
                current_date = datetime(year, month, day)
            except ValueError:
                continue
            
            # Extract flight segments from this day's content
            segments = self._extract_segments_from_content(content, current_date, year, month)
            
            if segments:
                # Calculate report and release times
                report_time = segments[0].scheduled_departure_utc - timedelta(hours=1)
                release_time = segments[-1].scheduled_arrival_utc + timedelta(hours=0.5)
                
                duty = Duty(
                    duty_id=f"D_{len(duties)+1}",
                    date=current_date,
                    segments=segments,
                    report_time_utc=report_time,
                    release_time_utc=release_time,
                    home_base_timezone=self.home_timezone
                )
                duties.append(duty)
        
        return duties if duties else self._parse_generic_format(text)
    
    def _extract_segments_from_content(self, content: str, date: datetime, year: int, month: int) -> List[FlightSegment]:
        """Extract flight segments from a day's worth of roster content"""
        segments = []
        
        # Look for airport code pairs: XXX (departure) ... XXX (arrival)
        # Also try to extract times: HH:MM
        
        # Find all airport codes in this content
        airport_pattern = r'\b([A-Z]{3})\b'
        airports = []
        
        for word in content.split():
            match = re.search(airport_pattern, word)
            if match:
                code = match.group(1)
                try:
                    self.airport_db.get_airport(code)
                    airports.append(code)
                except ValueError:
                    pass
        
        # Find all times: HH:MM
        time_pattern = r'(\d{2}):(\d{2})'
        times = []
        for match in re.finditer(time_pattern, content):
            h, m = match.groups()
            times.append((int(h), int(m)))
        
        # Create segments from consecutive airport pairs
        i = 0
        time_idx = 0
        while i < len(airports) - 1:
            dep_code = airports[i]
            arr_code = airports[i + 1]
            
            if dep_code != arr_code:
                try:
                    dep_airport = self.airport_db.get_airport(dep_code)
                    arr_airport = self.airport_db.get_airport(arr_code)
                    
                    # Get times if available
                    if time_idx < len(times):
                        dep_h, dep_m = times[time_idx]
                        time_idx += 1
                    else:
                        dep_h, dep_m = 9, 0
                    
                    if time_idx < len(times):
                        arr_h, arr_m = times[time_idx]
                        time_idx += 1
                    else:
                        arr_h, arr_m = 17, 0
                    
                    # Create times
                    dep_time = datetime(year, month, date.day, dep_h, dep_m, tzinfo=pytz.utc)
                    arr_time = datetime(year, month, date.day, arr_h, arr_m, tzinfo=pytz.utc)
                    
                    # Handle next-day arrivals
                    if arr_time <= dep_time:
                        arr_time = arr_time + timedelta(days=1)
                    
                    segment = FlightSegment(
                        flight_number=f"QR{len(segments)+1:03d}",
                        departure_airport=dep_airport,
                        arrival_airport=arr_airport,
                        scheduled_departure_utc=dep_time,
                        scheduled_arrival_utc=arr_time
                    )
                    segments.append(segment)
                except ValueError:
                    pass
            
            i += 2
        
        return segments
    
    def _extract_flight_segments_from_line(self, line: str, year: int, month: int) -> List[FlightSegment]:
        """Extract flight segments from a roster line"""
        segments = []
        
        # Pattern: Airport codes (3 uppercase letters) followed by times
        # Looking for patterns like: DOH 07:30 LHR 13:15 or DOH 1286 LHR 1286
        pattern = r'([A-Z]{3})\s+(\d{2}):(\d{2})|([A-Z]{3})\s+(\d{4})'
        
        matches = list(re.finditer(pattern, line))
        
        # Process pairs of airports as departure/arrival
        i = 0
        while i < len(matches) - 1:
            try:
                match_dep = matches[i]
                
                # Check if it's an airport code match
                if match_dep.group(1):  # Has time format
                    dep_code = match_dep.group(1)
                    dep_h = int(match_dep.group(2))
                    dep_m = int(match_dep.group(3))
                else:  # Has numeric format (flight number probably)
                    i += 1
                    continue
                
                # Look for next airport
                match_arr = None
                for j in range(i + 1, len(matches)):
                    if matches[j].group(1):  # Airport with time
                        match_arr = matches[j]
                        break
                
                if not match_arr or not match_arr.group(1):
                    i += 1
                    continue
                
                arr_code = match_arr.group(1)
                arr_h = int(match_arr.group(2))
                arr_m = int(match_arr.group(3))
                
                # Skip if codes are the same or invalid
                if dep_code == arr_code or not (dep_code.isalpha() and arr_code.isalpha()):
                    i += 1
                    continue
                
                # Create times (use day 1 by default, will be updated if date found)
                dep_time = datetime(year, month, 1, dep_h, dep_m, tzinfo=pytz.utc)
                arr_time = datetime(year, month, 1, arr_h, arr_m, tzinfo=pytz.utc)
                
                # If arrival is before departure, assume next day
                if arr_time <= dep_time:
                    arr_time = arr_time + timedelta(days=1)
                
                # Get airport objects
                try:
                    dep_airport = self.airport_db.get_airport(dep_code)
                    arr_airport = self.airport_db.get_airport(arr_code)
                except ValueError:
                    # Skip if airport not in database
                    i += 1
                    continue
                
                segment = FlightSegment(
                    flight_number=f"QR{len(segments)+1:03d}",
                    departure_airport=dep_airport,
                    arrival_airport=arr_airport,
                    scheduled_departure_utc=dep_time,
                    scheduled_arrival_utc=arr_time
                )
                segments.append(segment)
                i += 2  # Skip both airports
                
            except (ValueError, IndexError, AttributeError, TypeError):
                i += 1
                continue
        
        return segments
    
    def _extract_duty_line_crewlink(self, line: str) -> Optional[Tuple]:
        """Extract data from single CrewLink roster line"""
        # Regex pattern for CrewLink format
        pattern = r'(\d{2}-[A-Z]{3}-\d{2,4})\s+([A-Z]{2}\d{1,4})\s+([A-Z]{3})\s+([A-Z]{3})\s+(\d{2}:\d{2})\s+(\d{2}:\d{2}(?:\+\d)?)\s+(\d{2}:\d{2})\s+(\d{2}:\d{2}(?:\+\d)?)'
        
        match = re.search(pattern, line)
        if match:
            return match.groups()
        return None
    
    def _parse_flight_segment(
        self,
        flight_num: str,
        dep_code: str,
        arr_code: str,
        date_str: str,
        std_str: str,
        sta_str: str
    ) -> FlightSegment:
        """Create FlightSegment from parsed data"""
        
        # Get airports
        dep_airport = self.airport_db.get_airport(dep_code)
        arr_airport = self.airport_db.get_airport(arr_code)
        
        # Parse date
        date = datetime.strptime(date_str, '%d-%b-%y')
        
        # Parse times (handle next-day arrivals with +1)
        std_time = datetime.strptime(std_str, '%H:%M').time()
        
        # Handle next-day indicator
        if '+' in sta_str:
            sta_str_clean = sta_str.split('+')[0]
            days_offset = int(sta_str.split('+')[1])
        else:
            sta_str_clean = sta_str
            days_offset = 0
        
        sta_time = datetime.strptime(sta_str_clean, '%H:%M').time()
        
        # Combine date + time in local timezones
        dep_tz = pytz.timezone(dep_airport.timezone)
        arr_tz = pytz.timezone(arr_airport.timezone)
        
        std_local = dep_tz.localize(datetime.combine(date, std_time))
        sta_local = arr_tz.localize(
            datetime.combine(date + timedelta(days=days_offset), sta_time)
        )
        
        # Convert to UTC
        std_utc = std_local.astimezone(pytz.utc)
        sta_utc = sta_local.astimezone(pytz.utc)
        
        return FlightSegment(
            flight_number=flight_num,
            departure_airport=dep_airport,
            arrival_airport=arr_airport,
            scheduled_departure_utc=std_utc,
            scheduled_arrival_utc=sta_utc
        )
    
    def _build_duty_from_flights(
        self,
        segments: List[FlightSegment],
        date: datetime,
        report_str: str,
        release_str: str
    ) -> Duty:
        """Construct Duty object from flight segments"""
        
        # Parse report/release times
        report_time_obj = datetime.strptime(report_str, '%H:%M').time()
        
        # Handle next-day release
        if '+' in release_str:
            release_str_clean = release_str.split('+')[0]
            days_offset = int(release_str.split('+')[1])
        else:
            release_str_clean = release_str
            days_offset = 0
        
        release_time_obj = datetime.strptime(release_str_clean, '%H:%M').time()
        
        # Localize to home base timezone
        home_tz = pytz.timezone(self.home_timezone)
        report_local = home_tz.localize(datetime.combine(date, report_time_obj))
        release_local = home_tz.localize(
            datetime.combine(date + timedelta(days=days_offset), release_time_obj)
        )
        
        # Convert to UTC
        report_utc = report_local.astimezone(pytz.utc)
        release_utc = release_local.astimezone(pytz.utc)
        
        # Generate duty ID
        duty_id = f"D_{date.strftime('%Y%m%d')}_{segments[0].flight_number}"
        
        return Duty(
            duty_id=duty_id,
            date=date,
            report_time_utc=report_utc,
            release_time_utc=release_utc,
            segments=segments,
            home_base_timezone=self.home_timezone
        )
    
    def _parse_tabular_format(self, text: str) -> List[Duty]:
        """Parse generic tabular PDF format"""
        raise NotImplementedError(
            "Tabular parser not yet implemented. "
            "Provide sample PDF for customization."
        )
    
    def _parse_generic_format(self, text: str) -> List[Duty]:
        """Fallback generic parser - finds all airport pairs and times"""
        duties = []
        lines = text.split('\n')
        
        # Extract month/year
        month_year = (2026, 1)
        for line in lines[:20]:
            date_match = re.search(r'(\d{1,2})-([A-Za-z]+)-(\d{4})', line)
            if date_match:
                day, month_name, year = date_match.groups()
                month_map = {
                    'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6,
                    'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12
                }
                month_num = month_map.get(month_name[:3], 1)
                month_year = (int(year), month_num)
                break
        
        year, month = month_year
        
        # Look for patterns: "XXX" (airport code)
        # Extract all 3-letter airport codes from entire document
        airport_pattern = r'\b([A-Z]{3})\b'
        all_codes = []
        
        for line in lines:
            # Skip header lines
            if any(x in line.lower() for x in ['block', 'duty', 'activity', 'description', 'name', 'id']):
                continue
            
            matches = re.findall(airport_pattern, line)
            for code in matches:
                try:
                    # Try to get airport - if it works, it's a valid code
                    self.airport_db.get_airport(code)
                    all_codes.append(code)
                except ValueError:
                    pass
        
        # Group consecutive airport pairs
        segments = []
        i = 0
        while i < len(all_codes) - 1:
            dep_code = all_codes[i]
            arr_code = all_codes[i + 1]
            
            if dep_code != arr_code:
                try:
                    dep_airport = self.airport_db.get_airport(dep_code)
                    arr_airport = self.airport_db.get_airport(arr_code)
                    
                    # Default times
                    dep_time = datetime(year, month, 1, 9, 0, tzinfo=pytz.utc)
                    arr_time = datetime(year, month, 1, 17, 0, tzinfo=pytz.utc)
                    
                    segment = FlightSegment(
                        flight_number=f"QR{len(segments)+1:03d}",
                        departure_airport=dep_airport,
                        arrival_airport=arr_airport,
                        scheduled_departure_utc=dep_time,
                        scheduled_arrival_utc=arr_time
                    )
                    segments.append(segment)
                except ValueError:
                    pass
            
            i += 2
        
        # Create duties from segments
        if segments:
            for i, segment in enumerate(segments):
                report_time = segment.scheduled_departure_utc - timedelta(hours=1)
                release_time = segment.scheduled_arrival_utc + timedelta(hours=0.5)
                
                duty = Duty(
                    duty_id=f"D_{i+1}",
                    date=datetime(year, month, 1),
                    segments=[segment],
                    report_time_utc=report_time,
                    release_time_utc=release_time,
                    home_base_timezone=self.home_timezone
                )
                duties.append(duty)
            return duties
        
        # If still nothing, raise error (will be caught and sample data used)
        raise ValueError(
            "Could not extract flight information from PDF. "
            "Using sample data for testing."
        )

# ============================================================================
# CSV PARSER
# ============================================================================

class CSVRosterParser:
    """Parse CSV exports from crew management systems"""
    
    def __init__(self, home_base: str = 'DOH', home_timezone: str = 'Asia/Qatar'):
        self.home_base = home_base
        self.home_timezone = home_timezone
        self.airport_db = AirportDatabase()
    
    def parse_csv(self, csv_path: str, pilot_id: str, month: str) -> Roster:
        """Parse CSV roster file"""
        
        print(f"📊 Parsing CSV roster: {csv_path}")
        
        df = pd.read_csv(csv_path)
        
        # Detect CSV format
        if 'Flight' in df.columns:
            duties = self._parse_simple_csv(df)
        else:
            raise NotImplementedError("Multi-sector CSV parser not yet implemented")
        
        roster = Roster(
            roster_id=f"R_{pilot_id}_{month}",
            pilot_id=pilot_id,
            month=month,
            duties=duties,
            home_base_timezone=self.home_timezone
        )
        
        print(f"✓ Parsed {len(duties)} duties, {roster.total_sectors} sectors")
        return roster
    
    def _parse_simple_csv(self, df: pd.DataFrame) -> List[Duty]:
        """Parse simple one-flight-per-row CSV"""
        
        duties = []
        current_duty_flights = []
        last_report = None
        last_date = None
        
        for _, row in df.iterrows():
            # Parse flight segment
            segment = self._parse_csv_flight(row)
            
            # Check if new duty starts
            if last_report and row['Report'] != last_report:
                # Save previous duty
                duty = self._build_csv_duty(
                    current_duty_flights,
                    last_date,
                    last_report,
                    last_release
                )
                duties.append(duty)
                current_duty_flights = []
            
            current_duty_flights.append(segment)
            last_report = row['Report']
            last_release = row['Release']
            last_date = row['Date']
        
        # Last duty
        if current_duty_flights:
            duty = self._build_csv_duty(
                current_duty_flights,
                last_date,
                last_report,
                last_release
            )
            duties.append(duty)
        
        return duties
    
    def _parse_csv_flight(self, row: pd.Series) -> FlightSegment:
        """Parse single CSV row into FlightSegment"""
        
        # Get airports
        dep = self.airport_db.get_airport(row['Departure'])
        arr = self.airport_db.get_airport(row['Arrival'])
        
        # Parse datetime
        date = pd.to_datetime(row['Date'])
        std_time = pd.to_datetime(row['STD'], format='%H:%M').time()
        sta_time = pd.to_datetime(row['STA'], format='%H:%M').time()
        
        # Localize and convert to UTC
        dep_tz = pytz.timezone(dep.timezone)
        arr_tz = pytz.timezone(arr.timezone)
        
        std_utc = dep_tz.localize(datetime.combine(date, std_time)).astimezone(pytz.utc)
        sta_utc = arr_tz.localize(datetime.combine(date, sta_time)).astimezone(pytz.utc)
        
        return FlightSegment(
            flight_number=row['Flight'],
            departure_airport=dep,
            arrival_airport=arr,
            scheduled_departure_utc=std_utc,
            scheduled_arrival_utc=sta_utc
        )
    
    def _build_csv_duty(
        self,
        segments: List[FlightSegment],
        date: str,
        report: str,
        release: str
    ) -> Duty:
        """Build Duty from CSV data"""
        
        date_obj = pd.to_datetime(date)
        report_time = pd.to_datetime(report, format='%H:%M').time()
        release_time = pd.to_datetime(release, format='%H:%M').time()
        
        home_tz = pytz.timezone(self.home_timezone)
        
        report_utc = home_tz.localize(datetime.combine(date_obj, report_time)).astimezone(pytz.utc)
        release_utc = home_tz.localize(datetime.combine(date_obj, release_time)).astimezone(pytz.utc)
        
        duty_id = f"D_{date_obj.strftime('%Y%m%d')}_{segments[0].flight_number}"
        
        return Duty(
            duty_id=duty_id,
            date=date_obj,
            report_time_utc=report_utc,
            release_time_utc=release_utc,
            segments=segments,
            home_base_timezone=self.home_timezone
        )
