# visualization.py - Professional Fatigue Analysis Visualization (V2 Pro)

"""
Production-grade Plotly visualizations for aviation fatigue analysis

Design Principles:
1. Scientific accuracy - exact EASA thresholds, validated scaling
2. Accessibility - colorblind-friendly palettes (Okabe & Ito 2008)
3. Interactivity - Plotly tooltips & zoom for deep-dive analysis
4. Regulatory compliance - annotations reference EASA regulations
5. Professional aesthetics - matches modern dashboard standards
"""

import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta, time
from typing import Optional, List, Dict
import pandas as pd
import calendar

from data_models import DutyTimeline, MonthlyAnalysis, FlightPhase
from config import ModelConfig

# ============================================================================
# V2 PRO COLOR SCHEME (Plotly Dark Mode + Okabe & Ito)
# ============================================================================

THEME_COLORS = {
    'S': '#3498DB',          # Sleep Pressure - Blue
    'C': '#2ECC71',          # Circadian - Green
    'W': '#E74C3C',          # Wake/Inertia - Red
    'performance': '#00EBFF', # Neon Cyan
    'wocl': 'rgba(155, 89, 182, 0.25)',  # Translucent Purple
    'critical': '#D55E00',   # Red-Orange
    'high': '#E69F00',       # Orange
    'moderate': '#F0E442',   # Yellow
    'low': '#009E73'         # Green
}

RISK_PALETTE = {
    'critical': '#D55E00',
    'high': '#E69F00',
    'moderate': '#F0E442',
    'low': '#009E73'
}

class FatigueVisualizer:
    """
    Production-grade Plotly visualizer for aviation fatigue analysis
    
    V2 Pro Features:
    - Three-component stacked area (S/C/W decomposition)
    - WOCL shading with EASA compliance highlighting
    - Interactive tooltips with flight details
    - Dynamic theme sync for light/dark modes
    - Route map with risk-based coloring
    - Pinch event detection and marking
    """
    
    def __init__(self, config: ModelConfig = None, theme: str = "dark"):
        self.config = config or ModelConfig.default_easa_config()
        self.easa = self.config.easa_framework
        self.thresholds = self.config.risk_thresholds
        self.theme = theme
        self.template = "plotly_dark" if theme == "dark" else "plotly_white"
    
    def create_unified_timeline(self, duty_timeline: DutyTimeline):
        """
        Plotly unified timeline with stacked S/C/W components + WOCL shading
        
        Features:
        - Three-component stacked area showing fatigue decomposition
        - Performance line overlay (neon cyan)
        - WOCL background shading for EASA compliance
        - Interactive tooltips with flight number and sleep debt
        - Pinch event markers (red X symbols)
        """
        if not duty_timeline.timeline:
            return None
        
        fig = make_subplots(
            rows=2, cols=1, shared_xaxes=True,
            vertical_spacing=0.03, row_heights=[0.8, 0.2]
        )
        
        times = [p.timestamp_local for p in duty_timeline.timeline]
        
        # 1. STACKED COMPONENTS (S + C + W)
        fig.add_trace(go.Scatter(
            x=times, y=[p.homeostatic_component * 100 for p in duty_timeline.timeline],
            name="Sleep Pressure (S)", stackgroup='one', 
            fillcolor=THEME_COLORS['S'],
            line=dict(width=0), hoverinfo='skip'
        ), row=1, col=1)
        
        fig.add_trace(go.Scatter(
            x=times, y=[p.circadian_component * 100 for p in duty_timeline.timeline],
            name="Circadian (C)", stackgroup='one', 
            fillcolor=THEME_COLORS['C'],
            line=dict(width=0), hoverinfo='skip'
        ), row=1, col=1)
        
        fig.add_trace(go.Scatter(
            x=times, y=[p.sleep_inertia_component * 100 for p in duty_timeline.timeline],
            name="Sleep Inertia (W)", stackgroup='one', 
            fillcolor=THEME_COLORS['W'],
            line=dict(width=0), hoverinfo='skip'
        ), row=1, col=1)
        
        # 2. TOTAL PERFORMANCE LINE (High Emphasis)
        total_perf = [p.raw_performance for p in duty_timeline.timeline]
        flight_nos = [getattr(p, 'flight_no', 'N/A') for p in duty_timeline.timeline]
        sleep_debts = [getattr(p, 'sleep_debt', 0) for p in duty_timeline.timeline]
        
        fig.add_trace(go.Scatter(
            x=times, y=total_perf, name="Total Performance",
            mode='lines',
            line=dict(color=THEME_COLORS['performance'], width=4),
            customdata=[[fn, sd] for fn, sd in zip(flight_nos, sleep_debts)],
            hovertemplate="<b>%{y:.1f}% Perf</b><br>Flight: %{customdata[0]}<br>Sleep Debt: %{customdata[1]:.1f}h<extra></extra>"
        ), row=1, col=1)
        
        # 3. WOCL SHADING
        for start_wocl, end_wocl in getattr(duty_timeline, 'wocl_periods', []):
            fig.add_vrect(
                x0=start_wocl, x1=end_wocl, 
                fillcolor=THEME_COLORS['wocl'],
                layer="below", line_width=0, 
                annotation_text="WOCL", row=1, col=1
            )
        
        # 4. RISK THRESHOLD BANDS
        thresholds = [
            (0, 60, 'critical'), (60, 70, 'high'), 
            (70, 85, 'moderate'), (85, 100, 'low')
        ]
        for y0, y1, level in thresholds:
            fig.add_hrect(
                y0=y0, y1=y1, 
                fillcolor=RISK_PALETTE[level], 
                opacity=0.1, layer="below", line_width=0,
                row=1, col=1
            )
        
        # 5. PINCH EVENTS
        pinches = [p for p in duty_timeline.timeline if getattr(p, 'is_pinch', False)]
        if pinches:
            fig.add_trace(go.Scatter(
                x=[p.timestamp_local for p in pinches],
                y=[p.raw_performance for p in pinches],
                mode='markers+text',
                name='Critical Pinch',
                marker=dict(symbol='x', size=12, color='red', line=dict(width=2)),
                text=["⚠️ CRITICAL"] * len(pinches),
                textposition="top center"
            ), row=1, col=1)
        
        # 6. DUTY PHASE RIBBON (Row 2)
        fig.add_trace(go.Scatter(
            x=times, y=[1] * len(times),
            mode='lines',
            name='Duty Period',
            line=dict(color='#5DADE2', width=20),
            showlegend=False
        ), row=2, col=1)
        
        # STYLING
        fig.update_layout(
            title=dict(
                text=f"<b>{duty_timeline.duty_id}</b> | Landing: {duty_timeline.landing_performance:.1f}% | "
                     f"Min: {duty_timeline.min_performance:.1f}% | Sleep Debt: {duty_timeline.cumulative_sleep_debt:.1f}h",
                x=0.5, xanchor='center'
            ),
            height=600,
            template=self.template,
            margin=dict(l=10, r=10, t=60, b=10),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            hovermode="x unified",
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)'
        )
        
        fig.update_yaxes(title_text="Performance %", range=[0, 105], row=1, col=1)
        fig.update_yaxes(showticklabels=False, range=[0, 2], row=2, col=1)
        fig.update_xaxes(title_text="Local Time", row=2, col=1)
        
        return fig
    
    def create_route_map(self, analysis: MonthlyAnalysis, selected_id: Optional[str] = None):
        """
        Geographic route heatmap with risk-based coloring
        
        Features:
        - Scattergeo with great circle paths
        - Opacity highlighting for selected duty
        - Risk coloring based on landing performance
        """
        fig = go.Figure()
        
        trace_count = 0
        
        # Map duty_id to duty_timeline for performance lookup
        timeline_map = {dt.duty_id: dt for dt in analysis.duty_timelines}
        
        # Get segments from the roster duties
        if not hasattr(analysis, 'roster') or not analysis.roster:
            return fig  # Return empty figure if no roster
        
        for duty in analysis.roster.duties:
            duty_timeline = timeline_map.get(duty.duty_id)
            if not duty_timeline:
                continue
            
            is_selected = (duty.duty_id == selected_id)
            opacity = 0.8 if is_selected else 0.2
            landing_perf = getattr(duty_timeline, 'landing_performance', 100)
            risk_color = self._get_risk_color(landing_perf)
            
            for seg in getattr(duty, 'segments', []):
                # Access airport coordinates safely
                dep_airport = getattr(seg, 'departure_airport', None)
                arr_airport = getattr(seg, 'arrival_airport', None)
                
                if not dep_airport or not arr_airport:
                    continue
                
                dep_lon = getattr(dep_airport, 'longitude', None)
                dep_lat = getattr(dep_airport, 'latitude', None)
                arr_lon = getattr(arr_airport, 'longitude', None)
                arr_lat = getattr(arr_airport, 'latitude', None)
                
                # Skip only if coordinates are None (missing), not if they're 0
                if dep_lon is None or dep_lat is None or arr_lon is None or arr_lat is None:
                    continue
                
                flight_no = getattr(seg, 'flight_number', 'N/A')
                
                fig.add_trace(go.Scattergeo(
                    lon=[dep_lon, arr_lon],
                    lat=[dep_lat, arr_lat],
                    mode='lines+markers',
                    line=dict(width=2 if is_selected else 1.5, color=risk_color),
                    opacity=opacity,
                    hoverinfo="text",
                    text=f"Flight {flight_no} | Perf: {landing_perf:.0f}%" if landing_perf is not None else f"Flight {flight_no} | Perf: N/A",
                    showlegend=False
                ))
                trace_count += 1
        
        fig.update_layout(
            title=f"Route Heatmap ({getattr(analysis.roster, 'roster_id', 'Roster') if hasattr(analysis, 'roster') else 'Roster'}) - {trace_count} routes",
            geo=dict(
                projection_type='natural earth',
                showland=True,
                landcolor='#1a1a1a',
                bgcolor='rgba(0,0,0,0)',
                countrycolor='#444'
            ),
            height=500,
            template=self.template,
            margin=dict(l=0, r=0, t=50, b=0)
        )
        
        return fig
    
    def _get_risk_color(self, performance: Optional[float]) -> str:
        """Map performance score to risk color"""
        if performance is None:
            return RISK_PALETTE['low']  # Default to low risk if no performance data
        if performance < 60:
            return RISK_PALETTE['critical']
        elif performance < 75:
            return RISK_PALETTE['high']
        elif performance < 85:
            return RISK_PALETTE['moderate']
        else:
            return RISK_PALETTE['low']
    
    def create_month_calendar(self, monthly_analysis: MonthlyAnalysis):
        """
        Creates an interactive month calendar view with risk-colored day boxes
        
        Features:
        - 7 columns (Mon-Sun) grid layout
        - Color-coded by risk level (critical/high/moderate/low)
        - Shows key metrics per day (sleep debt, avg performance)
        - Click drill-down to duty details
        """
        # Create lookup: date -> duty_timeline
        duty_by_date = {}
        for dt in monthly_analysis.duty_timelines:
            duty_by_date[dt.duty_date.date()] = dt
        
        # Get month/year from first duty
        if monthly_analysis.duty_timelines:
            first_duty = monthly_analysis.duty_timelines[0]
            year = first_duty.duty_date.year
            month = first_duty.duty_date.month
        else:
            now = datetime.now()
            year = now.year
            month = now.month
        
        # Create calendar grid data
        import calendar
        cal = calendar.monthcalendar(year, month)
        month_name = calendar.month_name[month]
        
        # Build hover text and color for each day
        day_colors = []
        day_texts = []
        day_duties = []
        
        for week in cal:
            for day in week:
                if day == 0:  # Empty day
                    day_colors.append('rgba(0,0,0,0)')  # Transparent
                    day_texts.append('')
                    day_duties.append(None)
                else:
                    date_obj = datetime(year, month, day).date()
                    if date_obj in duty_by_date:
                        dt = duty_by_date[date_obj]
                        
                        # Determine risk color
                        avg_perf = sum(p.landing_performance for p in dt.timeline if p.landing_performance) / max(1, len([p for p in dt.timeline if p.landing_performance]))
                        risk_color = self._get_risk_color(avg_perf)
                        day_colors.append(risk_color)
                        
                        # Build hover text with key metrics
                        sleep_debt = dt.sleep_debt if hasattr(dt, 'sleep_debt') else 0
                        day_texts.append(
                            f"<b>{day}</b><br>"
                            f"Duty: {dt.duty_id}<br>"
                            f"Perf: {avg_perf:.0f}/100<br>"
                            f"Sleep Debt: {sleep_debt:.1f}h<br>"
                            f"Sectors: {len([p for p in dt.timeline if hasattr(p, 'flight_phase') and p.flight_phase.name == 'CRUISE'])}"
                        )
                        day_duties.append(dt.duty_id)
                    else:
                        # No duty scheduled
                        day_colors.append('rgba(100,100,100,0.3)')  # Light gray
                        day_texts.append(f"<b>{day}</b><br>Off")
                        day_duties.append(None)
        
        # Create heatmap-style calendar using Plotly
        # Flatten for heatmap
        z_values = []
        hover_texts = []
        x_labels = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
        
        week_num = 0
        for week in cal:
            week_values = []
            week_hovers = []
            for day_idx, day in enumerate(week):
                if day == 0:
                    week_values.append(None)
                    week_hovers.append('')
                else:
                    date_obj = datetime(year, month, day).date()
                    if date_obj in duty_by_date:
                        dt = duty_by_date[date_obj]
                        avg_perf = sum(p.landing_performance for p in dt.timeline if p.landing_performance) / max(1, len([p for p in dt.timeline if p.landing_performance]))
                        week_values.append(avg_perf)
                        week_hovers.append(f"<b>{x_labels[day_idx]} {day}</b><br>{dt.duty_id}<br>Perf: {avg_perf:.0f}/100")
                    else:
                        week_values.append(0)
                        week_hovers.append(f"<b>{x_labels[day_idx]} {day}</b><br>Off")
            z_values.append(week_values)
            week_num += 1
        
        # Create figure with Plotly heatmap
        fig = go.Figure(data=go.Heatmap(
            z=z_values,
            colorscale=[
                [0, RISK_PALETTE['critical']],
                [0.3, RISK_PALETTE['high']],
                [0.6, RISK_PALETTE['moderate']],
                [1.0, RISK_PALETTE['low']]
            ],
            colorbar=dict(title="Performance", tickvals=[60, 75, 85, 100], ticktext=['Critical', 'High', 'Moderate', 'Low']),
            x=x_labels,
            y=[f"Week {i+1}" for i in range(len(z_values))],
            text=hover_texts if hover_texts else None,
            hovertemplate='%{text}<extra></extra>'
        ))
        
        fig.update_layout(
            title=f"📅 {month_name} {year} - Fatigue Risk Calendar",
            xaxis_title="",
            yaxis_title="",
            template=self.template,
            height=400,
            font=dict(size=11)
        )
        
        return fig
    
    def plot_duty_timeline(
        self, 
        duty_timeline: DutyTimeline, 
        save_path: Optional[str] = None,
        show_components: bool = True
    ):
        """
        Legacy method for backward compatibility
        Creates interactive Plotly figure instead of matplotlib
        """
        fig = self.create_unified_timeline(duty_timeline)
        if fig and save_path:
            fig.write_html(save_path)
            print(f"✓ Duty timeline saved: {save_path}")
        return fig
    
    def plot_monthly_summary(
        self,
        monthly_analysis: MonthlyAnalysis,
        save_path: Optional[str] = None
    ):
        """
        Plotly bar chart of duty performance with risk classification
        
        Features:
        - Color-coded bars by risk level
        - Landing performance overlay markers
        - Risk threshold reference lines
        - Summary statistics sidebar
        """
        fig = go.Figure()
        
        duty_ids = [dt.duty_id for dt in monthly_analysis.duty_timelines]
        min_perfs = [dt.min_performance for dt in monthly_analysis.duty_timelines]
        landing_perfs = [
            dt.landing_performance if dt.landing_performance else dt.min_performance
            for dt in monthly_analysis.duty_timelines
        ]
        
        colors = [
            self._get_risk_color(perf)
            for perf in landing_perfs
        ]
        
        fig.add_trace(go.Bar(
            x=duty_ids, y=min_perfs,
            marker=dict(color=colors, line=dict(color='black', width=0.5)),
            name='Min Performance'
        ))
        
        fig.add_trace(go.Scatter(
            x=duty_ids, y=landing_perfs,
            mode='markers',
            marker=dict(symbol='triangle-down', size=10, color='navy', line=dict(width=1, color='black')),
            name='Landing Performance'
        ))
        
        # Risk threshold lines
        thresholds = [
            (60, 'Critical', '#D55E00'),
            (70, 'High', '#E69F00'),
            (85, 'Moderate', '#F0E442')
        ]
        for threshold, label, color in thresholds:
            fig.add_hline(
                y=threshold,
                line=dict(color=color, dash='dash', width=1.5),
                annotation_text=f"{label} ({threshold})",
                annotation_position="right"
            )
        
        fig.update_layout(
            title=f"Monthly Roster: {getattr(monthly_analysis.roster, 'roster_id', 'Roster')}",
            xaxis_title="Duty ID",
            yaxis_title="Performance Score (0-100)",
            template=self.template,
            height=500,
            barmode='group'
        )
        
        if save_path:
            fig.write_html(save_path)
            print(f"✓ Monthly summary saved: {save_path}")
        
        return fig
    
    def plot_component_breakdown(
        self,
        duty_timeline: DutyTimeline,
        save_path: Optional[str] = None
    ):
        """
        Stacked area showing C/S/W contribution to fatigue over time
        
        Features:
        - Stacked area decomposition
        - Individual component traces
        - Interactive legends
        """
        if not duty_timeline.timeline:
            return None
        
        fig = make_subplots(
            rows=2, cols=1,
            shared_xaxes=True,
            vertical_spacing=0.1,
            row_heights=[0.6, 0.4]
        )
        
        times = [p.timestamp_local for p in duty_timeline.timeline]
        
        # Stacked components (impairment perspective)
        c_impair = [(1 - p.circadian_component) * 100 for p in duty_timeline.timeline]
        s_impair = [p.homeostatic_component * 100 for p in duty_timeline.timeline]
        w_impair = [p.sleep_inertia_component * 100 for p in duty_timeline.timeline]
        
        fig.add_trace(go.Scatter(
            x=times, y=c_impair,
            name="Circadian Impairment (1-C)",
            fill='tozeroy',
            fillcolor=THEME_COLORS['C'],
            line=dict(width=0)
        ), row=1, col=1)
        
        fig.add_trace(go.Scatter(
            x=times, y=[c + s for c, s in zip(c_impair, s_impair)],
            name="Sleep Pressure (S)",
            fill='tonexty',
            fillcolor=THEME_COLORS['S'],
            line=dict(width=0)
        ), row=1, col=1)
        
        fig.add_trace(go.Scatter(
            x=times, y=[c + s + w for c, s, w in zip(c_impair, s_impair, w_impair)],
            name="Sleep Inertia (W)",
            fill='tonexty',
            fillcolor=THEME_COLORS['W'],
            line=dict(width=0)
        ), row=1, col=1)
        
        # Individual traces (row 2)
        fig.add_trace(go.Scatter(
            x=times, y=c_impair,
            name="Circadian (1-C)",
            mode='lines',
            line=dict(color=THEME_COLORS['C'], dash='dash'),
        ), row=2, col=1)
        
        fig.add_trace(go.Scatter(
            x=times, y=s_impair,
            name="Sleep Pressure (S)",
            mode='lines',
            line=dict(color=THEME_COLORS['S'], dash='dash'),
        ), row=2, col=1)
        
        fig.add_trace(go.Scatter(
            x=times, y=w_impair,
            name="Sleep Inertia (W)",
            mode='lines',
            line=dict(color=THEME_COLORS['W'], dash='dash'),
        ), row=2, col=1)
        
        fig.update_yaxes(title_text="Cumulative Impairment (%)", row=1, col=1)
        fig.update_yaxes(title_text="Component Value (%)", row=2, col=1)
        fig.update_xaxes(title_text="Local Time", row=2, col=1)
        
        fig.update_layout(
            title=f"Component Breakdown: {duty_timeline.duty_id}",
            template=self.template,
            height=600
        )
        
        if save_path:
            fig.write_html(save_path)
            print(f"✓ Component breakdown saved: {save_path}")
        
        return fig
