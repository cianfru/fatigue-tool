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
from pathlib import Path
import tempfile
from datetime import datetime
import traceback
from streamlit_folium import st_folium

# Add current directory to path
sys.path.append(str(Path(__file__).parent))

# Import modules
from core_model import BorbelyFatigueModel
from roster_parser import PDFRosterParser, CSVRosterParser, AirportDatabase
from easa_utils import FatigueRiskScorer
from visualization import FatigueVisualizer
from config import ModelConfig

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
                
                if uploaded_file.name.endswith('.pdf'):
                    parser = PDFRosterParser(
                        home_base=home_base_code,
                        home_timezone=home_timezone
                    )
                    roster = parser.parse_pdf(tmp_path, pilot_id, month)
                else:  # CSV
                    parser = CSVRosterParser(
                        home_base=home_base_code,
                        home_timezone=home_timezone
                    )
                    roster = parser.parse_csv(tmp_path, pilot_id, month)
            
            st.success(f"✅ Parsed {roster.total_duties} duties, {roster.total_sectors} sectors")
            
            # Store roster
            st.session_state.roster = roster
            
            # Run fatigue analysis
            with st.spinner("🧠 Running biomathematical analysis..."):
                model = BorbelyFatigueModel(config)
                monthly_analysis = model.simulate_roster(roster)
            
            st.success("✅ Analysis complete!")
            
            # Store results
            st.session_state.monthly_analysis = monthly_analysis
            st.session_state.analysis_complete = True
            
            # Force rerun to show results
            st.rerun()
            
        except Exception as e:
            st.error(f"❌ Error during analysis: {str(e)}")
            with st.expander("🔍 Technical Details"):
                st.code(traceback.format_exc())
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
    st.subheader("📅 Monthly Fatigue Calendar")
    
    month_calendar_fig = viz.create_month_calendar(monthly_analysis)
    st.plotly_chart(month_calendar_fig, use_container_width=True)
    
    st.markdown("**Color Legend:** 🔴 Critical (<60) | 🟠 High (60-74) | 🟡 Moderate (75-84) | 🟢 Low (85+)")
    
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
    st.header("📥 Step 4: Download Reports")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        try:
            fig = viz.plot_monthly_summary(monthly_analysis)
            if fig:
                st.plotly_chart(fig, use_container_width=True)
        except Exception as e:
            st.error(f"Error generating chart: {str(e)}")
    
    with col2:
        st.button("📄 Generate PDF Report", use_container_width=True, disabled=True)
        st.caption("PDF generation coming soon")
    
    with col3:
        st.button("📊 Export to Excel", use_container_width=True, disabled=True)
        st.caption("Excel export coming soon")

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
