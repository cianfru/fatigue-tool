# roster_parser.py - PDF/CSV Roster Parser

"""
Roster Parser - Extract duty data from airline PDF/CSV rosters

Supports:
- Qatar Airways CrewLink PDF (using specialized grid-based parser)
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
from roster_parser_qatar import QatarRosterParser

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
        'TRV': {'name': 'Thiruvananthapuram', 'timezone': 'Asia/Kolkata', 'lat': 8.48, 'lon': 76.90},
        'LCA': {'name': 'Larnaca', 'timezone': 'Asia/Nicosia', 'lat': 34.40, 'lon': 33.62},
        'ALP': {'name': 'Aleppo', 'timezone': 'Asia/Damascus', 'lat': 36.18, 'lon': 37.22},
        'DMM': {'name': 'Dammam', 'timezone': 'Asia/Riyadh', 'lat': 26.47, 'lon': 49.80},
        'TBS': {'name': 'Tbilisi', 'timezone': 'Asia/Tbilisi', 'lat': 41.71, 'lon': 44.74},
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
        with pdfplumber.open(pdf_path) as pdf:
            full_text = ""
            for page in pdf.pages:
                full_text += page.extract_text() + "\n"
        
        # Detect roster format
        roster_format = self._detect_format(full_text)
        print(f"   Detected format: {roster_format}")
        
        # Parse based on format
        pilot_info = {}  # Store pilot info extracted from PDF
        duties = []
        if roster_format == 'crewlink' or roster_format == 'generic':
            # Try specialized Qatar Airways grid-based parser first
            # (works for both explicitly detected and unknown formats)
            try:
                print("   Attempting specialized Qatar Airways grid parser...")
                qatar_parser = QatarRosterParser(timezone_format='auto')
                result = qatar_parser.parse_roster(pdf_path)
                duties = result['duties']
                pilot_info = result.get('pilot_info', {})
                
                # Report unknown airports if any
                if result.get('unknown_airports'):
                    print(f"   ⚠️  Found {len(result['unknown_airports'])} unknown airports:")
                    for code in sorted(result['unknown_airports']):
                        print(f"      - {code}")
                
                if duties:
                    print(f"   ✅ Qatar parser succeeded")
                    if pilot_info.get('name'):
                        print(f"      Pilot: {pilot_info.get('name')} (ID: {pilot_info.get('id')})")
                        print(f"      Base: {pilot_info.get('base')} | Aircraft: {pilot_info.get('aircraft')}")
                else:
                    print(f"   ℹ️  Qatar parser found no duties")
                    
            except Exception as e:
                print(f"   ⚠️  Qatar parser: {e}")
                
                # Only fall back to line-based if explicitly detected as CrewLink
                if roster_format == 'crewlink':
                    print("   Trying line-based CrewLink parser...")
                    duties = self._parse_crewlink_format(full_text)
                else:
                    # Generic format - raise informative error
                    raise NotImplementedError(
                        "❌ Unsupported PDF format detected.\n\n"
                        "The PDF could not be parsed. This could mean:\n"
                        "  1. The PDF format is not supported\n"
                        "  2. The PDF is image-based or corrupted\n"
                        "  3. Text extraction failed\n\n"
                        "Supported formats:\n"
                        "  • Qatar Airways CrewLink (grid layout with dates as columns)\n"
                        "  • Tabular format (with vertical pipes '|')\n"
                        "  • CSV files (comma-separated values)\n\n"
                        "Please provide a text-based PDF roster or contact support."
                    )
        
        elif roster_format == 'tabular':
            duties = self._parse_tabular_format(full_text)
        
        else:
            # Fallback: Generic line-by-line parser
            duties = self._parse_generic_format(full_text)
        
        roster = Roster(
            roster_id=f"R_{pilot_id}_{month}",
            pilot_id=pilot_id,
            pilot_name=pilot_info.get('name'),
            pilot_base=pilot_info.get('base', self.home_base),
            pilot_aircraft=pilot_info.get('aircraft'),
            month=month,
            duties=duties,
            home_base_timezone=self.home_timezone
        )
        
        print(f"✓ Parsed {len(duties)} duties, {roster.total_sectors} sectors")
        return roster
    
    def _detect_format(self, text: str) -> str:
        """Auto-detect roster format from content
        
        Detection strategy:
        1. Look for explicit CrewLink/Qatar Airways headers
        2. Look for Qatar Airways grid pattern (dates like "01Feb", "02Feb", etc.)
        3. Look for grid-like structure (multiple dates stacked)
        4. Look for tabular format (lots of pipes)
        5. Default to generic
        """
        text_lower = text.lower()
        
        # Explicit Qatar Airways CrewLink indicators
        if 'crewlink' in text_lower or 'qatar airways' in text_lower:
            return 'crewlink'
        
        # Grid format indicators - look for date pattern like "01Feb", "02Feb", etc.
        # These appear as column headers in Qatar Airways rosters
        date_pattern_count = len(re.findall(r'\d{2}[A-Z][a-z]{2}', text))
        if date_pattern_count >= 5:  # Multiple dates = likely grid format
            print(f"   ℹ️  Detected {date_pattern_count} date headers (grid format)")
            return 'crewlink'
        
        # Look for Qatar-specific keywords
        qatar_keywords = ['period:', 'name:', 'base:', 'pilot', 'rpt:', 'crew', 'roster']
        qatar_matches = sum(1 for kw in qatar_keywords if kw in text_lower)
        if qatar_matches >= 3:
            print(f"   ℹ️  Detected Qatar Airways keywords")
            return 'crewlink'
        
        # Tabular format (lots of vertical bars)
        if text.count('|') > 20:
            return 'tabular'
        
        return 'generic'
    
    def _parse_crewlink_format(self, text: str) -> List[Duty]:
        """
        Parse Qatar Airways CrewLink PDF format
        
        Example format:
        Date       Flight  Dep   Arr   STD     STA     Report  Release
        15-JAN-24  QR001   DOH   LHR   07:30   13:15   06:00   14:30
        """
        duties = []
        lines = text.split('\n')
        
        current_duty_flights = []
        current_date = None
        report_time = None
        
        for line in lines:
            # Skip header/empty lines
            if not line.strip() or 'Flight' in line or '---' in line:
                continue
            
            # Extract duty data
            match = self._extract_duty_line_crewlink(line)
            if not match:
                continue
            
            date, flight_num, dep, arr, std, sta, rep, rel = match
            
            # New duty starts (different report time or date change)
            if report_time and rep != report_time:
                # Save previous duty
                if current_duty_flights:
                    duty = self._build_duty_from_flights(
                        current_duty_flights,
                        current_date,
                        report_time,
                        release_time
                    )
                    duties.append(duty)
                
                # Reset for new duty
                current_duty_flights = []
            
            # Parse flight segment
            segment = self._parse_flight_segment(
                flight_num, dep, arr, date, std, sta
            )
            
            current_duty_flights.append(segment)
            current_date = date
            report_time = rep
            release_time = rel
        
        # Don't forget last duty
        if current_duty_flights:
            duty = self._build_duty_from_flights(
                current_duty_flights,
                current_date,
                report_time,
                release_time
            )
            duties.append(duty)
        
        return duties
    
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
            "⚠️ Tabular PDF format detected but parser not yet implemented.\n\n"
            "Please provide a sample of your PDF roster for customization.\n"
            "Contact support with your roster PDF file."
        )
    
    def _parse_generic_format(self, text: str) -> List[Duty]:
        """Fallback generic parser - tries specialized Qatar parser as last resort"""
        
        print("⚠️  Generic format detected - attempting specialized Qatar parser...")
        
        # Last resort: try the specialized Qatar parser
        try:
            qatar_parser = QatarRosterParser(timezone_format='auto')
            # We need a temp PDF path - this is a limitation
            # The generic parser receives text, not the PDF path
            raise NotImplementedError(
                "❌ Unsupported PDF format detected.\n\n"
                "The text-based detection didn't recognize this as a Qatar Airways roster.\n\n"
                "This could mean:\n"
                "  1. The PDF keywords ('CrewLink', 'Qatar Airways', 'Period', etc.) are not being extracted\n"
                "  2. The PDF uses a different format than expected\n"
                "  3. The PDF is image-based or has extraction issues\n\n"
                "Supported formats:\n"
                "  • Qatar Airways CrewLink PDF (grid layout with dates as columns)\n"
                "  • Tabular format (with vertical bars/pipes '|')\n"
                "  • CSV files (comma-separated values)\n\n"
                "ACTION: Please verify the PDF is not image-based or corrupted.\n"
                "        Try uploading again, or contact support with a sample PDF."
            )
        except Exception as e:
            raise NotImplementedError(str(e))

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
