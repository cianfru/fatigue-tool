# fatigue_app.py - Streamlit Web Interface

"""
EASA Fatigue Analysis Tool - Web Interface

Complete Streamlit application for:
- Roster upload (PDF/CSV)
- Fatigue analysis
- Interactive results display
- Report generation

Usage:
    streamlit run fatigue_app.py
"""

import streamlit as st
import sys
import os
from pathlib import Path
import tempfile
from datetime import datetime
import traceback

# Try importing folium with error handling
try:
    from streamlit_folium import st_folium
    HAS_FOLIUM = True
except ImportError:
    HAS_FOLIUM = False

# Add current directory to path
sys.path.append(str(Path(__file__).parent))

# Import modules
from core_model import BorbelyFatigueModel
from roster_parser import PDFRosterParser, CSVRosterParser, AirportDatabase
from easa_utils import FatigueRiskScorer
from visualization import FatigueVisualizer
from aviation_calendar import AviationCalendar
from chronogram import FatigueChronogram
from config import ModelConfig
import pandas as pd

# ============================================================================
# PAGE CONFIGURATION
# ============================================================================

st.set_page_config(
    page_title="Fatigue Analysis Tool",
    page_icon="✈️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============================================================================
# SESSION STATE INITIALIZATION
# ============================================================================

if 'analysis_complete' not in st.session_state:
    st.session_state.analysis_complete = False
if 'monthly_analysis' not in st.session_state:
    st.session_state.monthly_analysis = None
if 'roster' not in st.session_state:
    st.session_state.roster = None

# ============================================================================
# SIDEBAR - SETTINGS
# ============================================================================

st.sidebar.title("⚙️ Settings")

# Pilot ID
pilot_id = st.sidebar.text_input(
    "Pilot ID",
    value="P12345",
    help="Enter your pilot identifier"
)

# Home Base Selection
home_base_options = {
    "DOH - Doha, Qatar": ("DOH", "Asia/Qatar"),
    "LHR - London Heathrow": ("LHR", "Europe/London"),
    "JFK - New York": ("JFK", "America/New_York"),
    "DXB - Dubai": ("DXB", "Asia/Dubai"),
    "SIN - Singapore": ("SIN", "Asia/Singapore"),
    "HKG - Hong Kong": ("HKG", "Asia/Hong_Kong"),
    "SYD - Sydney": ("SYD", "Australia/Sydney"),
    "LAX - Los Angeles": ("LAX", "America/Los_Angeles"),
    "FRA - Frankfurt": ("FRA", "Europe/Berlin"),
    "CDG - Paris": ("CDG", "Europe/Paris"),
}

selected_base = st.sidebar.selectbox(
    "Home Base",
    list(home_base_options.keys()),
    help="Select your home base airport"
)
home_base_code, home_timezone = home_base_options[selected_base]

# Calendar Date Selection
st.sidebar.subheader("📅 Analysis Period")

date_selection_method = st.sidebar.radio(
    "Select period:",
    ["Single Month", "Date Range"],
    help="Choose how to select your analysis period"
)

if date_selection_method == "Single Month":
    selected_date = st.sidebar.date_input(
        "Select Month",
        value=datetime.now().date(),
        help="Select any day in the month you want to analyze"
    )
    month = selected_date.strftime("%Y-%m")
else:  # Date Range
    col1, col2 = st.sidebar.columns(2)
    with col1:
        start_date = st.date_input(
            "Start Date",
            value=datetime.now().replace(day=1).date(),
            help="First day of analysis period"
        )
    with col2:
        end_date = st.date_input(
            "End Date",
            value=datetime.now().date(),
            help="Last day of analysis period"
        )
    # For multi-month analysis, use start month for parsing
    month = start_date.strftime("%Y-%m")

st.sidebar.markdown("---")

# Theme Toggle
st.sidebar.subheader("🎨 Appearance")
theme = st.sidebar.radio(
    "Theme:",
    ["🌙 Dark", "☀️ Light"],
    help="Choose your preferred theme"
)
selected_theme = "dark" if "Dark" in theme else "light"

# Apply theme CSS
if selected_theme == "dark":
    st.markdown("""
    <style>
        :root {
            --primary-color: #ffffff;
            --background-color: #0e1117;
            --secondary-background-color: #161b22;
            --text-color: #c9d1d9;
        }
        body {
            background-color: #0e1117;
            color: #c9d1d9;
        }
        .stApp {
            background-color: #0e1117;
        }
        .stMarkdown {
            color: #c9d1d9;
        }
        [data-testid="stSidebar"] {
            background-color: #161b22;
        }
        [data-testid="stMetricValue"] {
            color: #ffffff;
        }
    </style>
    """, unsafe_allow_html=True)
else:
    st.markdown("""
    <style>
        :root {
            --primary-color: #000000;
            --background-color: #ffffff;
            --secondary-background-color: #f1f3f5;
            --text-color: #31333f;
        }
        body {
            background-color: #ffffff;
            color: #31333f;
        }
        .stApp {
            background-color: #ffffff;
        }
        .stMarkdown {
            color: #31333f;
        }
        [data-testid="stSidebar"] {
            background-color: #f1f3f5;
        }
        [data-testid="stMetricValue"] {
            color: #000000;
        }
    </style>
    """, unsafe_allow_html=True)

st.sidebar.markdown("---")

# Model Configuration
st.sidebar.subheader("🔬 Model Configuration")

config_options = {
    "Default (EASA)": ModelConfig.default_easa_config(),
    "Conservative": ModelConfig.conservative_config(),
    "Liberal (Airline)": ModelConfig.liberal_config(),
    "Research": ModelConfig.research_config()
}

selected_config = st.sidebar.selectbox(
    "Configuration Preset",
    list(config_options.keys()),
    help="Default: Balanced EASA-compliant\nConservative: Safety-critical ops\nLiberal: Airline assumptions\nResearch: Academic validation"
)

config = config_options[selected_config]

# Show config details
with st.sidebar.expander("ℹ️ Configuration Details"):
    st.write(f"**Interaction Exponent:** {config.borbely_params.interaction_exponent}")
    st.write(f"**High Risk Threshold:** {config.risk_thresholds.thresholds['high'][0]}")
    st.write(f"**Critical Risk Threshold:** {config.risk_thresholds.thresholds['critical'][0]}")

st.sidebar.markdown("---")

# Help
with st.sidebar.expander("📖 How to Use"):
    st.markdown("""
    **Step 1:** Upload your roster (PDF or CSV)
    
    **Step 2:** Click "Analyze Roster"
    
    **Step 3:** Review results by duty
    
    **Step 4:** Download PDF report
    
    **Supported Formats:**
    - Qatar Airways CrewLink PDF
    - Generic CSV exports
    
    **Need Help?**
    - Ensure airports are in database
    - Check date formats match
    - Verify timezone settings
    """)

# ============================================================================
# MAIN CONTENT
# ============================================================================

st.title("✈️ EASA Fatigue Analysis Tool")
st.markdown("*Biomathematical fatigue prediction based on Borbély two-process model*")
st.markdown("**Version 2.1.2** | EASA ORO.FTL Compliant")
st.markdown("---")

# ============================================================================
# STEP 1: UPLOAD ROSTER
# ============================================================================

st.header("📄 Step 1: Upload Roster")

uploaded_file = st.file_uploader(
    "Choose your roster file",
    type=["pdf", "csv"],
    help="Supported formats: PDF (CrewLink), CSV export"
)

if uploaded_file:
    st.success(f"✅ File uploaded: {uploaded_file.name}")
    
    # Show file details
    with st.expander("📋 File Details"):
        col1, col2, col3 = st.columns(3)
        with col1:
            st.write(f"**Name:** {uploaded_file.name}")
        with col2:
            st.write(f"**Size:** {uploaded_file.size:,} bytes")
        with col3:
            file_type = "PDF" if uploaded_file.name.endswith('.pdf') else "CSV"
            st.write(f"**Type:** {file_type}")
    
    st.markdown("---")
    
    # ========================================================================
    # STEP 2: RUN ANALYSIS
    # ========================================================================
    
    st.header("🚀 Step 2: Run Analysis")
    
    col1, col2 = st.columns([1, 3])
    
    with col1:
        analyze_button = st.button(
            "🔬 Analyze Roster",
            type="primary",
            use_container_width=True
        )
    
    with col2:
        if st.session_state.analysis_complete:
            st.info("✅ Analysis complete - results shown below")
    
    if analyze_button:
        
        try:
            # Parse roster
            with st.spinner("📄 Parsing roster..."):
                
                # Save uploaded file temporarily
                with tempfile.NamedTemporaryFile(delete=False, suffix=Path(uploaded_file.name).suffix) as tmp:
                    tmp.write(uploaded_file.read())
                    tmp_path = tmp.name
                
                st.write(f"DEBUG: File saved to {tmp_path}, file type: {Path(uploaded_file.name).suffix}")
                
                if uploaded_file.name.endswith('.pdf'):
                    st.write("DEBUG: Using PDF parser")
                    parser = PDFRosterParser(
                        home_base=home_base_code,
                        home_timezone=home_timezone
                    )
                    roster = parser.parse_pdf(tmp_path, pilot_id, month)
                else:  # CSV
                    st.write("DEBUG: Using CSV parser")
                    parser = CSVRosterParser(
                        home_base=home_base_code,
                        home_timezone=home_timezone
                    )
                    roster = parser.parse_csv(tmp_path, pilot_id, month)
                
                st.write(f"DEBUG: Parsed successfully - duties: {roster.total_duties}, sectors: {roster.total_sectors}")
            
            st.success(f"✅ Parsed {roster.total_duties} duties, {roster.total_sectors} sectors")
            
            # Store roster
            st.session_state.roster = roster
            
            # Run fatigue analysis
            with st.spinner("🧠 Running biomathematical analysis..."):
                st.write("DEBUG: Starting analysis...")
                model = BorbelyFatigueModel(config)
                monthly_analysis = model.simulate_roster(roster)
                st.write(f"DEBUG: Analysis complete - {len(monthly_analysis.duty_timelines)} duty timelines")
            
            st.success("✅ Analysis complete!")
            
            # Store results
            st.session_state.monthly_analysis = monthly_analysis
            st.session_state.analysis_complete = True
            
            st.write("DEBUG: About to rerun...")
            # Force rerun to show results
            st.rerun()
            
        except Exception as e:
            st.error(f"❌ **ERROR during analysis:** {str(e)}")
            st.write("**Full Error Trace:**")
            st.code(traceback.format_exc(), language="python")
            st.info("💡 **Troubleshooting:**\n- Check if all airports are in the database\n- Verify date format matches expected format\n- Ensure roster file is not corrupted")

else:
    st.info("👆 Please upload a roster file to continue")

# ============================================================================
# STEP 3: SHOW RESULTS
# ============================================================================

if st.session_state.analysis_complete and st.session_state.monthly_analysis:
    
    monthly_analysis = st.session_state.monthly_analysis
    roster = st.session_state.roster
    
    # Initialize visualizer once for all charts
    viz = FatigueVisualizer(config, theme=selected_theme)
    
    st.markdown("---")
    st.header("📊 Step 3: Results")
    
    # ========================================================================
    # SUMMARY METRICS
    # ========================================================================
    
    st.subheader("Summary Statistics")
    
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col1:
        st.metric(
            "Total Duties",
            roster.total_duties
        )
    
    with col2:
        st.metric(
            "Total Sectors",
            roster.total_sectors
        )
    
    with col3:
        st.metric(
            "High Risk Duties",
            monthly_analysis.high_risk_duties,
            delta=f"{monthly_analysis.high_risk_duties} duties" if monthly_analysis.high_risk_duties > 0 else None,
            delta_color="inverse"
        )
    
    with col4:
        st.metric(
            "Critical Risk",
            monthly_analysis.critical_risk_duties,
            delta=f"{monthly_analysis.critical_risk_duties} duties" if monthly_analysis.critical_risk_duties > 0 else None,
            delta_color="inverse"
        )
    
    with col5:
        st.metric(
            "Max Sleep Debt",
            f"{monthly_analysis.max_sleep_debt:.1f}h",
            delta=f"{monthly_analysis.max_sleep_debt:.1f}h" if monthly_analysis.max_sleep_debt > 5 else None,
            delta_color="inverse"
        )
    
    # ========================================================================
    # OVERALL ASSESSMENT
    # ========================================================================
    
    st.markdown("---")
    
    if monthly_analysis.critical_risk_duties > 0:
        st.error(f"⚠️ **CRITICAL:** {monthly_analysis.critical_risk_duties} duties with critical risk detected. SMS reporting required per EASA ORO.FTL.120")
    elif monthly_analysis.high_risk_duties > 0:
        st.warning(f"⚠️ **WARNING:** {monthly_analysis.high_risk_duties} duties with high risk detected. Review mitigation strategies.")
    else:
        st.success("✅ No high-risk duties detected in this roster.")
    
    # ========================================================================
    # MONTH CALENDAR VIEW
    # ========================================================================
    
    st.markdown("---")
    st.subheader("� Monthly Chronogram - High-Resolution Timeline")
    st.markdown("*30-minute resolution showing duty timing, WOCL exposure, and fatigue patterns*")
    
    try:
        # Mode selector
        col1, col2 = st.columns([3, 1])
        with col1:
            chrono_mode = st.radio(
                "Display Mode",
                ["risk", "state", "hybrid"],
                format_func=lambda x: {
                    "risk": "🎨 Performance Heatmap (shows fatigue levels)",
                    "state": "📊 Duty/Rest Timeline (simple)",
                    "hybrid": "🔄 Combined View"
                }[x],
                horizontal=True
            )
        
        with col2:
            show_patterns = st.checkbox("Show Pattern Detection", value=True)
        
        # Generate chronogram
        chrono = FatigueChronogram(theme='light')
        
        with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as tmp:
            chrono.plot_monthly_chronogram(
                monthly_analysis,
                save_path=tmp.name,
                mode=chrono_mode,
                show_annotations=show_patterns
            )
            
            st.image(tmp.name, use_container_width=True)
        
        # Explanation
        with st.expander("ℹ️ How to Read This Chart"):
            st.markdown("""
            **What You're Seeing:**
            - Each row = One day of the month
            - Each column = 30-minute time slot
            - Purple shading = WOCL (Window of Circadian Low, 02:00-06:00)
            - Color intensity = Fatigue risk (green=good, red=high risk)
            
            **Key Insights:**
            - **Vertical patterns** = Same time of day duties (circadian alignment)
            - **Diagonal shifts** = "The Flip" (circadian disruption)
            - **Horizontal bands** = Multi-day duty or ultra-long-haul
            - **Purple overlap** = WOCL exposure (highest fatigue risk)
            
            **Pattern Warnings:**
            - ⚠️ WOCL = Multiple consecutive night duties
            - ⚠️ FLIP = Large circadian phase shift (>8h)
            """)
    
    except Exception as e:
        st.error(f"Error generating chronogram: {str(e)}")
        with st.expander("🔍 Technical Details"):
            st.code(traceback.format_exc())
    
    # ========================================================================
    # DUTY-BY-DUTY ANALYSIS
    # ========================================================================
    
    st.markdown("---")
    st.subheader("Duty Analysis")
    
    # Create tabs for each duty with formatted dates
    tab_labels = [f"{dt.duty_date.strftime('%a, %b %d')}" for dt in monthly_analysis.duty_timelines]
    duty_tabs = st.tabs(tab_labels)
    
    scorer = FatigueRiskScorer(config.risk_thresholds)
    
    for i, (tab, duty_timeline) in enumerate(zip(duty_tabs, monthly_analysis.duty_timelines)):
        with tab:
            
            duty = roster.duties[i]
            
            # Duty header with date
            st.markdown(f"### {duty_timeline.duty_date.strftime('%A, %B %d, %Y')}")
            
            # Duty details
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.write(f"**Date:** {duty_timeline.duty_date.strftime('%d-%b-%Y')}")
                st.write(f"**Duty Hours:** {duty.duty_hours:.1f}h")
                st.write(f"**Sectors:** {len(duty.segments)}")
            
            with col2:
                st.write(f"**Min Performance:** {duty_timeline.min_performance:.1f}/100")
                st.write(f"**Avg Performance:** {duty_timeline.average_performance:.1f}/100")
                if duty_timeline.landing_performance:
                    st.write(f"**Landing Performance:** {duty_timeline.landing_performance:.1f}/100")
            
            with col3:
                st.write(f"**Sleep Debt:** {duty_timeline.cumulative_sleep_debt:.1f}h")
                st.write(f"**WOCL Exposure:** {duty_timeline.wocl_encroachment_hours:.1f}h")
                st.write(f"**Prior Sleep:** {duty_timeline.prior_sleep_hours:.1f}h")
            
            # Flight segments
            with st.expander("✈️ Flight Segments"):
                for seg in duty.segments:
                    st.write(f"**{seg.flight_number}:** {seg.departure_airport.code} → {seg.arrival_airport.code} ({seg.block_time_hours:.1f}h)")
            
            # Risk assessment
            risk = scorer.score_duty_timeline(duty_timeline)
            
            st.markdown("---")
            st.markdown("#### Risk Assessment")
            
            # Risk level with color
            risk_colors_st = {
                'low': '🟢',
                'moderate': '🟡',
                'high': '🟠',
                'critical': '🔴',
                'extreme': '🔴'
            }
            
            risk_level = risk['overall_risk']
            risk_icon = risk_colors_st.get(risk_level, '⚪')
            
            st.markdown(f"**Overall Risk:** {risk_icon} **{risk_level.upper()}**")
            
            col1, col2 = st.columns(2)
            with col1:
                st.write(f"**Minimum Performance Risk:** {risk['min_performance_risk'].upper()}")
            with col2:
                st.write(f"**Landing Risk:** {risk['landing_risk'].upper()}")
            
            # SMS Reportable
            if risk['is_reportable']:
                st.error("⚠️ **SMS Reportable** - File fatigue report per EASA ORO.FTL.120")
            
            # Pinch events
            if duty_timeline.pinch_events:
                st.warning(f"⚠️ **{len(duty_timeline.pinch_events)} Pinch Event(s) Detected** (High S + Low C during critical phase)")
            
            # Recommendations
            with st.expander("📋 Detailed Assessment & Recommendations"):
                st.write(f"**Recommended Action:**")
                st.info(risk['recommended_action'])
                
                st.write(f"**EASA Reference:**")
                st.write(risk['easa_reference'])
                
                st.write(f"**Description:**")
                st.write(risk['description'])
                
                if risk['additional_warnings']:
                    st.write("**Additional Warnings:**")
                    for warning in risk['additional_warnings']:
                        st.write(f"  - ⚠️ {warning}")
            
            # Visualization
            st.markdown("---")
            st.markdown("#### Performance Timeline")
            
            try:
                fig = viz.create_unified_timeline(duty_timeline)
                if fig:
                    st.plotly_chart(fig, use_container_width=True)
            except Exception as e:
                st.error(f"Could not generate plot: {str(e)}")
    
    # ========================================================================
    # ROUTE VISUALIZATION
    # ========================================================================
    
    st.markdown("---")
    st.subheader("🌍 Route Network Analysis")
    
    if not HAS_FOLIUM:
        st.warning("📦 Folium dependency not yet installed. Please wait for Streamlit Cloud to rebuild, or redeploy the app.")
        st.info("Dependencies are being installed from requirements.txt. This typically takes 1-2 minutes.")
    else:
        try:
            route_map = viz.create_route_map_folium(monthly_analysis)
            if route_map:
                st_folium(route_map, width=1400, height=600)
            else:
                st.warning("No flight routes available to display")
        except Exception as e:
            st.warning(f"Route map not available: {str(e)}")
            with st.expander("🔍 Technical Details"):
                st.code(traceback.format_exc())
    
    # ========================================================================
    # STEP 4: DOWNLOAD REPORTS
    # ========================================================================
    
    st.markdown("---")
    st.header("� Monthly Analysis")
    
    # ========================================================================
    # ENHANCED BAR CHART WITH ANNOTATIONS
    # ========================================================================
    
    st.subheader("📊 Duty Performance Summary")
    st.markdown("*Performance scores for each duty with risk classification*")
    
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as tmp:
            viz.plot_monthly_summary(monthly_analysis, save_path=tmp.name)
            st.image(tmp.name, use_container_width=True)
        
        # Add download buttons
        col1, col2, col3 = st.columns([1, 1, 2])
        
        with col1:
            if os.path.exists(tmp.name):
                with open(tmp.name, 'rb') as f:
                    st.download_button(
                        "📥 Download Chart",
                        data=f,
                        file_name=f"performance_summary_{month}.png",
                        mime="image/png",
                        use_container_width=True
                    )
        
        with col2:
            # Generate chronogram for download
            chrono = FatigueChronogram(theme='light')
            with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as tmp_chrono:
                chrono.plot_monthly_chronogram(
                    monthly_analysis,
                    save_path=tmp_chrono.name,
                    mode='risk',
                    show_annotations=True
                )
                
                if os.path.exists(tmp_chrono.name):
                    with open(tmp_chrono.name, 'rb') as f:
                        st.download_button(
                            "📥 Download Chronogram",
                            data=f,
                            file_name=f"chronogram_{month}.png",
                            mime="image/png",
                            use_container_width=True
                        )
    
    except Exception as e:
        st.error(f"Error generating performance chart: {str(e)}")
        with st.expander("🔍 Technical Details"):
            st.code(traceback.format_exc())
    
    # ========================================================================
    # PATTERN DETECTION TABLE
    # ========================================================================
    
    st.markdown("---")
    st.subheader("🔍 Detected Fatigue Patterns")
    
    # Build pattern summary
    patterns_detected = []
    
    # Check for consecutive WOCL
    wocl_count = sum(1 for dt in monthly_analysis.duty_timelines if dt.wocl_encroachment_hours > 0)
    if wocl_count >= 3:
        patterns_detected.append({
            "Pattern": "Consecutive WOCL Duties",
            "Count": f"{wocl_count} duties",
            "Risk Level": "🔴 High",
            "Recommendation": "Consider circadian re-alignment rest periods"
        })
    
    # Check for quick turnarounds
    quick_turns = 0
    for i in range(len(roster.duties) - 1):
        rest_hours = (roster.duties[i+1].report_time_utc - 
                      roster.duties[i].release_time_utc).total_seconds() / 3600
        if rest_hours < 15:
            quick_turns += 1
    
    if quick_turns > 0:
        patterns_detected.append({
            "Pattern": "Quick Turnarounds",
            "Count": f"{quick_turns} occurrences",
            "Risk Level": "🟠 Moderate",
            "Recommendation": "Monitor sleep quality and cumulative fatigue"
        })
    
    # Check for high cumulative debt
    if monthly_analysis.max_sleep_debt > 8:
        patterns_detected.append({
            "Pattern": "Excessive Sleep Debt",
            "Count": f"{monthly_analysis.max_sleep_debt:.1f}h peak",
            "Risk Level": "🔴 High",
            "Recommendation": "Schedule extended rest period (48h+)"
        })
    
    if patterns_detected:
        df = pd.DataFrame(patterns_detected)
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.success("✅ No concerning fatigue patterns detected in this roster")
    
    # ========================================================================
    # WEEKLY BREAKDOWN
    # ========================================================================
    
    with st.expander("📅 Weekly Breakdown"):
        
        # Group duties by week
        weeks = {}
        for duty_timeline in monthly_analysis.duty_timelines:
            week_num = (duty_timeline.duty_date.day - 1) // 7 + 1
            if week_num not in weeks:
                weeks[week_num] = []
            weeks[week_num].append(duty_timeline)
        
        for week_num, week_duties in sorted(weeks.items()):
            st.markdown(f"**Week {week_num}**")
            
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric("Duties", len(week_duties))
            
            with col2:
                avg_perf = sum(d.average_performance for d in week_duties) / len(week_duties)
                st.metric("Avg Performance", f"{avg_perf:.1f}")
            
            with col3:
                wocl_duties = sum(1 for d in week_duties if d.wocl_encroachment_hours > 0)
                st.metric("WOCL Duties", wocl_duties)
            
            with col4:
                high_risk = sum(
                    1 for d in week_duties 
                    if d.landing_performance and d.landing_performance < 60
                )
                st.metric("High Risk", high_risk)
            
            st.markdown("---")
    
    st.markdown("---")
    
    # Export options
    st.subheader("💾 Export Options")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.write("**📅 Aviation Calendar**")
        st.caption("Multi-day duty calendar with risk levels")
        if st.button("📥 Download Calendar PNG", use_container_width=True):
            try:
                # Generate calendar
                cal = AviationCalendar(theme=selected_theme)
                
                # Save to temporary file
                with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as tmp:
                    cal.plot_monthly_roster(monthly_analysis, save_path=tmp.name, show_performance=True)
                    
                    # Read the file back and display download button
                    with open(tmp.name, 'rb') as f:
                        calendar_data = f.read()
                    
                    st.download_button(
                        label="💾 Save Calendar PNG",
                        data=calendar_data,
                        file_name=f"aviation_calendar_{roster.pilot_id}_{roster.month}.png",
                        mime="image/png",
                        use_container_width=True
                    )
                    st.success("✅ Calendar generated successfully!")
            except Exception as e:
                st.error(f"❌ Error generating calendar: {str(e)}")
                with st.expander("🔍 Technical Details"):
                    st.code(traceback.format_exc())
    
    with col2:
        st.write("**📄 PDF Report**")
        st.caption("Coming soon")
        st.button("📄 Generate PDF Report", use_container_width=True, disabled=True)
    
    with col3:
        st.write("**📊 Excel Export**")
        st.caption("Coming soon")
        st.button("📊 Export to Excel", use_container_width=True, disabled=True)

# ============================================================================
# FOOTER
# ============================================================================

st.markdown("---")
st.markdown("""
<div style='text-align: center; color: gray; font-size: 12px;'>
    <p>EASA Fatigue Analysis Tool v2.1.2</p>
    <p>Based on Borbély Two-Process Model • EASA ORO.FTL Compliant</p>
    <p>Scientific references: Borbély & Achermann (1999), Van Dongen et al. (2003), Dinges et al. (1997)</p>
</div>
""", unsafe_allow_html=True)
