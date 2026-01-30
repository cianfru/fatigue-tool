# roster_parser.py - PDF/CSV Roster Parser

"""
Roster Parser - Extract duty data from airline PDF/CSV rosters

Supports:
- Qatar Airways CrewLink (Grid & Text formats)
- Generic CSV exports
- Robust Pilot ID and Report Time extraction

Scientific Note: Parser outputs standardized Roster objects
for biomathematical analysis (Borbély model)
"""

import pdfplumber
import pandas as pd
import re
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
import pytz

# Ensure you have these models defined in your project
from data_models import Airport, FlightSegment, Duty, Roster
from qatar_crewlink_parser import CrewLinkRosterParser

# ============================================================================
# AIRPORT DATABASE
# ============================================================================

class AirportDatabase:
    """
    IATA airport database with timezone information
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
        'AUH': {'name': 'Abu Dhabi', 'timezone': 'Asia/Dubai', 'lat': 24.43, 'lon': 54.65},
        'ELQ': {'name': 'Gassim', 'timezone': 'Asia/Riyadh', 'lat': 26.30, 'lon': 43.77},
        'IKA': {'name': 'Tehran Imam Khomeini', 'timezone': 'Asia/Tehran', 'lat': 35.41, 'lon': 51.15},
        'NJF': {'name': 'Najaf', 'timezone': 'Asia/Baghdad', 'lat': 31.99, 'lon': 44.40},
        'SHJ': {'name': 'Sharjah', 'timezone': 'Asia/Dubai', 'lat': 25.32, 'lon': 55.51},
        'JMK': {'name': 'Mykonos', 'timezone': 'Europe/Athens', 'lat': 37.43, 'lon': 25.34},
        'BAH': {'name': 'Bahrain', 'timezone': 'Asia/Bahrain', 'lat': 26.27, 'lon': 50.63},
        'MCT': {'name': 'Muscat', 'timezone': 'Asia/Muscat', 'lat': 23.59, 'lon': 58.28},
        'EBL': {'name': 'Erbil', 'timezone': 'Asia/Baghdad', 'lat': 36.23, 'lon': 43.96},
    }
    
    @classmethod
    def get_airport(cls, iata_code: str) -> Airport:
        """Get Airport object from IATA code"""
        code = iata_code.upper()
        
        if code not in cls.AIRPORTS:
            # Fallback for unknown airports to prevent crash, default to UTC
            print(f"⚠️ Warning: Airport '{code}' not in database. Using UTC default.")
            return Airport(
                code=code,
                timezone='UTC',
                latitude=0.0,
                longitude=0.0
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
        self.roster_year = datetime.now().year  # Default, will be updated from PDF
    
    def parse_pdf(self, pdf_path: str, pilot_id: str, month: str) -> Roster:
        """
        Main entry point - extract roster from PDF
        """
        print(f"📄 Parsing PDF roster: {pdf_path}")
        
        # Extract text from PDF
        with pdfplumber.open(pdf_path) as pdf:
            full_text = ""
            for page in pdf.pages:
                full_text += page.extract_text() + "\n"
        
        # Extract the Roster Period Year
        self._extract_roster_year(full_text)

        # Pre-extract Header Info (Robust Regex for ID/Name)
        header_info = self._extract_header_info(full_text)
        
        # Detect roster format
        roster_format = self._detect_format(full_text)
        print(f"   Detected format: {roster_format}")
        
        pilot_info = {} 
        duties = []

        if roster_format == 'crewlink' or roster_format == 'generic':
            # Try specialized CrewLink-style grid parser first
            try:
                print("   Attempting CrewLink grid-format parser...")
                grid_parser = CrewLinkRosterParser(timezone_format='auto')
                result = grid_parser.parse_roster(pdf_path)
                duties = result['duties']
                pilot_info = result.get('pilot_info', {})
                
                # Report unknown airports if any
                if result.get('unknown_airports'):
                    print(f"   ⚠️  Found {len(result['unknown_airports'])} unknown airports:")
                    for code in sorted(result['unknown_airports']):
                        print(f"      - {code}")
                
                if duties:
                    print(f"   ✅ Grid parser succeeded")
                else:
                    print(f"   ℹ️  Grid parser found no duties - Switching to Line Parser")
                    raise ValueError("Grid parser returned empty duties")
                    
            except Exception as e:
                print(f"   ⚠️  Grid parser: {e}")
                
                # Fall back to line-based parser (Handles the messy "text soup")
                print("   Trying line-based CrewLink parser (Stateful)...")
                duties = self._parse_crewlink_format(full_text)
        
        elif roster_format == 'tabular':
            duties = self._parse_tabular_format(full_text)
        
        else:
            duties = self._parse_generic_format(full_text)
       
        # MERGE LOGIC: Prioritize the Header Extraction for ID/Name
        final_pilot_id = header_info.get('id') or pilot_info.get('id') or pilot_id
        final_pilot_name = header_info.get('name') or pilot_info.get('name')
        final_base = header_info.get('base') or pilot_info.get('base') or self.home_base
        final_aircraft = header_info.get('aircraft') or pilot_info.get('aircraft')

        print(f"   Found Pilot: {final_pilot_name} (ID: {final_pilot_id})")
        print(f"   Base: {final_base} | Aircraft: {final_aircraft}")

        roster = Roster(
            roster_id=f"R_{final_pilot_id}_{month}",
            pilot_id=final_pilot_id,
            pilot_name=final_pilot_name,
            pilot_base=final_base,
            pilot_aircraft=final_aircraft,
            month=month,
            duties=duties,
            home_base_timezone=self.home_timezone
        )
        
        print(f"✓ Parsed {len(duties)} duties, {roster.total_sectors} sectors")
        return roster
    
    def _extract_roster_year(self, text: str):
        """Extract year from 'Period: 01-Aug-2025' line"""
        match = re.search(r'Period:.*(\d{4})', text)
        if match:
            self.roster_year = int(match.group(1))
            print(f"   Confirmed Roster Year: {self.roster_year}")

    def _extract_header_info(self, text: str) -> Dict[str, str]:
        """
        Robustly extract Pilot Header details using Regex
        Matches format: Name: XXXX \n ID:134614 (DOH CP-A320)
        """
        # AGGRESSIVE cleaning of PDF artifacts
        text = re.sub(r'\(cid:\d+\)', '', text)  # Remove (cid:X) markers
        text = re.sub(r'[\x00-\x1F\x7F]', ' ', text)  # Remove control characters
        
        info = {}
        
        # DEBUG: Show what we're working with
        if 'ID' in text:
            id_context = text[text.find('ID'):text.find('ID')+100]
            print(f"   [DEBUG] Text around ID: {repr(id_context)}")
        else:
            print(f"   [DEBUG] 'ID' keyword not found in text")
        
        # 1. Extract ID - MORE FLEXIBLE pattern
        # Match ID followed by digits, allowing for spaces/junk between digits
        id_match = re.search(r'ID\s*[:]\s*([\d\s]+)', text, re.IGNORECASE)
        if id_match:
            # Clean up the captured digits (remove spaces)
            raw_id = id_match.group(1)
            clean_id = re.sub(r'\D', '', raw_id)  # Keep only digits
            if clean_id:
                info['id'] = clean_id
                print(f"   [DEBUG] Extracted ID: '{clean_id}' (raw: '{raw_id.strip()}')")
        else:
            print(f"   [DEBUG] ID extraction FAILED")

        # 2. Extract Name - Stop at "All times", "ID", or newline
        name_match = re.search(r'Name\s*[:]\s*(.+?)(?=\s+All times|\s+ID|\n|$)', text, re.IGNORECASE)
        if name_match:
            info['name'] = name_match.group(1).strip()
            print(f"   [DEBUG] Extracted Name: '{info['name']}'")

        # 3. Extract Base and Aircraft from parens
        # Looks for patterns like (DOH CP-A320) or (DOH FO-A320)
        details_match = re.search(r'\(([A-Z]{3})\s+[A-Z]{2}-([A-Z0-9\-]+)\)', text)
        if details_match:
            info['base'] = details_match.group(1)      # e.g. DOH
            info['aircraft'] = details_match.group(2)  # e.g. A320
            print(f"   [DEBUG] Extracted Base: {info['base']}, Aircraft: {info['aircraft']}")
            
        return info

    def _detect_format(self, text: str) -> str:
        """Auto-detect roster format from content"""
        text_lower = text.lower()
        
        # Explicit Qatar Airways CrewLink indicators
        if 'crewlink' in text_lower or 'qatar airways' in text_lower or 'qatar' in text_lower:
            return 'crewlink'
        
        # Grid format indicators
        date_pattern_count = len(re.findall(r'\d{2}[A-Z][a-z]{2}', text))
        if date_pattern_count >= 5: 
            return 'crewlink'
        
        return 'generic'
    
    def _parse_crewlink_format(self, text: str) -> List[Duty]:
        """
        Parse Qatar Airways CrewLink PDF format (Stateful "Soup" Parser)
        
        Handles fragmented text where RPT (Report/Sign-in) appears 
        before the flight details, distinct from the flight row.
        """
        duties = []
        lines = text.split('\n')
        
        current_duty_flights = []
        current_date = None
        current_report_time = None  # Store RPT when found
        current_release_time = None
        
        # Regex for "RPT:HH:MM" tag
        rpt_pattern = re.compile(r'RPT:(\d{2}:\d{2})')
        
        # Regex for date headers like "01Aug" or "01Aug Fri"
        date_pattern = re.compile(r'(\d{2}[A-Z][a-z]{2})')
        
        for line in lines:
            line = line.strip()
            if not line:
                continue

            # 1. Capture Date (e.g., "01Aug")
            # We need this to anchor the duty
            date_match = date_pattern.search(line)
            if date_match:
                try:
                    date_str = date_match.group(1)
                    current_date = self._parse_partial_date(date_str)
                except ValueError:
                    pass

            # 2. Capture Report Time (RPT)
            # Looks for "RPT:07:30" anywhere in the line
            rpt_match = rpt_pattern.search(line)
            if rpt_match:
                # If we find a NEW report time, finalize previous duty
                if current_duty_flights:
                    # Use date of first flight for the previous duty
                    duty_date = current_duty_flights[0].date_obj if hasattr(current_duty_flights[0], 'date_obj') else current_date
                    duty = self._build_duty_from_flights(
                        current_duty_flights,
                        duty_date,
                        current_report_time,
                        "00:00"  # fallback release if not captured
                    )
                    duties.append(duty)
                    current_duty_flights = []
                
                current_report_time = rpt_match.group(1)
                
            # 3. Capture Flight Info
            # Matches: 1044 DOH 08:45 AUH 09:55
            flight_match = self._extract_flight_data_loose(line)
            
            if flight_match and current_date:
                flight_num, dep, std, arr, sta = flight_match
                
                # Parse the segment
                segment = self._parse_flight_segment(
                    flight_num, dep, arr, 
                    current_date.strftime('%d-%b-%Y'),
                    std, sta
                )
                segment.date_obj = current_date  # Store for reference
                
                current_duty_flights.append(segment)

        # 4. Save any remaining duty at end of file
        if current_duty_flights and current_report_time:
            duty_date = current_duty_flights[0].date_obj if hasattr(current_duty_flights[0], 'date_obj') else current_date
            duty = self._build_duty_from_flights(
                current_duty_flights,
                duty_date,
                current_report_time,
                "00:00"
            )
            duties.append(duty)
            
        return duties

    def _extract_flight_data_loose(self, line: str) -> Optional[Tuple]:
        """
        Regex for raw flight strings
        Matches: "1044 DOH 08:45 AUH 09:55"
        """
        pattern = r'(\d{3,4})\s+([A-Z]{3})\s+(\d{2}:\d{2})\s+([A-Z]{3})\s+(\d{2}:\d{2}(?:\+\d)?)'
        match = re.search(pattern, line)
        if match:
            return match.groups()
        return None

    def _parse_partial_date(self, date_str: str) -> datetime:
        """Handle '01Aug' -> datetime object with correct year"""
        dt = datetime.strptime(date_str, '%d%b')
        return dt.replace(year=self.roster_year)

    def _parse_flight_segment(self, flight_num: str, dep_code: str, arr_code: str, date_str: str, std_str: str, sta_str: str) -> FlightSegment:
        dep_airport = self.airport_db.get_airport(dep_code)
        arr_airport = self.airport_db.get_airport(arr_code)
        
        try:
            date = datetime.strptime(date_str, '%d-%b-%Y')
        except ValueError:
             date = datetime.strptime(date_str, '%d-%b-%y')

        std_time = datetime.strptime(std_str, '%H:%M').time()
        
        if '+' in sta_str:
            sta_str_clean = sta_str.split('+')[0]
            days_offset = int(sta_str.split('+')[1])
        else:
            sta_str_clean = sta_str
            days_offset = 0
        
        sta_time = datetime.strptime(sta_str_clean, '%H:%M').time()
        
        dep_tz = pytz.timezone(dep_airport.timezone)
        arr_tz = pytz.timezone(arr_airport.timezone)
        
        std_local = dep_tz.localize(datetime.combine(date, std_time))
        sta_local = arr_tz.localize(datetime.combine(date + timedelta(days=days_offset), sta_time))
        
        std_utc = std_local.astimezone(pytz.utc)
        sta_utc = sta_local.astimezone(pytz.utc)
        
        return FlightSegment(
            flight_number=flight_num,
            departure_airport=dep_airport,
            arrival_airport=arr_airport,
            scheduled_departure_utc=std_utc,
            scheduled_arrival_utc=sta_utc
        )
    
    def _validate_duty_times(self, report_utc: datetime, release_utc: datetime, 
                            segments: List[FlightSegment], date: datetime) -> Tuple[datetime, datetime, List[str]]:
        """
        Validate and correct duty times to ensure chronological consistency.
        
        Returns:
            Tuple of (corrected_report_utc, corrected_release_utc, warnings)
        """
        warnings = []
        corrected_report = report_utc
        corrected_release = release_utc
        
        if not segments:
            return corrected_report, corrected_release, warnings
        
        first_departure = segments[0].scheduled_departure_utc
        last_arrival = segments[-1].scheduled_arrival_utc
        
        # Check if report time is after first departure (likely wrong day)
        if corrected_report > first_departure:
            # Move report to previous day
            corrected_report = corrected_report - timedelta(days=1)
            warnings.append(f"Report time moved to previous day (was after first departure)")
        
        # Validate report is before first departure (with reasonable buffer)
        time_before_departure = (first_departure - corrected_report).total_seconds() / 3600
        if time_before_departure < 0.5:  # Less than 30 minutes before departure
            warnings.append(f"Warning: Report time only {time_before_departure*60:.0f}min before departure")
        elif time_before_departure > 4:  # More than 4 hours before departure
            warnings.append(f"Note: Report time {time_before_departure:.1f}h before departure (long pre-flight)")
        
        # Validate release time is after last arrival
        if corrected_release < last_arrival:
            # Release must be at least 30 min after landing
            corrected_release = last_arrival + timedelta(minutes=30)
            warnings.append(f"Release time adjusted to 30min after last landing")
        
        # Final check: ensure report < release
        if corrected_report >= corrected_release:
            warnings.append(f"ERROR: Invalid duty - report time >= release time")
        
        return corrected_report, corrected_release, warnings

    def _build_duty_from_flights(self, segments: List[FlightSegment], date: datetime, report_str: str, release_str: str) -> Duty:
        report_time_obj = datetime.strptime(report_str, '%H:%M').time()
        
        if '+' in release_str:
            release_str_clean = release_str.split('+')[0]
            days_offset = int(release_str.split('+')[1])
        else:
            release_str_clean = release_str
            days_offset = 0
        
        release_time_obj = datetime.strptime(release_str_clean, '%H:%M').time()
        
        home_tz = pytz.timezone(self.home_timezone)

        report_local = home_tz.localize(datetime.combine(date, report_time_obj))
        release_local = home_tz.localize(datetime.combine(date + timedelta(days=days_offset), release_time_obj))
        
        report_utc = report_local.astimezone(pytz.utc)
        release_utc = release_local.astimezone(pytz.utc)
        
        # Validate and correct times
        report_utc, release_utc, validation_warnings = self._validate_duty_times(
            report_utc, release_utc, segments, date
        )
        
        # Log any warnings
        for warning in validation_warnings:
            print(f"  ⚠️  {warning}")
        
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
        raise NotImplementedError("Tabular PDF format parser not yet implemented.")
    
    def _parse_generic_format(self, text: str) -> List[Duty]:
        raise NotImplementedError("Generic format parser failed to identify roster structure.")

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
        duties = []
        current_duty_flights = []
        last_report = None
        last_date = None
        last_release = None
        
        for _, row in df.iterrows():
            segment = self._parse_csv_flight(row)
            
            if last_report and row['Report'] != last_report:
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
        dep = self.airport_db.get_airport(row['Departure'])
        arr = self.airport_db.get_airport(row['Arrival'])
        
        date = pd.to_datetime(row['Date'])
        std_time = pd.to_datetime(row['STD'], format='%H:%M').time()
        sta_time = pd.to_datetime(row['STA'], format='%H:%M').time()
        
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
    
    def _build_csv_duty(self, segments: List[FlightSegment], date: str, report: str, release: str) -> Duty:
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
