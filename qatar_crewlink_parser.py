"""
Airline Grid Roster Parser
============================

Parses grid/table layout rosters commonly used by airlines (CrewLink, etc.) where:
- Each date is a column header
- Data for that day is stacked vertically below it (RPT, flights, times)
- Multi-sector days have multiple flight entries stacked

Design: Pattern-based recognition, works with ANY airline using similar grid layout
Supports: Qatar Airways, Emirates, Etihad, and other airlines with CrewLink-style rosters
"""

import re
import pdfplumber
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import pytz

from data_models import Airport, FlightSegment, Duty


# Known airports database with timezone information
# This is a starter list - unknown airports are auto-created with UTC timezone
# Parser will flag unknown airports for manual timezone addition if needed
KNOWN_AIRPORTS = {
    # === MIDDLE EAST HUBS ===
    'DOH': Airport('DOH', 'Asia/Qatar', 25.273056, 51.608056),        # Doha
    'DXB': Airport('DXB', 'Asia/Dubai', 25.252778, 55.364444),        # Dubai
    'AUH': Airport('AUH', 'Asia/Dubai', 24.433056, 54.651111),        # Abu Dhabi
    'JED': Airport('JED', 'Asia/Riyadh', 21.679556, 39.156639),       # Jeddah
    'RUH': Airport('RUH', 'Asia/Riyadh', 24.957222, 46.698889),       # Riyadh
    'DMM': Airport('DMM', 'Asia/Riyadh', 26.471161, 49.797933),       # Dammam
    'KWI': Airport('KWI', 'Asia/Kuwait', 29.226667, 47.968889),       # Kuwait
    'BAH': Airport('BAH', 'Asia/Bahrain', 26.270556, 50.633611),      # Bahrain
    'MCT': Airport('MCT', 'Asia/Muscat', 23.593278, 58.284444),       # Muscat
    
    # === MAJOR EUROPEAN HUBS ===
    'LHR': Airport('LHR', 'Europe/London', 51.4700, -0.4543),         # London Heathrow
    'LGW': Airport('LGW', 'Europe/London', 51.148056, -0.190278),     # London Gatwick
    'CDG': Airport('CDG', 'Europe/Paris', 49.009722, 2.547778),       # Paris CDG
    'FRA': Airport('FRA', 'Europe/Berlin', 50.033333, 8.570556),      # Frankfurt
    'MUC': Airport('MUC', 'Europe/Berlin', 48.353889, 11.786111),     # Munich
    'AMS': Airport('AMS', 'Europe/Amsterdam', 52.308056, 4.764167),   # Amsterdam
    'FCO': Airport('FCO', 'Europe/Rome', 41.804167, 12.250833),       # Rome
    'MAD': Airport('MAD', 'Europe/Madrid', 40.471926, -3.56264),      # Madrid
    'BCN': Airport('BCN', 'Europe/Madrid', 41.297078, 2.078464),      # Barcelona
    'ZRH': Airport('ZRH', 'Europe/Zurich', 47.464722, 8.549167),      # Zurich
    'VIE': Airport('VIE', 'Europe/Vienna', 48.110833, 16.570833),     # Vienna
    'ATH': Airport('ATH', 'Europe/Athens', 37.934444, 23.947222),     # Athens
    'IST': Airport('IST', 'Europe/Istanbul', 41.275278, 28.751944),   # Istanbul
    
    # === NORTH AMERICA ===
    'JFK': Airport('JFK', 'America/New_York', 40.6413, -73.7781),     # New York JFK
    'EWR': Airport('EWR', 'America/New_York', 40.6925, -74.168611),   # Newark
    'IAD': Airport('IAD', 'America/New_York', 38.944533, -77.455811), # Washington Dulles
    'ORD': Airport('ORD', 'America/Chicago', 41.978611, -87.904722),  # Chicago
    'LAX': Airport('LAX', 'America/Los_Angeles', 33.94, -118.41),     # Los Angeles
    'SFO': Airport('SFO', 'America/Los_Angeles', 37.619, -122.375),   # San Francisco
    'YYZ': Airport('YYZ', 'America/Toronto', 43.677222, -79.630556),  # Toronto
    'YVR': Airport('YVR', 'America/Vancouver', 49.193889, -123.184),  # Vancouver
    
    # === ASIA PACIFIC ===
    'SIN': Airport('SIN', 'Asia/Singapore', 1.350194, 103.994433),    # Singapore
    'HKG': Airport('HKG', 'Asia/Hong_Kong', 22.308889, 113.914722),   # Hong Kong
    'BKK': Airport('BKK', 'Asia/Bangkok', 13.681111, 100.747222),     # Bangkok
    'KUL': Airport('KUL', 'Asia/Kuala_Lumpur', 2.745578, 101.709917), # Kuala Lumpur
    'CGK': Airport('CGK', 'Asia/Jakarta', -6.125567, 106.655897),     # Jakarta
    'MNL': Airport('MNL', 'Asia/Manila', 14.508647, 121.019581),      # Manila
    'ICN': Airport('ICN', 'Asia/Seoul', 37.469075, 126.450517),       # Seoul Incheon
    'NRT': Airport('NRT', 'Asia/Tokyo', 35.764722, 140.386389),       # Tokyo Narita
    'PVG': Airport('PVG', 'Asia/Shanghai', 31.143333, 121.805278),    # Shanghai
    'PEK': Airport('PEK', 'Asia/Shanghai', 40.080111, 116.584556),    # Beijing
    'DEL': Airport('DEL', 'Asia/Kolkata', 28.556161, 77.100389),      # Delhi
    'BOM': Airport('BOM', 'Asia/Kolkata', 19.088686, 72.867919),      # Mumbai
    'HYD': Airport('HYD', 'Asia/Kolkata', 17.231361, 78.429639),      # Hyderabad
    'BLR': Airport('BLR', 'Asia/Kolkata', 13.198889, 77.705556),      # Bangalore
    'CCJ': Airport('CCJ', 'Asia/Kolkata', 11.136111, 75.955278),      # Kozhikode
    'TRV': Airport('TRV', 'Asia/Kolkata', 8.482122, 76.920136),       # Thiruvananthapuram
    'SYD': Airport('SYD', 'Australia/Sydney', -33.946111, 151.177222),# Sydney
    'MEL': Airport('MEL', 'Australia/Melbourne', -37.673333, 144.843333), # Melbourne
    
    # === AFRICA ===
    'CAI': Airport('CAI', 'Africa/Cairo', 30.121944, 31.405556),      # Cairo
    'JNB': Airport('JNB', 'Africa/Johannesburg', -26.133694, 28.242317), # Johannesburg
    'CPT': Airport('CPT', 'Africa/Johannesburg', -33.969444, 18.597222), # Cape Town
    'NBO': Airport('NBO', 'Africa/Nairobi', -1.319167, 36.927778),    # Nairobi
    'ADD': Airport('ADD', 'Africa/Addis_Ababa', 8.977889, 38.799319), # Addis Ababa
    
    # === SOUTH AMERICA ===
    'GRU': Airport('GRU', 'America/Sao_Paulo', -23.435556, -46.473056), # São Paulo
    'EZE': Airport('EZE', 'America/Argentina/Buenos_Aires', -34.822222, -58.535833), # Buenos Aires
    
    # === MIDDLE EAST REGIONAL ===
    'AMM': Airport('AMM', 'Asia/Amman', 31.722556, 35.993214),        # Amman
    'BEY': Airport('BEY', 'Asia/Beirut', 33.820931, 35.488389),       # Beirut
    'LCA': Airport('LCA', 'Asia/Nicosia', 34.875117, 33.624944),      # Larnaca
    'TBS': Airport('TBS', 'Asia/Tbilisi', 41.669167, 44.954722),      # Tbilisi
    'EVN': Airport('EVN', 'Asia/Yerevan', 40.147275, 44.395881),      # Yerevan
    'GYD': Airport('GYD', 'Asia/Baku', 40.467222, 50.046667),         # Baku
    'RSI': Airport('RSI', 'Asia/Baghdad', 33.262222, 44.234722),      # Basra
    'BGW': Airport('BGW', 'Asia/Baghdad', 33.262514, 44.234622),      # Baghdad
    'TIF': Airport('TIF', 'Asia/Riyadh', 21.483333, 39.183333),       # Taif
    'ALP': Airport('ALP', 'Asia/Damascus', 36.180556, 37.224444),     # Aleppo
    
    # NOTE: Unknown airports are automatically created with UTC timezone
    # Parser will flag them for manual timezone addition if accurate analysis is needed
}


class CrewLinkRosterParser:
    """
    Generic pattern-based parser for airline grid-format rosters (CrewLink-style)
    
    KEY DESIGN: Pattern recognition, not airline-specific
    - Detects RPT:HH:MM pattern (reporting time)
    - Detects flight pattern: NNNN AAA HH:MM AAA HH:MM
    - Handles unknown airports gracefully (auto-creates with UTC)
    - Works with ANY airline using similar grid layout
    
    Supported: Qatar Airways, Emirates, Etihad, and other airlines with CrewLink rosters
    """
    
    def __init__(self, auto_create_airports: bool = True, timezone_format: str = 'auto'):
        """
        Initialize parser
        
        Args:
            auto_create_airports: Create placeholder for unknown airports
            timezone_format: 'auto', 'local', or 'zulu'
                - 'auto': Detect from PDF header (default, recommended)
                - 'local': Times in roster are in local timezone of each airport
                - 'zulu': Times in roster are in UTC/Zulu (all times are UTC)
        """
        self.airports = KNOWN_AIRPORTS.copy()
        self.auto_create_airports = auto_create_airports
        self.timezone_format = timezone_format.lower()
        self.unknown_airports = set()  # Track for reporting
        
        if self.timezone_format not in ['auto', 'local', 'zulu']:
            raise ValueError(f"timezone_format must be 'auto', 'local' or 'zulu', got '{timezone_format}'")
    
    def _get_or_create_airport(self, code: str) -> Optional[Airport]:
        """
        Get airport from database, or create placeholder if unknown
        
        This allows parser to work with ANY flights, not just known routes
        """
        if code in self.airports:
            return self.airports[code]
        
        if not self.auto_create_airports:
            self.unknown_airports.add(code)
            return None
        
        # Create placeholder airport with UTC timezone
        placeholder = Airport(
            code=code,
            timezone='UTC',  # Default timezone
            latitude=0.0,
            longitude=0.0
        )
        
        self.airports[code] = placeholder
        self.unknown_airports.add(code)
        
        print(f"⚠️  Created placeholder airport for {code} (timezone=UTC)")
        print(f"    Please add proper timezone for accurate analysis")
        
        return placeholder
    
    def parse_roster(self, pdf_path: str) -> Dict:
        """
        Main entry point - parses airline grid-format roster PDF
        
        Returns:
            Dict with pilot info and parsed duties
        """
        with pdfplumber.open(pdf_path) as pdf:
            page = pdf.pages[0]
            
            # Auto-detect timezone format if set to 'auto'
            if self.timezone_format == 'auto':
                detected_format = self._detect_timezone_format(page)
                self.timezone_format = detected_format
                print(f"   ℹ️  Detected timezone format: {detected_format.upper()}")
            
            # Extract pilot info from header
            pilot_info = self._extract_pilot_info(page)
            pilot_info['timezone_format'] = self.timezone_format
            
            # Extract the main schedule table
            table = self._extract_schedule_table(page)
            
            # Parse the grid into duties
            duties = self._parse_grid_to_duties(table, pilot_info['year'])
            
            return {
                'pilot_info': pilot_info,
                'duties': duties,
                'statistics': self._extract_statistics(page),
                'unknown_airports': list(self.unknown_airports)
            }
    
    def _detect_timezone_format(self, page) -> str:
        """
        Auto-detect timezone format from PDF header
        
        Looks for phrases like:
        - "All times are in Local" -> 'local'
        - "All times are in UTC" -> 'zulu'
        - "Times: UTC" -> 'zulu'
        
        Returns:
            'local' or 'zulu'
        """
        text = page.extract_text().lower()
        
        # Check for explicit statements
        if 'all times are in local' in text or 'times: local' in text or 'times local' in text:
            print("✓ Detected timezone format: LOCAL (times shown in airport local time)")
            return 'local'
        
        if ('all times are in utc' in text or 
            'all times are in zulu' in text or
            'times: utc' in text or
            'times: zulu' in text or
            'times utc' in text):
            print("✓ Detected timezone format: ZULU/UTC (all times are UTC)")
            return 'zulu'
        
        # Default to local if not explicitly stated
        print("⚠️  Could not detect timezone format from PDF header")
        print("    Defaulting to 'local' format (times in each airport's local timezone)")
        print("    If times are showing incorrectly, the PDF may be using UTC format")
        return 'local'
    
    def _extract_pilot_info(self, page) -> Dict:
        """
        Extract pilot and roster metadata from PDF header
        
        Extracts:
        - Pilot name
        - Pilot ID
        - Pilot base
        - Aircraft type
        - Roster period (start and end dates)
        - Block hours and duty hours statistics
        - Timezone format (local vs UTC)
        
        Returns:
            Dict with keys: name, id, base, aircraft, period_start, period_end,
            block_hours, duty_hours, year, month
        """
        text = page.extract_text()
        
        # CRITICAL FIX: Clean PDF extraction artifacts
        # pdfplumber may include (cid:X) markers for special characters like tabs
        # These MUST be removed before regex matching
        text_clean = re.sub(r'\(cid:\d+\)', ' ', text)
        
        # Debug: Print first 500 chars of cleaned text
        print(f"\n   [DEBUG] First 500 chars of cleaned PDF text:")
        print(f"   {repr(text_clean[:500])}\n")
        
        # Initialize with defaults
        info = {
            'name': None,
            'id': None,
            'base': 'DOH',  # Default
            'aircraft': 'A320',  # Default
            'year': None,
            'month': None,
            'period_start': None,
            'period_end': None,
            'block_hours': '00:00',
            'duty_hours': '00:00'
        }
        
        # ----
        # 1. EXTRACT PILOT NAME
        # ----
        # Pattern handles extra whitespace and stops at "All times"
        # Improved to handle PDF artifacts and various formatting
        name_match = re.search(r'Name\s+:\s*(.+?)(?:\n|All times|ID\s+:)', text_clean, re.DOTALL)
        if name_match:
            info['name'] = name_match.group(1).strip()
            print(f"   ✓ Extracted pilot name: {info['name']}")
        else:
            # Fallback: Try without requiring whitespace after colon
            name_match = re.search(r'Name\s*:\s*(.+?)(?:\n|$)', text_clean)
            if name_match:
                info['name'] = name_match.group(1).strip()
                print(f"   ✓ Extracted pilot name (fallback): {info['name']}")
            else:
                print(f"   ⚠️  Could not extract pilot name from PDF header")
                print(f"   [DEBUG] Text around 'Name': {repr(text_clean[:200])}")
        
        # ----
        # 2. EXTRACT ID, BASE, AIRCRAFT
        # ----
        # Format in PDF: "ID    :134614 (DOH CP-A320)"
        # Improved pattern with flexible spacing
        id_pattern = r'ID\s+:\s*(\d+)\s*\(\s*([A-Z]{3})\s+CP-(\w+)\)'
        id_match = re.search(id_pattern, text_clean)
        
        if id_match:
            info['id'] = id_match.group(1)
            info['base'] = id_match.group(2)
            info['aircraft'] = id_match.group(3)
            print(f"   ✓ Extracted pilot ID: {info['id']} | Base: {info['base']} | Aircraft: {info['aircraft']}")
        else:
            # Try simpler pattern without CP prefix
            id_match_simple = re.search(r'ID\s*:\s*(\d+)', text_clean)
            if id_match_simple:
                info['id'] = id_match_simple.group(1)
                print(f"   ✓ Extracted pilot ID: {info['id']} (base/aircraft not found)")
            else:
                print(f"   ⚠️  Could not extract pilot ID from PDF header")
        
        # ----
        # 3. EXTRACT ROSTER PERIOD (ENHANCED)
        # ----
        # Format: "Period: 01-Feb-2026 - 28-Feb-2026 | Published"
        # This is ESSENTIAL for determining the month being analyzed
        period_match = re.search(
            r'Period:\s*(\d{2}-\w{3}-\d{4})\s*-\s*(\d{2}-\w{3}-\d{4})',
            text_clean
        )
        
        if period_match:
            info['period_start'] = period_match.group(1)
            info['period_end'] = period_match.group(2)
            
            # Also extract month and year from period_start
            date_parts = re.search(r'\d+-(\w{3})-(\d{4})', info['period_start'])
            if date_parts:
                info['month'] = date_parts.group(1)
                info['year'] = int(date_parts.group(2))
            
            print(f"   ✓ Period: {info['period_start']} to {info['period_end']}")
            print(f"   ✓ Extracted period: {info['month']} {info['year']}")
        else:
            # Fallback to simpler pattern
            period_match_simple = re.search(r'Period:\s*\d+-([A-Za-z]+)-(\d{4})', text_clean)
            if period_match_simple:
                info['month'] = period_match_simple.group(1)
                info['year'] = int(period_match_simple.group(2))
                print(f"   ✓ Extracted period: {info['month']} {info['year']}")
            else:
                print(f"   ⚠️  Period extraction failed")
        
        # ----
        # 4. EXTRACT STATISTICS (BLOCK HOURS, DUTY HOURS)
        # ----
        # Format: "VALUE 71:45 114:30 0 24 00:00 0 0 0 17"
        #         (block hrs, duty hrs, ...)
        stats_match = re.search(r'VALUE\s+([\d:]+)\s+([\d:]+)', text_clean)
        
        if stats_match:
            info['block_hours'] = stats_match.group(1)
            info['duty_hours'] = stats_match.group(2)
            print(f"   ✓ Statistics: {info['block_hours']} block hours, {info['duty_hours']} duty hours")
        else:
            print(f"   ⚠️  Statistics extraction failed")
        
        # ----
        # 5. DETECT TIMEZONE FORMAT
        # ----
        # This determines how to interpret all times in the duty details
        if "All times are in Local" in text_clean:
            print(f"   ✓ Timezone: LOCAL TIMES")
        elif "All times are in UTC" in text_clean or "Zulu" in text_clean:
            print(f"   ✓ Timezone: UTC/ZULU TIMES")
        else:
            print(f"   ℹ️  Timezone not explicitly stated, assuming LOCAL")
        
        return info
    
    def _extract_schedule_table(self, page) -> List[List[str]]:
        """
        Extract the main schedule grid using pdfplumber table detection
        """
        # Use aggressive table detection for complex grid
        table = page.extract_table({
            "vertical_strategy": "lines",
            "horizontal_strategy": "lines",
            "snap_tolerance": 5,
            "join_tolerance": 3,
            "edge_min_length": 10,
        })
        
        if not table:
            # Fallback: try text strategy
            table = page.extract_table({
                "vertical_strategy": "text",
                "horizontal_strategy": "text",
                "snap_tolerance": 5,
            })
        
        return table if table else []
    
    def _parse_grid_to_duties(self, table: List[List[str]], year: int) -> List[Duty]:
        """
        Parse the grid table into Duty objects
        
        Grid structure:
        Row 0: Date headers (e.g., "01Feb Sun", "02Feb Mon", ...)
        Row 1+: Data rows (RPT, flights, times, block/duty hours)
        """
        if not table or len(table) < 2:
            return []
        
        duties = []
        
        # First row = date headers
        date_headers = table[0]
        
        # Identify which columns are dates (skip empty/label columns)
        date_columns = []
        for col_idx, header in enumerate(date_headers):
            if header and re.match(r'\d{2}[A-Z][a-z]{2}', header):
                # Parse date like "01Feb" -> datetime
                date_str = header.split('\n')[0].split()[0]  # Get "01Feb"
                day = int(date_str[:2])
                month_str = date_str[2:]
                month = datetime.strptime(month_str, '%b').month
                date = datetime(year, month, day)
                
                date_columns.append({
                    'col_idx': col_idx,
                    'date': date,
                    'date_str': date_str
                })
        
        # For each date column, extract vertical stack of data
        for date_col in date_columns:
            col_idx = date_col['col_idx']
            date = date_col['date']
            
            # Collect all non-empty cells in this column
            column_data = []
            for row_idx in range(1, len(table)):
                cell = table[row_idx][col_idx]
                if cell and cell.strip():
                    column_data.append(cell.strip())
            
            # Parse this column's data into a duty (if any)
            duty = self._parse_column_to_duty(date, column_data)
            if duty:
                duties.append(duty)
        
        return duties
    
    def _parse_column_to_duty(self, date: datetime, column_data: List[str]) -> Optional[Duty]:
        """
        Parse a single date column vertical data stack into a Duty
        """
        if not column_data:
            return None
        
        # Combine all data and split by newlines
        full_text = '\n'.join(column_data)
        lines = [line.strip() for line in full_text.split('\n') if line.strip()]
        
        if not lines:
            return None
        
        # Check if OFF day
        first_item = lines[0].upper()
        if 'OFF' in first_item or 'GOFF' in first_item:
            return None  # OFF day, no duty
        
        # Check if standby
        if 'PSBY' in first_item or 'STANDBY' in first_item:
            return None  # Standby, not a flying duty
        
        # Extract report time (RPT) and flight segments first
        # We need to know the departure airport to properly localize report time
        report_time = None
        report_hour = None
        report_minute = None
        
        for line in lines:
            rpt_match = re.match(r'RPT:(\d{2}):(\d{2})', line)
            if rpt_match:
                report_hour = int(rpt_match.group(1))
                report_minute = int(rpt_match.group(2))
                break
        
        # Extract flight segments first to determine departure airport
        segments = self._extract_segments_from_lines(lines, date)
        
        if not segments:
            return None
        
        # Now create report time using the DEPARTURE AIRPORT timezone (not home base)
        # This is critical for circadian alignment
        if report_hour is not None:
            report_time_naive = datetime(date.year, date.month, date.day, report_hour, report_minute)
            
            # Get timezone from departure airport (first segment's departure)
            dep_airport = segments[0].departure_airport
            
            if self.timezone_format == 'local':
                # Report time is in LOCAL timezone of departure airport
                dep_tz = pytz.timezone(dep_airport.timezone)
                report_time = dep_tz.localize(report_time_naive)
            else:  # zulu
                # Report time is already in UTC
                report_time = pytz.utc.localize(report_time_naive)
        else:
            # Fallback: report time = departure time - 1 hour
            report_time = segments[0].scheduled_departure_utc - timedelta(hours=1)
        
        if not report_time:
            return None  # No valid duty
        
        # Calculate release time: last landing + 30 minutes post-flight duty per EASA FTL
        # EASA defines FDP as report time to END OF LAST LANDING (not +1 hour)
        last_landing = segments[-1].scheduled_arrival_utc
        release_time = last_landing + timedelta(minutes=30)
        
        # Create duty
        # Use departure airport timezone as home base (will be corrected by parent parser)
        duty = Duty(
            duty_id=f"D{date.strftime('%Y%m%d')}",
            date=date,
            report_time_utc=report_time.astimezone(pytz.utc),
            release_time_utc=release_time,
            segments=segments,
            home_base_timezone=segments[0].departure_airport.timezone
        )
        
        return duty
    
    def _extract_segments_from_lines(
        self, 
        lines: List[str], 
        date: datetime
    ) -> List[FlightSegment]:
        """
        Extract flight segments using PATTERN DETECTION
        
        Pattern recognition (works with any flights):
        - Flight number: 3-4 digits
        - Airport code: 3 uppercase letters
        - Time: HH:MM format
        - Sequence: FlightNum to Airport to Time to Airport to Time
        """
        segments = []
        
        i = 0
        while i < len(lines):
            line = lines[i]
            
            # PATTERN 1: Look for flight number (3-4 digits, not a time)
            if re.match(r'^\d{3,4}$', line) and ':' not in line:
                flight_num = line
                
                # Look ahead for: AIRPORT TIME AIRPORT TIME
                if i + 4 >= len(lines):
                    i += 1
                    continue
                
                # PATTERN 2: Departure airport (3 letters)
                dep_code = lines[i + 1]
                if not re.match(r'^[A-Z]{3}$', dep_code):
                    i += 1
                    continue
                
                # PATTERN 3: Departure time (HH:MM)
                dep_time_str = lines[i + 2]
                if not re.search(r'\d{2}:\d{2}', dep_time_str):
                    i += 1
                    continue
                
                # PATTERN 4: Arrival airport (3 letters)
                arr_code = lines[i + 3]
                if not re.match(r'^[A-Z]{3}$', arr_code):
                    i += 1
                    continue
                
                # PATTERN 5: Arrival time (HH:MM)
                arr_time_str = lines[i + 4]
                if not re.search(r'\d{2}:\d{2}', arr_time_str):
                    i += 1
                    continue
                
                # VALID FLIGHT PATTERN DETECTED!
                dep_airport = self._get_or_create_airport(dep_code)
                arr_airport = self._get_or_create_airport(arr_code)
                
                # Skip if airports couldn't be created
                if not dep_airport or not arr_airport:
                    i += 5
                    continue
                
                # Parse times
                dep_time = self._parse_time(dep_time_str, date)
                arr_time = self._parse_time(arr_time_str, date)
                
                if not dep_time or not arr_time:
                    i += 5
                    continue
                
                # Convert to UTC based on timezone format
                try:
                    if self.timezone_format == 'local':
                        # Times are in LOCAL timezone of each airport
                        dep_tz = pytz.timezone(dep_airport.timezone)
                        arr_tz = pytz.timezone(arr_airport.timezone)
                        
                        dep_utc = dep_tz.localize(dep_time).astimezone(pytz.utc)
                        arr_utc = arr_tz.localize(arr_time).astimezone(pytz.utc)
                    
                    else:  # timezone_format == 'zulu'
                        # Times are already in UTC/Zulu
                        dep_utc = pytz.utc.localize(dep_time)
                        arr_utc = pytz.utc.localize(arr_time)
                    
                    segment = FlightSegment(
                        flight_number=flight_num,  # Keep as-is from PDF
                        departure_airport=dep_airport,
                        arrival_airport=arr_airport,
                        scheduled_departure_utc=dep_utc,
                        scheduled_arrival_utc=arr_utc
                    )
                    
                    segments.append(segment)
                    
                except Exception as e:
                    print(f"⚠️  Error creating segment for flight {flight_num}: {e}")
                
                # Skip past this flight's data
                i += 5
                continue
            
            i += 1
        
        return segments
    
    def _parse_time(self, time_str: str, date: datetime) -> Optional[datetime]:
        """Parse time string like "07:45" or "02:25(+1)" into datetime"""
        # Remove (+1) marker
        time_str = re.sub(r'\(\+\d+\)', '', time_str).strip()
        
        # Parse HH:MM
        match = re.match(r'(\d{2}):(\d{2})', time_str)
        if match:
            hour = int(match.group(1))
            minute = int(match.group(2))
            return datetime(date.year, date.month, date.day, hour, minute)
        
        return None
    
    def _extract_statistics(self, page) -> Dict:
        """Extract summary statistics from bottom of page"""
        text = page.extract_text()
        
        stats = {}
        
        # Look for statistics table
        stats_match = re.search(
            r'BLOCK\s+HOURS.*?VALUE\s+([\d:]+)\s+([\d:]+)',
            text,
            re.DOTALL
        )
        
        if stats_match:
            stats['block_hours'] = stats_match.group(1)
            stats['duty_hours'] = stats_match.group(2)
        
        return stats
