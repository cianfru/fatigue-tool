# visualization_v2.py - Modern, Clear Fatigue Visualization
# =========================================================

"""
FIXES from V1:
1. Performance shown as LINE (not stacked area)
2. Risk zones clearly colored
3. Flight phases shown separately
4. Dark/Light theme support
5. Calendar month view
"""

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.patches as mpatches
from matplotlib.gridspec import GridSpec
import numpy as np
from datetime import datetime, timedelta
from typing import Optional, List
import pytz

# Import your data models
from data_models import DutyTimeline, MonthlyAnalysis, FlightPhase, PerformancePoint

# ============================================================================
# THEME SYSTEM
# ============================================================================

class Theme:
    """Color themes for visualization"""
    
    @staticmethod
    def dark():
        return {
            'background': '#1e1e1e',
            'text': '#ffffff',
            'grid': '#444444',
            'performance_line': '#00ff88',
            'risk_low': '#2d5a3d',
            'risk_moderate': '#5a4d2d',
            'risk_high': '#5a3d2d',
            'risk_critical': '#5a2d2d',
            'wocl': '#6a2d7a',
            'takeoff': '#ff4444',
            'landing': '#ff4444',
            'cruise': '#4488ff',
        }
    
    @staticmethod
    def light():
        return {
            'background': '#ffffff',
            'text': '#000000',
            'grid': '#cccccc',
            'performance_line': '#00aa44',
            'risk_low': '#90ee90',
            'risk_moderate': '#ffeb3b',
            'risk_high': '#ff9800',
            'risk_critical': '#f44336',
            'wocl': '#9c27b0',
            'takeoff': '#ff1744',
            'landing': '#ff1744',
            'cruise': '#2196f3',
        }


def apply_theme(fig, ax_list, theme_dict):
    """Apply theme colors to figure and axes"""
    fig.patch.set_facecolor(theme_dict['background'])
    
    for ax in ax_list:
        ax.set_facecolor(theme_dict['background'])
        ax.spines['bottom'].set_color(theme_dict['text'])
        ax.spines['left'].set_color(theme_dict['text'])
        ax.spines['top'].set_color(theme_dict['text'])
        ax.spines['right'].set_color(theme_dict['text'])
        ax.tick_params(colors=theme_dict['text'])
        ax.xaxis.label.set_color(theme_dict['text'])
        ax.yaxis.label.set_color(theme_dict['text'])
        ax.title.set_color(theme_dict['text'])
        ax.grid(color=theme_dict['grid'], alpha=0.3)


# ============================================================================
# IMPROVED DUTY TIMELINE
# ============================================================================

def plot_duty_timeline_v2(
    duty_timeline: DutyTimeline,
    save_path: Optional[str] = None,
    theme: str = 'light'
):
    """
    Modern, clear duty timeline
    
    Shows:
    1. Performance as clear LINE (not area)
    2. Risk zones as horizontal bands
    3. Flight phases as colored background
    4. WOCL as shaded region
    """
    
    if not duty_timeline.timeline:
        print(f"No timeline data for {duty_timeline.duty_id}")
        return
    
    # Get theme
    colors = Theme.dark() if theme == 'dark' else Theme.light()
    
    # Create figure
    fig, (ax_main, ax_phase) = plt.subplots(
        2, 1,
        figsize=(16, 8),
        height_ratios=[4, 1],
        sharex=True
    )
    
    # Extract data
    times = [p.timestamp_local for p in duty_timeline.timeline]
    performance = [p.raw_performance for p in duty_timeline.timeline]
    
    # ========================================================================
    # MAIN PLOT: Performance Line with Risk Zones
    # ========================================================================
    
    # Risk zone backgrounds
    ax_main.axhspan(0, 45, color=colors['risk_critical'], alpha=0.15, label='Critical Risk')
    ax_main.axhspan(45, 55, color=colors['risk_high'], alpha=0.15, label='High Risk')
    ax_main.axhspan(55, 70, color=colors['risk_moderate'], alpha=0.15, label='Moderate Risk')
    ax_main.axhspan(70, 100, color=colors['risk_low'], alpha=0.15, label='Low Risk')
    
    # Risk threshold lines
    for threshold, label in [(45, 'CRITICAL'), (55, 'HIGH'), (70, 'MODERATE')]:
        ax_main.axhline(
            threshold,
            color=colors['text'],
            linestyle='--',
            linewidth=1.5,
            alpha=0.5
        )
        ax_main.text(
            times[-1], threshold + 2,
            f' {label}',
            color=colors['text'],
            fontsize=9,
            fontweight='bold',
            va='bottom'
        )
    
    # Performance line (THICK and CLEAR)
    ax_main.plot(
        times, performance,
        color=colors['performance_line'],
        linewidth=4,
        label='Performance',
        zorder=10
    )
    
    # Landing marker
    if duty_timeline.landing_performance:
        landing_times = [
            p.timestamp_local for p in duty_timeline.timeline
            if p.current_flight_phase == FlightPhase.LANDING
        ]
        if landing_times:
            ax_main.scatter(
                landing_times[-1],
                duty_timeline.landing_performance,
                color='#ff0000',
                s=300,
                marker='v',
                edgecolors=colors['text'],
                linewidths=2,
                zorder=15,
                label=f'Landing: {duty_timeline.landing_performance:.1f}/100'
            )
    
    # Minimum performance marker
    if duty_timeline.min_performance_time:
        ax_main.scatter(
            duty_timeline.min_performance_time,
            duty_timeline.min_performance,
            color='#ffaa00',
            s=200,
            marker='X',
            edgecolors=colors['text'],
            linewidths=2,
            zorder=15,
            label=f'Minimum: {duty_timeline.min_performance:.1f}/100'
        )
    
    # Labels
    ax_main.set_ylabel('Performance Score (0-100)', fontsize=12, fontweight='bold')
    ax_main.set_ylim(-5, 105)
    ax_main.legend(loc='lower left', fontsize=10, framealpha=0.9)
    ax_main.set_title(
        f'{duty_timeline.duty_id} - {duty_timeline.duty_date.strftime("%d %B %Y")}\n'
        f'Landing: {duty_timeline.landing_performance:.1f} | '
        f'Min: {duty_timeline.min_performance:.1f} | '
        f'Avg: {duty_timeline.average_performance:.1f} | '
        f'Sleep Debt: {duty_timeline.cumulative_sleep_debt:.1f}h',
        fontsize=14,
        fontweight='bold',
        pad=15
    )
    
    # ========================================================================
    # PHASE PLOT: Flight Phases + WOCL
    # ========================================================================
    
    # Flight phases as colored blocks
    current_phase = None
    phase_start = None
    
    for i, point in enumerate(duty_timeline.timeline):
        if point.current_flight_phase != current_phase:
            # Draw previous phase
            if current_phase and phase_start:
                # Color based on criticality
                if current_phase in [FlightPhase.TAKEOFF, FlightPhase.LANDING]:
                    color = colors['takeoff']
                    alpha = 0.7
                elif current_phase == FlightPhase.CRUISE:
                    color = colors['cruise']
                    alpha = 0.4
                else:
                    color = colors['grid']
                    alpha = 0.3
                
                ax_phase.axvspan(
                    phase_start, times[i],
                    color=color,
                    alpha=alpha
                )
                
                # Label
                mid_time = phase_start + (times[i] - phase_start) / 2
                ax_phase.text(
                    mid_time, 0.5,
                    current_phase.value.replace('_', ' ').upper(),
                    ha='center', va='center',
                    fontsize=10,
                    fontweight='bold' if current_phase in [FlightPhase.TAKEOFF, FlightPhase.LANDING] else 'normal',
                    color=colors['text']
                )
            
            current_phase = point.current_flight_phase
            phase_start = times[i]
    
    # Draw final phase
    if current_phase and phase_start:
        if current_phase in [FlightPhase.TAKEOFF, FlightPhase.LANDING]:
            color = colors['takeoff']
            alpha = 0.7
        elif current_phase == FlightPhase.CRUISE:
            color = colors['cruise']
            alpha = 0.4
        else:
            color = colors['grid']
            alpha = 0.3
        
        ax_phase.axvspan(phase_start, times[-1], color=color, alpha=alpha)
        mid_time = phase_start + (times[-1] - phase_start) / 2
        ax_phase.text(
            mid_time, 0.5,
            current_phase.value.replace('_', ' ').upper(),
            ha='center', va='center',
            fontsize=10,
            fontweight='bold' if current_phase in [FlightPhase.TAKEOFF, FlightPhase.LANDING] else 'normal',
            color=colors['text']
        )
    
    # WOCL overlay
    if duty_timeline.wocl_encroachment_hours > 0:
        # Find WOCL periods
        for ts in times:
            hour = ts.hour
            if 2 <= hour < 6:  # WOCL: 02:00-05:59
                day_start = ts.replace(hour=2, minute=0, second=0, microsecond=0)
                day_end = ts.replace(hour=5, minute=59, second=59, microsecond=0)
                
                ax_phase.axvspan(
                    day_start, day_end,
                    color=colors['wocl'],
                    alpha=0.5,
                    zorder=5
                )
                
                # Label once
                if ts == times[0] or (ts.hour == 2 and ts.minute < 10):
                    ax_phase.text(
                        day_start + (day_end - day_start) / 2,
                        0.8,
                        f'WOCL\n{duty_timeline.wocl_encroachment_hours:.1f}h',
                        ha='center', va='center',
                        fontsize=9,
                        fontweight='bold',
                        color='white',
                        bbox=dict(boxstyle='round', facecolor=colors['wocl'], alpha=0.8)
                    )
                break
    
    ax_phase.set_ylim(0, 1)
    ax_phase.set_yticks([])
    ax_phase.set_xlabel('Local Time', fontsize=12, fontweight='bold')
    
    # X-axis formatting
    ax_phase.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
    ax_phase.xaxis.set_major_locator(mdates.HourLocator(interval=1))
    plt.setp(ax_phase.xaxis.get_majorticklabels(), rotation=45, ha='right')
    
    # Apply theme
    apply_theme(fig, [ax_main, ax_phase], colors)
    
    plt.tight_layout()
    
    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight', facecolor=colors['background'])
        print(f"✓ Saved: {save_path}")
    else:
        plt.show()
    
    plt.close()


# ============================================================================
# MONTH CALENDAR VIEW
# ============================================================================

def plot_monthly_calendar(
    monthly_analysis: MonthlyAnalysis,
    save_path: Optional[str] = None,
    theme: str = 'light'
):
    """
    Calendar heatmap showing fatigue risk across entire month
    """
    
    colors = Theme.dark() if theme == 'dark' else Theme.light()
    
    # Get all dates in month
    duties = monthly_analysis.duty_timelines
    if not duties:
        return
    
    first_date = min(d.duty_date for d in duties)
    last_date = max(d.duty_date for d in duties)
    
    # Create calendar grid (7 columns for days of week)
    fig, ax = plt.subplots(figsize=(16, 10))
    
    # Map duties to dates
    duty_map = {d.duty_date.date(): d for d in duties}
    
    # Start from first day of month
    month_start = first_date.replace(day=1)
    
    # Find first Monday before or on month start
    days_to_monday = month_start.weekday()
    grid_start = month_start - timedelta(days=days_to_monday)
    
    # Draw calendar grid
    row = 0
    col = 0
    current_date = grid_start
    
    max_rows = 6  # 6 weeks maximum
    
    for week in range(max_rows):
        for day in range(7):
            current_date = grid_start + timedelta(days=week * 7 + day)
            
            # Check if this date has a duty
            if current_date.date() in duty_map:
                duty_timeline = duty_map[current_date.date()]
                perf = duty_timeline.landing_performance or duty_timeline.min_performance
                
                # Risk color
                if perf >= 70:
                    color = colors['risk_low']
                elif perf >= 55:
                    color = colors['risk_moderate']
                elif perf >= 45:
                    color = colors['risk_high']
                else:
                    color = colors['risk_critical']
                
                # Draw colored square
                rect = mpatches.Rectangle(
                    (day, max_rows - week - 1), 1, 1,
                    facecolor=color,
                    edgecolor=colors['text'],
                    linewidth=2
                )
                ax.add_patch(rect)
                
                # Date number
                ax.text(
                    day + 0.5, max_rows - week - 1 + 0.7,
                    str(current_date.day),
                    ha='center', va='top',
                    fontsize=14,
                    fontweight='bold',
                    color=colors['text']
                )
                
                # Performance score
                ax.text(
                    day + 0.5, max_rows - week - 1 + 0.3,
                    f'{perf:.0f}',
                    ha='center', va='center',
                    fontsize=11,
                    color=colors['text']
                )
            
            elif current_date.month == first_date.month:
                # OFF day in current month
                rect = mpatches.Rectangle(
                    (day, max_rows - week - 1), 1, 1,
                    facecolor=colors['background'],
                    edgecolor=colors['grid'],
                    linewidth=1
                )
                ax.add_patch(rect)
                
                ax.text(
                    day + 0.5, max_rows - week - 1 + 0.5,
                    str(current_date.day),
                    ha='center', va='center',
                    fontsize=12,
                    color=colors['grid']
                )
                
                ax.text(
                    day + 0.5, max_rows - week - 1 + 0.2,
                    'OFF',
                    ha='center', va='center',
                    fontsize=9,
                    style='italic',
                    color=colors['grid']
                )
            
            else:
                # Outside current month
                rect = mpatches.Rectangle(
                    (day, max_rows - week - 1), 1, 1,
                    facecolor=colors['background'],
                    edgecolor='none',
                    alpha=0.3
                )
                ax.add_patch(rect)
    
    # Day labels
    days_of_week = ['MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT', 'SUN']
    for i, day_name in enumerate(days_of_week):
        ax.text(
            i + 0.5, max_rows + 0.2,
            day_name,
            ha='center', va='bottom',
            fontsize=12,
            fontweight='bold',
            color=colors['text']
        )
    
    # Title
    ax.set_title(
        f'{first_date.strftime("%B %Y")} - Fatigue Risk Calendar\n'
        f'{monthly_analysis.roster.pilot_id} | '
        f'High Risk: {monthly_analysis.high_risk_duties} | '
        f'Critical: {monthly_analysis.critical_risk_duties}',
        fontsize=16,
        fontweight='bold',
        pad=20
    )
    
    # Legend
    legend_y = -0.5
    legend_elements = [
        mpatches.Patch(color=colors['risk_low'], label='Low Risk (>70)'),
        mpatches.Patch(color=colors['risk_moderate'], label='Moderate (55-70)'),
        mpatches.Patch(color=colors['risk_high'], label='High (45-55)'),
        mpatches.Patch(color=colors['risk_critical'], label='Critical (<45)'),
    ]
    ax.legend(
        handles=legend_elements,
        loc='upper center',
        bbox_to_anchor=(0.5, legend_y),
        ncol=4,
        fontsize=11,
        frameon=True
    )
    
    ax.set_xlim(0, 7)
    ax.set_ylim(-1, max_rows + 0.5)
    ax.set_aspect('equal')
    ax.axis('off')
    
    apply_theme(fig, [ax], colors)
    
    plt.tight_layout()
    
    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight', facecolor=colors['background'])
        print(f"✓ Saved: {save_path}")
    else:
        plt.show()
    
    plt.close()


if __name__ == "__main__":
    print("Modern Visualization Module Loaded")
    print("Functions:")
    print("  - plot_duty_timeline_v2(duty_timeline, theme='light')")
    print("  - plot_monthly_calendar(monthly_analysis, theme='dark')")
