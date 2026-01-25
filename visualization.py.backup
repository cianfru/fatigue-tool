# visualization.py - Fatigue Analysis Visualization Tools

"""
Publication-quality fatigue visualization

Design Principles:
1. Scientific accuracy - exact EASA thresholds, validated scaling
2. Accessibility - colorblind-friendly palettes (Okabe & Ito 2008)
3. Clarity - minimal chartjunk, maximum data-ink ratio (Tufte 2001)
4. Regulatory compliance - annotations reference EASA regulations
"""

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.patches as mpatches
from matplotlib.gridspec import GridSpec
from datetime import datetime, timedelta, time
from typing import Optional, List
import numpy as np
import pytz

from data_models import DutyTimeline, MonthlyAnalysis, FlightPhase
from config import ModelConfig

# ============================================================================
# SCIENTIFIC COLOR SCHEMES (Okabe & Ito 2008 - Colorblind-friendly)
# ============================================================================

RISK_COLORS = {
    'low': '#009E73',       # Green
    'moderate': '#F0E442',  # Yellow
    'high': '#E69F00',      # Orange
    'critical': '#D55E00',  # Red-orange
    'extreme': '#CC0000',   # Dark red
    'unknown': '#999999'    # Gray
}

PHASE_COLORS = {
    FlightPhase.PREFLIGHT: '#E8E8E8',
    FlightPhase.PREFLIGHT: '#F5F5F5',
    FlightPhase.TAXI_OUT: '#D0D0D0',
    FlightPhase.TAKEOFF: '#FF6B6B',
    FlightPhase.CLIMB: '#FFB366',
    FlightPhase.CRUISE: '#98D8C8',
    FlightPhase.DESCENT: '#FFB366',
    FlightPhase.APPROACH: '#FF8C42',
    FlightPhase.LANDING: '#FF6B6B',
    FlightPhase.TAXI_IN: '#D0D0D0'
}

COMPONENT_COLORS = {
    'circadian': '#2E86AB',
    'homeostatic': '#A23B72',
    'inertia': '#F18F01',
    'performance': '#000000'
}

class FatigueVisualizer:
    """
    Publication-quality fatigue visualization
    
    Outputs suitable for:
    - SMS fatigue reports
    - Regulatory submissions
    - Academic publications
    - Pilot briefings
    """
    
    def __init__(self, config: ModelConfig = None):
        self.config = config or ModelConfig.default_easa_config()
        self.easa = self.config.easa_framework
        self.thresholds = self.config.risk_thresholds
        
        # Set matplotlib style
        plt.style.use('seaborn-v0_8-darkgrid')
        plt.rcParams['font.family'] = 'DejaVu Sans'
        plt.rcParams['font.size'] = 10
        plt.rcParams['axes.labelsize'] = 11
        plt.rcParams['axes.titlesize'] = 12
        plt.rcParams['figure.titlesize'] = 14
    
    def plot_duty_timeline(
        self, 
        duty_timeline: DutyTimeline, 
        save_path: Optional[str] = None,
        show_components: bool = True
    ):
        """
        Detailed single-duty timeline with all processes
        
        Scientific Features:
        - Risk thresholds from Dinges et al. (1997)
        - WOCL highlighting per EASA ORO.FTL.105(10)
        - Critical phase annotations
        - Pinch event markers
        """
        if not duty_timeline.timeline:
            print(f"⚠️  No data to plot for duty {duty_timeline.duty_id}")
            return
        
        # Create figure
        fig = plt.figure(figsize=(16, 10))
        gs = GridSpec(3, 1, height_ratios=[3, 1, 1], hspace=0.15)
        
        ax_perf = fig.add_subplot(gs[0])
        ax_phase = fig.add_subplot(gs[1], sharex=ax_perf)
        ax_wocl = fig.add_subplot(gs[2], sharex=ax_perf)
        
        times_local = [p.timestamp_local for p in duty_timeline.timeline]
        performance = [p.raw_performance for p in duty_timeline.timeline]
        
        # ====================================================================
        # UPPER PLOT: Performance & Components
        # ====================================================================
        
        # Risk threshold bands
        for level in ['extreme', 'critical', 'high', 'moderate']:
            low, high = self.thresholds.thresholds[level]
            ax_perf.axhspan(low, high, color=RISK_COLORS[level], alpha=0.15, zorder=0)
            ax_perf.text(
                times_local[-1], (low + high) / 2, 
                f' {level.upper()}',
                va='center', ha='left',
                color=RISK_COLORS[level],
                fontweight='bold',
                fontsize=9
            )
        
        # Performance line
        ax_perf.plot(
            times_local, performance,
            color=COMPONENT_COLORS['performance'],
            linewidth=2.5,
            label='Performance Score',
            zorder=10
        )
        
        # Components (if requested)
        if show_components:
            circadian = [p.circadian_component * 100 for p in duty_timeline.timeline]
            homeostatic = [p.homeostatic_component * 100 for p in duty_timeline.timeline]
            inertia = [p.sleep_inertia_component * 100 for p in duty_timeline.timeline]
            
            ax_perf.plot(
                times_local, circadian,
                color=COMPONENT_COLORS['circadian'],
                linestyle='--',
                linewidth=1.5,
                label='Circadian (C)',
                alpha=0.7
            )
            ax_perf.plot(
                times_local, homeostatic,
                color=COMPONENT_COLORS['homeostatic'],
                linestyle='--',
                linewidth=1.5,
                label='Sleep Pressure (S)',
                alpha=0.7
            )
            
            if max(inertia) > 1:
                ax_perf.fill_between(
                    times_local, 0, inertia,
                    color=COMPONENT_COLORS['inertia'],
                    alpha=0.25,
                    label='Sleep Inertia (W)'
                )
        
        # Pinch events
        if duty_timeline.pinch_events:
            for pinch in duty_timeline.pinch_events:
                ax_perf.scatter(
                    pinch.time_local, pinch.performance,
                    color='red',
                    marker='X',
                    s=200,
                    edgecolors='darkred',
                    linewidths=2,
                    zorder=20,
                    label='Pinch Event' if pinch == duty_timeline.pinch_events[0] else ''
                )
                ax_perf.annotate(
                    f'PINCH\n{pinch.flight_phase.value}',
                    (pinch.time_local, pinch.performance),
                    xytext=(0, 15),
                    textcoords='offset points',
                    ha='center',
                    fontsize=8,
                    color='darkred',
                    bbox=dict(boxstyle='round,pad=0.3', fc='yellow', alpha=0.7),
                    arrowprops=dict(arrowstyle='->', color='red', lw=1.5)
                )
        
        # Landing performance marker
        if duty_timeline.landing_performance:
            landing_points = [
                p for p in duty_timeline.timeline 
                if p.current_flight_phase == FlightPhase.LANDING
            ]
            if landing_points:
                landing_time = landing_points[-1].timestamp_local
                ax_perf.scatter(
                    landing_time, duty_timeline.landing_performance,
                    color='navy',
                    marker='v',
                    s=150,
                    edgecolors='black',
                    linewidths=1.5,
                    zorder=15,
                    label='Landing Performance'
                )
        
        ax_perf.set_ylabel('Performance / Component (%)', fontsize=11)
        ax_perf.set_ylim(-5, 105)
        ax_perf.grid(True, alpha=0.3)
        ax_perf.legend(loc='upper left', framealpha=0.9)
        
        # Title
        risk_level = self.thresholds.classify(duty_timeline.landing_performance or 0)
        title = (
            f"Fatigue Analysis: {duty_timeline.duty_id} "
            f"({duty_timeline.duty_date.strftime('%d-%b-%Y')})\n"
            f"Landing: {duty_timeline.landing_performance:.1f}/100 ({risk_level.upper()})  •  "
            f"Min: {duty_timeline.min_performance:.1f}  •  "
            f"Avg: {duty_timeline.average_performance:.1f}  •  "
            f"Sleep Debt: {duty_timeline.cumulative_sleep_debt:.1f}h"
        )
        ax_perf.set_title(title, fontsize=13, fontweight='bold', pad=15)
        
        # ====================================================================
        # MIDDLE PLOT: Flight Phases
        # ====================================================================
        
        current_phase = None
        phase_start = None
        
        for i, point in enumerate(duty_timeline.timeline):
            if point.current_flight_phase != current_phase:
                if current_phase is not None and phase_start is not None:
                    ax_phase.axvspan(
                        phase_start,
                        times_local[i],
                        color=PHASE_COLORS.get(current_phase, '#CCCCCC'),
                        alpha=0.6
                    )
                    mid_time = phase_start + (times_local[i] - phase_start) / 2
                    ax_phase.text(
                        mid_time, 0.5,
                        current_phase.value.replace('_', ' ').title(),
                        ha='center', va='center',
                        fontsize=9,
                        fontweight='bold' if current_phase in [FlightPhase.TAKEOFF, FlightPhase.LANDING] else 'normal'
                    )
                
                current_phase = point.current_flight_phase
                phase_start = times_local[i]
        
        # Draw final phase
        if current_phase and phase_start:
            ax_phase.axvspan(
                phase_start,
                times_local[-1],
                color=PHASE_COLORS.get(current_phase, '#CCCCCC'),
                alpha=0.6
            )
            mid_time = phase_start + (times_local[-1] - phase_start) / 2
            ax_phase.text(
                mid_time, 0.5,
                current_phase.value.replace('_', ' ').title(),
                ha='center', va='center',
                fontsize=9,
                fontweight='bold' if current_phase in [FlightPhase.TAKEOFF, FlightPhase.LANDING] else 'normal'
            )
        
        ax_phase.set_ylim(0, 1)
        ax_phase.set_yticks([])
        ax_phase.set_ylabel('Flight Phase', fontsize=10)
        ax_phase.grid(False)
        
        # ====================================================================
        # LOWER PLOT: WOCL Indicator
        # ====================================================================
        
        tz = times_local[0].tzinfo
        
        for ts in times_local:
            day_start = ts.replace(hour=0, minute=0, second=0, microsecond=0)
            wocl_start = day_start.replace(hour=self.easa.wocl_start_hour)
            wocl_end = day_start.replace(
                hour=self.easa.wocl_end_hour,
                minute=self.easa.wocl_end_minute,
                second=59
            )
            
            if self.easa.wocl_start_hour > self.easa.wocl_end_hour:
                if ts.hour < self.easa.wocl_end_hour:
                    wocl_start -= timedelta(days=1)
                else:
                    wocl_end += timedelta(days=1)
            
            if wocl_start <= ts <= wocl_end:
                ax_wocl.axvspan(wocl_start, wocl_end, color='purple', alpha=0.3)
                if ts == times_local[0] or (ts.hour == self.easa.wocl_start_hour and ts.minute < 10):
                    ax_wocl.text(
                        wocl_start + (wocl_end - wocl_start) / 2,
                        0.5,
                        f'WOCL\n({duty_timeline.wocl_encroachment_hours:.1f}h exposure)',
                        ha='center', va='center',
                        fontsize=9,
                        color='purple',
                        fontweight='bold'
                    )
        
        ax_wocl.set_ylim(0, 1)
        ax_wocl.set_yticks([])
        ax_wocl.set_ylabel('WOCL', fontsize=10)
        ax_wocl.set_xlabel('Local Time', fontsize=11)
        ax_wocl.grid(False)
        
        # X-axis formatting
        ax_wocl.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
        ax_wocl.xaxis.set_major_locator(mdates.HourLocator(interval=1))
        plt.setp(ax_wocl.xaxis.get_majorticklabels(), rotation=45, ha='right')
        
        ax_perf.tick_params(labelbottom=False)
        ax_phase.tick_params(labelbottom=False)
        
        # Footer
        fig.text(
            0.99, 0.01,
            'EASA ORO.FTL.105 • Borbély Two-Process Model • Fatigue Analysis Tool v2.1.2',
            ha='right', va='bottom',
            fontsize=7,
            color='gray',
            style='italic'
        )
        
        plt.tight_layout()
        
        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
            print(f"✓ Duty timeline saved: {save_path}")
        else:
            plt.show()
        
        plt.close()
    
    def plot_monthly_summary(
        self,
        monthly_analysis: MonthlyAnalysis,
        save_path: Optional[str] = None
    ):
        """Bar chart of minimum performance per duty with risk classification"""
        
        fig, ax = plt.subplots(figsize=(16, 8))
        
        duty_ids = [dt.duty_id for dt in monthly_analysis.duty_timelines]
        min_perfs = [dt.min_performance for dt in monthly_analysis.duty_timelines]
        landing_perfs = [
            dt.landing_performance if dt.landing_performance else dt.min_performance
            for dt in monthly_analysis.duty_timelines
        ]
        
        colors = [
            RISK_COLORS[self.thresholds.classify(perf)]
            for perf in landing_perfs
        ]
        
        bars = ax.bar(duty_ids, min_perfs, color=colors, edgecolor='black', linewidth=0.5)
        
        ax.scatter(
            duty_ids, landing_perfs,
            color='navy',
            marker='v',
            s=100,
            edgecolors='black',
            linewidths=1,
            zorder=10,
            label='Landing Performance'
        )
        
        # Risk threshold lines
        for level in ['high', 'critical', 'extreme']:
            low, _ = self.thresholds.thresholds[level]
            ax.axhline(
                low,
                color=RISK_COLORS[level],
                linestyle='--',
                linewidth=1.5,
                alpha=0.7,
                label=f'{level.capitalize()} Threshold ({low})'
            )
        
        ax.set_ylabel('Performance Score (0-100)', fontsize=12)
        ax.set_xlabel('Duty ID', fontsize=12)
        ax.set_title(
            f'Monthly Roster Analysis: {monthly_analysis.roster.roster_id} '
            f'({monthly_analysis.roster.month})',
            fontsize=14,
            fontweight='bold',
            pad=15
        )
        ax.set_ylim(0, 100)
        ax.grid(axis='y', alpha=0.3)
        ax.legend(loc='lower left', framealpha=0.9)
        
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha='right')
        
        # Summary text box
        summary = (
            f"ROSTER SUMMARY\n"
            f"{'─' * 25}\n"
            f"Total Duties: {monthly_analysis.roster.total_duties}\n"
            f"Total Sectors: {monthly_analysis.roster.total_sectors}\n"
            f"Block Hours: {monthly_analysis.roster.total_block_hours:.1f}h\n"
            f"Duty Hours: {monthly_analysis.roster.total_duty_hours:.1f}h\n"
            f"\n"
            f"RISK SUMMARY\n"
            f"{'─' * 25}\n"
            f"High Risk: {monthly_analysis.high_risk_duties}\n"
            f"Critical Risk: {monthly_analysis.critical_risk_duties}\n"
            f"Pinch Events: {monthly_analysis.total_pinch_events}\n"
            f"\n"
            f"SLEEP METRICS\n"
            f"{'─' * 25}\n"
            f"Avg Sleep/Night: {monthly_analysis.average_sleep_per_night:.1f}h\n"
            f"Max Sleep Debt: {monthly_analysis.max_sleep_debt:.1f}h\n"
            f"\n"
            f"WORST DUTY\n"
            f"{'─' * 25}\n"
            f"ID: {monthly_analysis.lowest_performance_duty}\n"
            f"Perf: {monthly_analysis.lowest_performance_value:.1f}/100"
        )
        
        ax.text(
            1.02, 0.98,
            summary,
            transform=ax.transAxes,
            fontsize=9,
            verticalalignment='top',
            fontfamily='monospace',
            bbox=dict(
                boxstyle='round,pad=0.8',
                facecolor='wheat',
                alpha=0.8,
                edgecolor='black'
            )
        )
        
        plt.tight_layout(rect=[0, 0, 0.85, 1])
        
        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
            print(f"✓ Monthly summary saved: {save_path}")
        else:
            plt.show()
        
        plt.close()
    
    def plot_component_breakdown(
        self,
        duty_timeline: DutyTimeline,
        save_path: Optional[str] = None
    ):
        """Stacked area plot showing C/S/W contribution to fatigue"""
        
        if not duty_timeline.timeline:
            return
        
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10), sharex=True)
        
        times = [p.timestamp_local for p in duty_timeline.timeline]
        
        # Convert to "impairment"
        c_impairment = [(1 - p.circadian_component) * 100 for p in duty_timeline.timeline]
        s_impairment = [p.homeostatic_component * 100 for p in duty_timeline.timeline]
        w_impairment = [p.sleep_inertia_component * 100 for p in duty_timeline.timeline]
        
        # Stacked components
        ax1.fill_between(
            times, 0, c_impairment,
            color=COMPONENT_COLORS['circadian'],
            alpha=0.7,
            label='Circadian Impairment (1-C)'
        )
        ax1.fill_between(
            times, c_impairment, 
            [c + s for c, s in zip(c_impairment, s_impairment)],
            color=COMPONENT_COLORS['homeostatic'],
            alpha=0.7,
            label='Homeostatic (S)'
        )
        ax1.fill_between(
            times, 
            [c + s for c, s in zip(c_impairment, s_impairment)],
            [c + s + w for c, s, w in zip(c_impairment, s_impairment, w_impairment)],
            color=COMPONENT_COLORS['inertia'],
            alpha=0.7,
            label='Sleep Inertia (W)'
        )
        
        ax1.set_ylabel('Impairment (%)', fontsize=11)
        ax1.set_title(
            f'Fatigue Component Breakdown: {duty_timeline.duty_id}\n'
            f'(Shows what is causing fatigue at each moment)',
            fontsize=12,
            fontweight='bold'
        )
        ax1.legend(loc='upper left')
        ax1.grid(True, alpha=0.3)
        ax1.set_ylim(0, 200)
        
        # Individual components
        ax2.plot(times, c_impairment, color=COMPONENT_COLORS['circadian'], 
                 linewidth=2, label='Circadian (1-C)', linestyle='--')
        ax2.plot(times, s_impairment, color=COMPONENT_COLORS['homeostatic'], 
                 linewidth=2, label='Sleep Pressure (S)', linestyle='--')
        ax2.plot(times, w_impairment, color=COMPONENT_COLORS['inertia'], 
                 linewidth=2, label='Sleep Inertia (W)', linestyle='--')
        
        ax2.set_ylabel('Component Value (%)', fontsize=11)
        ax2.set_xlabel('Local Time', fontsize=11)
        ax2.legend(loc='upper left')
        ax2.grid(True, alpha=0.3)
        ax2.set_ylim(0, 100)
        
        ax2.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
        ax2.xaxis.set_major_locator(mdates.HourLocator(interval=1))
        plt.setp(ax2.xaxis.get_majorticklabels(), rotation=45, ha='right')
        
        plt.tight_layout()
        
        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
            print(f"✓ Component breakdown saved: {save_path}")
        else:
            plt.show()
        
        plt.close()
