# Vercel v0 Prompts — Pilot Fatigue Analysis Tool Frontend

Copy-paste these prompts sequentially into v0.dev. Each builds on the previous one.

---

## PROMPT 1: Project Setup + Landing Page + Upload Flow

```
Build a Next.js app called "FatigueIQ" — a pilot fatigue risk analysis tool for airline crew.

Tech stack: Next.js 14 App Router, TypeScript, Tailwind CSS, shadcn/ui, Recharts, Lucide icons.

Color palette:
- Background: slate-950 (dark mode default)
- Primary accent: sky-500 / sky-400
- Risk colors: green-500 (low), amber-500 (moderate), orange-500 (high), red-500 (critical), red-700 (extreme)
- Cards: slate-900 with slate-800 borders
- Text: slate-50 primary, slate-400 secondary

Page 1 — Landing / Upload page ("/"):

Hero section:
- Large headline: "Know Your Fatigue Before You Fly"
- Subtitle: "Biomathematical fatigue modeling backed by 30+ peer-reviewed studies. Upload your roster, see your risk."
- Three small badges below subtitle: "EASA ORO.FTL Compliant" · "Borbély Two-Process Model" · "Educational Use"

Below hero, a centered upload card (max-w-2xl):
- Drag-and-drop zone with dashed border that accepts PDF or CSV files
- Text: "Drop your roster PDF or CSV here" with a file icon
- On file drop, show file name, size, and a remove button
- Below the drop zone, a collapsible "Settings" panel (default collapsed) with these fields:
  - Pilot ID (text input, default "P12345")
  - Month (month picker, default current month)
  - Home Base (text input with IATA code validation, default "DOH")
  - Home Timezone (select dropdown with common aviation timezones: Asia/Qatar, Europe/London, Europe/Paris, America/New_York, Asia/Dubai, Asia/Singapore, etc.)
  - Model Preset (radio group): Default EASA | Conservative | Liberal | Research — each with a one-line description:
    - Default EASA: "Balanced parameters per EASA research"
    - Conservative: "Stricter thresholds — flags more risk"
    - Liberal: "Relaxed thresholds — fewer flags"
    - Research: "Pure Borbély model — academic use"
- A large "Analyze Roster" button (sky-500, full width of card) that shows a loading spinner during analysis

The upload card should call this API:
POST {API_BASE_URL}/api/analyze
Content-Type: multipart/form-data
Fields: file, pilot_id, month (YYYY-MM), home_base, home_timezone, config_preset

Store API_BASE_URL in an environment variable NEXT_PUBLIC_API_URL (default http://localhost:8000).

On success, store the full AnalysisResult in React state and navigate to /analysis/[analysis_id].

TypeScript types for the API response (put in lib/types.ts):

interface DutySegment {
  flight_number: string;
  departure: string;
  arrival: string;
  departure_time: string;
  arrival_time: string;
  block_hours: number;
}

interface SleepBlock {
  sleep_start_time: string;
  sleep_end_time: string;
  sleep_start_iso: string;
  sleep_end_iso: string;
  sleep_type: string;
  duration_hours: number;
  effective_hours: number;
  quality_factor: number;
}

interface QualityFactors {
  base_efficiency: number;
  wocl_boost: number;
  late_onset_penalty: number;
  recovery_boost: number;
  time_pressure_factor: number;
  insufficient_penalty: number;
}

interface Reference {
  key: string;
  short: string;
  full: string;
}

interface SleepQuality {
  total_sleep_hours: number;
  effective_sleep_hours: number;
  sleep_efficiency: number;
  wocl_overlap_hours: number;
  sleep_strategy: string;
  confidence: number;
  warnings: string[];
  sleep_blocks: SleepBlock[];
  sleep_start_time: string | null;
  sleep_end_time: string | null;
  explanation: string | null;
  confidence_basis: string | null;
  quality_factors: QualityFactors | null;
  references: Reference[];
}

interface Duty {
  duty_id: string;
  date: string;
  report_time_utc: string;
  release_time_utc: string;
  report_time_local: string | null;
  release_time_local: string | null;
  duty_hours: number;
  sectors: number;
  segments: DutySegment[];
  min_performance: number;
  avg_performance: number;
  landing_performance: number | null;
  sleep_debt: number;
  wocl_hours: number;
  prior_sleep: number;
  pre_duty_awake_hours: number;
  risk_level: 'low' | 'moderate' | 'high' | 'critical' | 'extreme' | 'unknown';
  is_reportable: boolean;
  pinch_events: number;
  max_fdp_hours: number | null;
  extended_fdp_hours: number | null;
  used_discretion: boolean;
  sleep_quality: SleepQuality | null;
  time_validation_warnings: string[];
}

interface RestDaySleep {
  date: string;
  sleep_blocks: SleepBlock[];
  total_sleep_hours: number;
  effective_sleep_hours: number;
  sleep_efficiency: number;
  strategy_type: string;
  confidence: number;
}

interface AnalysisResult {
  analysis_id: string;
  roster_id: string;
  pilot_id: string;
  pilot_name: string;
  pilot_base: string;
  pilot_aircraft: string;
  month: string;
  total_duties: number;
  total_sectors: number;
  total_duty_hours: number;
  total_block_hours: number;
  high_risk_duties: number;
  critical_risk_duties: number;
  total_pinch_events: number;
  avg_sleep_per_night: number;
  max_sleep_debt: number;
  worst_duty_id: string;
  worst_performance: number;
  duties: Duty[];
  rest_days_sleep: RestDaySleep[];
}

Also create a global context or zustand store to hold the AnalysisResult so all pages can access it.
```

---

## PROMPT 2: Dashboard Overview Page

```
Now build the analysis dashboard page at /analysis/[analysis_id].

This is the main results page shown after a roster is analyzed. It reads the AnalysisResult from the store/context (populated in Prompt 1).

Layout: Full-width page with a fixed left sidebar (w-64) and scrollable main content area.

LEFT SIDEBAR:
- Pilot info card at top: name (from pilot_name), base (pilot_base), aircraft (pilot_aircraft), month
- Navigation links (vertically stacked, with Lucide icons):
  1. Dashboard (LayoutDashboard icon) — current page
  2. Duty Timeline (Calendar icon) — /analysis/[id]/timeline
  3. Duty Table (Table icon) — /analysis/[id]/duties
  4. Sleep Analysis (Moon icon) — /analysis/[id]/sleep
  5. Science (FlaskConical icon) — /analysis/[id]/science
- "New Analysis" button at bottom that navigates back to "/"
- Active link highlighted with sky-500 left border and sky-500/10 background

MAIN CONTENT — Dashboard:

Row 1: Four KPI stat cards in a grid (grid-cols-4):
1. "Duties Analyzed" — total_duties, with total_sectors sectors below in small text
2. "High Risk" — high_risk_duties count, red if > 0, with critical_risk_duties critical below
3. "Avg Sleep" — avg_sleep_per_night formatted to 1 decimal + "h", colored: green if >= 7, amber if >= 6, red if < 6
4. "Max Sleep Debt" — max_sleep_debt formatted to 1 decimal + "h", colored: green if < 2, amber if < 4, red if >= 4

Row 2: Two charts side by side (grid-cols-2):

Left chart — "Landing Performance Trend" (Recharts AreaChart):
- X axis: duty dates
- Y axis: 0-100 performance scale
- Area fill colored by risk thresholds: green above 75, amber 65-75, orange 55-65, red below 55
- Plot landing_performance for each duty (skip nulls)
- Horizontal reference lines at 75, 65, 55, 45 with subtle dashed style and labels "Low", "Moderate", "High", "Critical"
- Tooltip showing: date, flight numbers, landing performance, risk level

Right chart — "Sleep & Sleep Debt" (Recharts ComposedChart):
- Dual Y axis
- Left axis: prior_sleep (hours) as bars (sky-500)
- Right axis: sleep_debt (hours) as line (red-400)
- Horizontal reference line at 8h on left axis labeled "Baseline Need"
- X axis: duty dates

Row 3: "Risk Distribution" — full width card:
- Horizontal stacked bar showing count of duties by risk level
- Each segment colored: green (low), amber (moderate), orange (high), red (critical), dark-red (extreme)
- Labels on each segment showing count
- Below the bar, a sentence: "X of Y duties require attention (high risk or above)"

Row 4: "Worst Duty" highlight card:
- Finds the duty matching worst_duty_id
- Shows: date, flight segments, landing performance (large, colored), risk badge, sleep debt, prior sleep, WOCL hours, pre-duty awake hours
- If pre_duty_awake_hours > 17, show a warning badge: "17+ hours awake — equivalent to 0.05% BAC (Dawson & Reid 1997)"
- "View Details" button linking to the duty detail page
```

---

## PROMPT 3: Duty Table + Duty Detail Drawer

```
Build the Duty Table page at /analysis/[id]/duties.

Same sidebar layout as the dashboard. Main content:

A full-width data table (use shadcn Table or DataTable) showing all duties from the AnalysisResult.

Columns:
1. Date — formatted as "Mon DD" (e.g. "Feb 03")
2. Flights — segments mapped to flight_number, joined with " → " (e.g. "QR304 → QR305")
3. Route — first segment departure + " → " + last segment arrival (IATA codes)
4. Report — report_time_local or report_time_utc, formatted HH:mm
5. Release — release_time_local or release_time_utc, formatted HH:mm
6. Duty Hours — duty_hours to 1 decimal
7. Landing Perf — landing_performance as colored number (green >= 75, amber >= 65, orange >= 55, red < 55), show "-" if null
8. Sleep Debt — sleep_debt to 1 decimal + "h", colored red if > 4
9. Prior Sleep — prior_sleep to 1 decimal + "h", colored red if < 6
10. WOCL — wocl_hours to 1 decimal + "h", hidden if 0
11. Risk — colored badge (pill shape) showing risk_level text with appropriate background color
12. Alerts — icon indicators: moon icon if wocl_hours > 0, alert-triangle if pinch_events > 0, clock if pre_duty_awake_hours > 16

Table features:
- Sortable by any column (click column header)
- Filterable by risk level (dropdown filter above table: All, Low, Moderate, High, Critical, Extreme)
- Row click opens a slide-over detail drawer from the right

DUTY DETAIL DRAWER (Sheet component, right side, w-[600px]):

When a duty row is clicked, open a drawer that calls this API for 5-minute-resolution timeline data:
GET {API_BASE_URL}/api/duty/{analysis_id}/{duty_id}

Response type:
interface TimelinePoint {
  timestamp: string;
  performance: number;
  sleep_pressure: number;
  circadian: number;
  sleep_inertia: number;
  hours_on_duty: number;
  time_on_task_penalty: number;
  flight_phase: string | null;
  is_critical: boolean;
}

interface PinchEvent {
  timestamp: string;
  performance: number;
  phase: string | null;
  cause: string;
}

interface DutyDetail {
  duty_id: string;
  timeline: TimelinePoint[];
  summary: { min_performance, avg_performance, landing_performance, wocl_hours, prior_sleep, pre_duty_awake_hours, sleep_debt };
  pinch_events: PinchEvent[];
}

Drawer contents:

Section 1 — Header:
- Date and flight numbers
- Route with IATA codes
- Risk level badge (large)

Section 2 — "Performance Timeline" (Recharts LineChart):
- X axis: timestamps (HH:mm format)
- Y axis: 0-100
- Three lines: performance (sky-500, thick), sleep_pressure mapped to 20+((1-value)*80) (amber-400, dashed), circadian mapped to 20+(((value+1)/2)*80) (violet-400, dashed)
- Background colored bands for risk zones: green (75-100), amber (65-75), orange (55-65), red (0-55)
- Vertical markers for flight phases if available (takeoff, landing labeled)
- Red dots for pinch events
- Tooltip: timestamp, performance, sleep pressure (raw), circadian (raw), flight phase, time on task penalty

Section 3 — "Fatigue Factors" metrics grid (2x3):
- Landing Performance (large colored number)
- Prior Sleep (hours)
- Sleep Debt (hours)
- WOCL Exposure (hours)
- Pre-Duty Awake (hours)
- Pinch Events (count, red if > 0)

Section 4 — "Sleep Analysis" (only if sleep_quality exists on the duty):
- Strategy badge showing sleep_quality.sleep_strategy (e.g. "Early Morning Strategy")
- Explanation text from sleep_quality.explanation in an info callout box
- Confidence bar (progress bar 0-100% from sleep_quality.confidence)
- Confidence basis text from sleep_quality.confidence_basis
- Sleep blocks listed: each block showing start time → end time, duration, effective hours, quality factor as a mini bar
- Quality factors breakdown as a horizontal bar chart: base_efficiency, wocl_boost, late_onset_penalty, recovery_boost, time_pressure_factor, insufficient_penalty — each bar 0-1.0, colored green if >= 0.95, amber if >= 0.85, red if < 0.85

Section 5 — "Scientific References" (collapsible):
- List sleep_quality.references showing short citation and full citation on expand
- Each reference with a small book icon

Section 6 — "EASA Compliance":
- FDP limit: max_fdp_hours
- Extended limit: extended_fdp_hours
- Actual FDP: duty_hours
- Progress bar showing duty_hours / max_fdp_hours, turning red if > 100%
- "Commander Discretion Used" badge if used_discretion is true
- Any time_validation_warnings shown as amber alert boxes
```

---

## PROMPT 4: Duty Timeline (Visual Calendar View)

```
Build the Duty Timeline page at /analysis/[id]/timeline.

Same sidebar layout. Main content:

A monthly calendar/timeline visualization showing every day of the month.

Layout: 7-column grid (Mon-Sun) calendar view, each cell representing one day.

Each day cell:
- Day number in top-left corner
- If the day has a duty (match by date):
  - Colored bar spanning the cell, color = risk_level color
  - Flight numbers in small text (e.g. "QR304/305")
  - Report time in top-right (small, slate-400)
  - Landing performance score centered in a circle badge (colored by risk)
  - Small icons at bottom: moon if WOCL > 0, triangle if pinch_events > 0
- If the day is a rest day (found in rest_days_sleep):
  - Light blue background tint
  - "OFF" label
  - Sleep hours shown: e.g. "8.0h sleep"
- If the day has neither, leave it empty/dimmed

Below the calendar, show a "Month Summary Bar" — a single horizontal bar chart where each day is a thin vertical bar, height = landing_performance (0-100 scale), colored by risk level. Rest days are shown as thin gray bars. This creates a quick visual "heartbeat" of the entire month.

Add toggle buttons above the calendar:
- "Color by: Risk Level | Performance | Sleep Debt" — changes what colors the day cells
- When "Performance": gradient from green (100) to red (0)
- When "Sleep Debt": gradient from green (0h) to red (8h+)

Clicking any duty day should navigate to /analysis/[id]/duties with that duty's drawer open (or scroll to it).
```

---

## PROMPT 5: Sleep Analysis Deep-Dive Page

```
Build the Sleep Analysis page at /analysis/[id]/sleep.

Same sidebar layout. Main content:

This page focuses entirely on sleep patterns, quality, and the science behind the estimates.

Section 1 — "Sleep Overview" (full-width card):
- Large stat: avg_sleep_per_night with "h average" suffix
- Comparison text: "vs 8.0h baseline need (Van Dongen et al. 2003)"
- A horizontal sparkline showing prior_sleep for each duty across the month, with a dashed line at 8h

Section 2 — "Sleep Architecture" chart (full width, Recharts):
A 24-hour timeline chart (Y axis = days of month, X axis = 00:00-23:59):
- For each day, draw horizontal bars representing sleep blocks (from rest_days_sleep and duties' sleep_quality.sleep_blocks)
- Color blocks by sleep_type: main sleep = indigo-600, nap = sky-400, anchor = violet-500, inflight = amber-400
- Shade the WOCL zone (02:00-05:59) with a subtle vertical band
- This creates a "raster plot" showing when the pilot sleeps across the entire month
- Legend at top: Main Sleep, Nap, Anchor Sleep, Inflight Rest, WOCL Zone

Section 3 — "Sleep Strategy Distribution" (two cards side by side):

Left card — Donut chart showing count of each sleep_strategy type used:
- Normal (green)
- Night Departure (indigo)
- Early Morning (amber)
- WOCL/Anchor (violet)
- Recovery (sky)

Right card — "Effective vs Raw Sleep" bar chart:
- For each duty, two bars: total_sleep_hours (lighter) and effective_sleep_hours (darker)
- Shows the quality penalty visually — the gap between raw and effective sleep

Section 4 — "Quality Factor Analysis" (full-width card):
- Six mini box plots or bar charts, one for each quality factor across all duties:
  1. Base Efficiency — distribution of base_efficiency values
  2. Circadian Alignment — distribution of wocl_boost values
  3. Late Onset Penalty — distribution of late_onset_penalty values
  4. Recovery Boost — distribution of recovery_boost values
  5. Time Pressure — distribution of time_pressure_factor values
  6. Insufficient Sleep — distribution of insufficient_penalty values
- Each shows min, max, mean as a simple range bar with a dot at the mean
- Colored: green if mean > 0.95, amber if > 0.85, red if <= 0.85

Section 5 — "Sleep Debt Accumulation" (full-width chart, Recharts AreaChart):
- X axis: all days of the month (duties + rest days)
- Y axis: cumulative sleep debt (hours)
- Area fill: gradient from green (0h) to red (8h+)
- Vertical dotted lines marking rest days
- Annotation showing "Debt recovery" on rest days where debt decreases
```

---

## PROMPT 6: Science/Methodology Transparency Page

```
Build the Science page at /analysis/[id]/science.

Same sidebar layout. This page explains the science behind every calculation, making the tool credible and educational.

Section 1 — "Model Overview" hero card:
- Title: "Borbély Two-Process Sleep Regulation Model"
- Subtitle: "The gold standard in fatigue biomathematics since 1982"
- Three-column layout explaining:
  Column 1 — "Process S (Homeostatic)":
    - Icon: battery icon
    - "Sleep pressure builds during wakefulness and dissipates during sleep"
    - "Buildup: τ_i = 18.2h (Jewett & Kronauer 1999)"
    - "Decay: τ_d = 4.2h"
    - Small formula: S(t) = S_max - (S_max - S₀) × e^(-t/τ)
  Column 2 — "Process C (Circadian)":
    - Icon: sun/moon icon
    - "24-hour biological clock driving alertness peaks and troughs"
    - "Peak alertness: ~16:00 (acrophase)"
    - "Minimum: ~04:00 (WOCL nadir)"
    - Small formula: C(t) = 0.5 + 0.3 × cos(2π(t-16)/24)
  Column 3 — "Process W (Sleep Inertia)":
    - Icon: alarm-clock icon
    - "Grogginess upon waking that impairs performance"
    - "Duration: 30 minutes (Tassi & Muzet 2000)"
    - "Max magnitude: 30% performance penalty"
    - Small formula: W(t) = 0.30 × e^(-t/10)

Section 2 — "Performance Calculation" card:
- Step-by-step breakdown with numbered steps:
  1. "Base Alertness = (1-S) × 0.6 + ((C+1)/2) × 0.4"
  2. "Apply sleep inertia: Alertness × (1 - W)"
  3. "Apply time-on-task: -0.008 per hour on duty (Folkard & Åkerstedt 1999)"
  4. "Scale to 0-100: Performance = 20 + (Alertness × 80)"
  5. "Floor at 20 = severe impairment (~0.05% BAC, Dawson & Reid 1997)"
- Diagram showing the formula visually if possible

Section 3 — "Risk Thresholds" table:
| Risk Level | Score Range | EASA Reference | Required Action |
| Low | 75-100 | ORO.FTL.120 | No action needed |
| Moderate | 65-75 | AMC1 ORO.FTL.120 | Enhanced monitoring |
| High | 55-65 | GM1 ORO.FTL.235 | Mitigation required |
| Critical | 45-55 | ORO.FTL.120(a) | Mandatory roster modification |
| Extreme | 0-45 | ORO.FTL.120(b) | Do not fly |

Use the risk colors for each row background.

Section 4 — "Sleep Estimation Strategies" accordion/tabs:
Five expandable cards, one per strategy:

1. "Normal Sleep" (report 07:00-19:59, no WOCL crossing):
   - Pattern: 23:00-07:00 (8h)
   - Confidence: 70%
   - "Standard sleep-wake pattern when no circadian disruption occurs"

2. "Early Morning" (report before 07:00):
   - Pattern: Roach regression — sleep = 6.6 - 0.25 × max(0, 9 - report_hour) hours
   - Confidence: 55%
   - "Pilots cannot fully advance bedtime. Based on actigraphy data from Roach et al. (2012)"
   - Show example: "05:00 report → 6.6 - 0.25×4 = 5.6h sleep"

3. "Night Departure" (report >= 20:00 or < 04:00):
   - Pattern: Morning sleep 23:00-07:00 (8h) + optional 2h pre-duty nap (54% uptake)
   - Confidence: 60%
   - "Signal et al. (2014): Pre-departure naps are common but not universal"

4. "WOCL/Anchor Sleep" (crosses 02:00-05:59, duty > 6h):
   - Pattern: 4.5h anchor block ending 1.5h before duty
   - Confidence: 65%
   - "Minors & Waterhouse (1981, 1983): Anchor sleep of ≥4h maintains circadian stability"

5. "Recovery (Rest Days)":
   - Pattern: 23:00-07:00 at 95% quality
   - Confidence: 80%
   - "Full recovery sleep without duty constraints"

Section 5 — "References" (full width):
A clean bibliography list of all scientific references. Show ~15-20 key citations grouped by category:

Fatigue Modeling:
- Borbély & Achermann (1999) — Two-process sleep regulation model
- Jewett & Kronauer (1999) — Tau constants
- Van Dongen et al. (2003) — Cumulative cost of additional wakefulness

Aviation Sleep Research:
- Roach et al. (2012) — Early morning duty sleep restriction
- Signal et al. (2014) — Pre-departure nap behavior
- Signal et al. (2013) — In-flight sleep quality (PSG)
- Gander et al. (2014) — Pilot fatigue and departure times

Circadian Physiology:
- Dijk & Czeisler (1994, 1995) — Sleep consolidation
- Waterhouse et al. (2007) — Jet lag adaptation rates
- Aschoff (1978) — Circadian features for shift work

Performance & Impairment:
- Dawson & Reid (1997) — Fatigue-alcohol equivalence (17h = 0.05% BAC)
- Folkard & Åkerstedt (1999) — Time-on-task effects
- Tassi & Muzet (2000) — Sleep inertia duration

Regulatory:
- EU Regulation 965/2012 (EASA ORO.FTL)
- Moebus Report (2013) — EASA evidence-based assessment

Section 6 — Disclaimer card (subtle, bottom):
"FatigueIQ is an educational tool. It does not replace SMS fatigue risk assessments, medical judgment, or regulatory compliance processes. All parameters are derived from published research but individual variation exists. Use as one input among many in fatigue risk management."
```

---

## PROMPT 7: Polish, Animations, and Mobile Responsiveness

```
Polish the entire FatigueIQ app with these improvements:

1. ANIMATIONS:
- Page transitions: fade-in with subtle upward slide (150ms)
- Cards: stagger-fade on initial load (each card delays 50ms more than previous)
- Charts: animate on scroll into viewport (use Intersection Observer)
- Number counters: animate from 0 to final value over 600ms on the KPI cards
- Drawer: slide in from right with backdrop blur
- Upload zone: pulse animation on drag-over, success checkmark animation on file accepted
- Risk badges: subtle pulse animation on critical/extreme duties
- Skeleton loaders while waiting for API responses (use shadcn Skeleton)

2. MOBILE RESPONSIVENESS:
- Sidebar collapses to a hamburger menu on screens < 1024px
- KPI grid goes from 4 columns → 2 columns on tablet → 1 column on mobile
- Charts stack vertically on mobile
- Duty table becomes a card list on mobile (each duty = one card with key metrics)
- Drawer becomes full-screen sheet on mobile

3. HEADER BAR (fixed top, h-14):
- Left: FatigueIQ logo text (font-mono, sky-400)
- Center: pilot name + month (if analysis loaded)
- Right: theme toggle (dark/light), "Export Report" button (generates a summary)

4. TOAST NOTIFICATIONS:
- Success: "Analysis complete — X duties analyzed, Y flagged high risk"
- Error: Show API error message
- Warning: Show if any duties have time_validation_warnings

5. EMPTY STATES:
- No analysis yet: illustration with "Upload a roster to get started"
- No high-risk duties: celebration graphic with "All duties within safe limits"
- API unreachable: "Backend not connected" with retry button and health check to GET /health

6. KEYBOARD SHORTCUTS:
- Cmd+K: Quick search (search duties by date or flight number)
- Escape: Close any open drawer/modal
- Arrow keys: Navigate between duties in the table

7. PRINT STYLES:
- @media print: hide sidebar, expand content to full width
- Clean black-and-white risk indicators
- Page breaks between sections
```

---

## PROMPT 8 (Optional): Export/Report Generation

```
Add a "Generate Report" feature accessible from the header "Export Report" button.

When clicked, open a modal with options:
1. "Summary PDF" — generates a single-page executive summary
2. "Full Report" — comprehensive multi-page PDF
3. "CSV Export" — raw data table

For the Summary PDF (using @react-pdf/renderer or html2canvas + jsPDF):

Page layout:
- Header: "FATIGUE RISK ASSESSMENT — [Month Year]" with FatigueIQ branding
- Pilot info: Name, Base, Aircraft, Analysis ID
- Risk summary: pie chart of risk distribution + key stats
- Top 5 highest-risk duties table: date, flights, landing performance, risk level, key contributing factor
- Sleep summary: average sleep, max debt, worst night
- Footer: "Generated by FatigueIQ — Educational use only. Based on Borbély two-process model. See full methodology at [app URL]/science"
- Disclaimer: "This report is for educational and personal awareness purposes. It does not constitute a formal fatigue risk assessment under EASA ORO.FTL regulations."

For CSV Export:
- Headers: Date, Duty_ID, Flights, Route, Report_UTC, Release_UTC, Duty_Hours, Landing_Performance, Min_Performance, Sleep_Debt, Prior_Sleep, WOCL_Hours, Pre_Duty_Awake, Risk_Level, Sleep_Strategy, Pinch_Events
- One row per duty
- Download as "[pilot_id]_[month]_fatigue_analysis.csv"
```
