"""
config.py - EASA Fatigue Model Configuration (Version 2.1)
==========================================================

All model parameters, thresholds, and configuration settings.
Based on published research and EASA regulatory framework.

VERSION 2.1 IMPROVEMENTS:
- Interaction exponent default changed to 1.5 (non-linear fatigue)
- Added __post_init__ validation to all dataclasses
- Moved sleep quality multipliers to configurable parameters
- Added acclimatization reference switching logic
- Added conservative/liberal/research config variants

References:
- EU Regulation 965/2012 (EASA ORO.FTL)
- Borbély & Achermann (1999) - Two-process model
- EASA Moebus Report (2013) - Aviation fatigue parameters
- Van Dongen et al. (2003) - Sleep debt & non-linearity
- Dinges et al. (1997) - PVT performance degradation
- Tamaki et al. (2016) - First-night effect
- NASA Ames Fatigue Countermeasures Program
"""

from dataclasses import dataclass, field
from typing import Dict, Tuple


@dataclass
class EASAFatigueFramework:
    """
    EASA FTL regulatory definitions and thresholds
    Source: EU Regulation 965/2012 ORO.FTL + AMC/GM
    """
    
    # Window of Circadian Low (WOCL) - AMC1 ORO.FTL.105(10)
    wocl_start_hour: int = 2      # 02:00 local (reference time)
    wocl_end_hour: int = 5         # 05:59 local
    wocl_end_minute: int = 59
    
    # Acclimatization - AMC1 ORO.FTL.105(1)
    acclimatization_timezone_band_hours: float = 2.0
    acclimatization_required_local_nights: int = 3
    acclimatization_unknown_threshold_hours: float = 60.0
    
    # NEW in V2.1: Acclimatization state transitions
    acclimatization_partial_threshold_hours: float = 12.0   # Start adapting after 12h
    acclimatization_full_threshold_hours: float = 36.0      # Fully acclimatized after 36h
    
    # Circadian reference strategy for Process C calculation
    # Options: 'home_base' (conservative), 'destination' (aggressive), 'adaptive' (gradual)
    circadian_reference_strategy: str = 'adaptive'
    
    # For 'adaptive' strategy: Switch reference when this % adapted
    circadian_reference_switch_threshold: float = 0.5  # Switch at 50% adaptation
    
    # Local night definition (22:00-08:00)
    local_night_start_hour: int = 22
    local_night_end_hour: int = 8
    
    # Disruptive duties - GM1 ORO.FTL.235
    early_start_threshold_hour: int = 6
    late_finish_threshold_hour: int = 2
    
    # Rest requirements - ORO.FTL.235
    minimum_rest_hours: float = 12.0
    minimum_sleep_opportunity_hours: float = 8.0
    recurrent_rest_hours: float = 36.0
    recurrent_rest_local_nights: int = 2
    recurrent_rest_frequency_days: int = 7
    
    # FDP limits - ORO.FTL.205
    max_fdp_basic_hours: float = 13.0
    max_duty_hours: float = 14.0
    
    def __post_init__(self):
        """Validate EASA parameters"""
        
        # WOCL window
        assert 0 <= self.wocl_start_hour < 24, \
            f"WOCL start hour invalid: {self.wocl_start_hour}"
        assert 0 <= self.wocl_end_hour < 24, \
            f"WOCL end hour invalid: {self.wocl_end_hour}"
        assert self.wocl_start_hour < self.wocl_end_hour, \
            "WOCL window inverted (start must be before end)"
        
        # Acclimatization
        assert self.acclimatization_timezone_band_hours > 0, \
            "Timezone band must be positive"
        assert self.acclimatization_required_local_nights > 0, \
            "Required local nights must be positive"
        assert self.acclimatization_partial_threshold_hours > 0, \
            "Partial acclimatization threshold must be positive"
        assert self.acclimatization_full_threshold_hours > self.acclimatization_partial_threshold_hours, \
            "Full acclimatization threshold must be greater than partial threshold"
        
        # Circadian reference strategy
        assert self.circadian_reference_strategy in ['home_base', 'destination', 'adaptive'], \
            f"Invalid circadian reference strategy: {self.circadian_reference_strategy}"
        assert 0 < self.circadian_reference_switch_threshold <= 1.0, \
            "Switch threshold must be between 0 and 1"
        
        # Rest requirements
        assert self.minimum_rest_hours > 0, "Minimum rest must be positive"
        assert self.minimum_sleep_opportunity_hours > 0, "Minimum sleep opportunity must be positive"
        assert self.recurrent_rest_hours > self.minimum_rest_hours, \
            "Recurrent rest must be greater than minimum rest"


@dataclass
class BorbelyParameters:
    """
    Two-process sleep regulation model parameters
    
    Sources:
    - Borbély AA, Achermann P (1999). J Biol Rhythms, 14(6), 559-570
    - EASA Moebus Report (2013), Appendix
    - Van Dongen et al. (2003). Sleep debt dynamics
    - Dinges et al. (1997). PVT non-linear performance degradation
    """
    
    # Process S (Homeostatic) - Borbély 1999, Table 1
    S_max: float = 1.0
    S_min: float = 0.0
    tau_i: float = 18.2      # Wake build-up time constant (hours)
    tau_d: float = 4.2       # Sleep decay time constant (hours)
    
    # Process C (Circadian) - EASA Moebus 2013, p.47
    circadian_amplitude: float = 0.25
    circadian_mesor: float = 0.5
    circadian_period_hours: float = 24.0
    circadian_acrophase_hours: float = 17.0  # Peak alertness ~17:00 local
    
    # Performance integration (V2.1: Changed default to 1.5)
    weight_circadian: float = 0.4
    weight_homeostatic: float = 0.6
    
    # CHANGED in V2.1: Non-linear interaction (was 1.0)
    # Based on Dinges (1997) & Van Dongen (2003) - fatigue is exponential
    interaction_exponent: float = 1.5  # Creates "performance cliff" at high fatigue
    
    # Sleep inertia (Process W)
    inertia_duration_minutes: float = 30.0
    inertia_max_magnitude: float = 0.30
    
    # Sleep debt - Van Dongen 2003
    baseline_sleep_need_hours: float = 8.0
    sleep_debt_decay_rate: float = 0.25  # Per day (exponential decay)
    
    def __post_init__(self):
        """Validate parameters are physically plausible"""
        
        # Process S bounds
        assert 0 <= self.S_min < self.S_max <= 1.0, \
            f"S bounds invalid: S_min={self.S_min}, S_max={self.S_max} (must be 0 ≤ S_min < S_max ≤ 1)"
        
        # Time constants must be positive
        assert self.tau_i > 0, \
            f"Wake time constant must be positive: tau_i={self.tau_i}"
        assert self.tau_d > 0, \
            f"Sleep time constant must be positive: tau_d={self.tau_d}"
        
        # Typical range check (warn if unusual)
        if not (10 < self.tau_i < 30):
            import warnings
            warnings.warn(f"tau_i={self.tau_i} is outside typical range (10-30h)")
        if not (2 < self.tau_d < 8):
            import warnings
            warnings.warn(f"tau_d={self.tau_d} is outside typical range (2-8h)")
        
        # Circadian parameters
        assert 0 < self.circadian_amplitude <= 0.5, \
            f"Circadian amplitude unrealistic: {self.circadian_amplitude} (must be 0 < amp ≤ 0.5)"
        assert 0 <= self.circadian_mesor <= 1.0, \
            f"Circadian mesor out of range: {self.circadian_mesor} (must be 0 ≤ mesor ≤ 1)"
        assert 0 <= self.circadian_acrophase_hours < 24, \
            f"Acrophase must be 0-24h: {self.circadian_acrophase_hours}"
        
        # Performance integration
        weight_sum = self.weight_circadian + self.weight_homeostatic
        assert abs(weight_sum - 1.0) < 0.001, \
            f"Weights must sum to 1.0: circadian={self.weight_circadian}, homeostatic={self.weight_homeostatic}, sum={weight_sum}"
        
        assert self.interaction_exponent > 0, \
            f"Interaction exponent must be positive: {self.interaction_exponent}"
        
        # Typical range for exponent
        if not (1.0 <= self.interaction_exponent <= 3.0):
            import warnings
            warnings.warn(f"interaction_exponent={self.interaction_exponent} is outside typical range (1.0-3.0)")
        
        # Sleep inertia
        assert self.inertia_duration_minutes > 0, \
            f"Inertia duration must be positive: {self.inertia_duration_minutes}"
        assert 0 <= self.inertia_max_magnitude <= 1.0, \
            f"Inertia magnitude out of range: {self.inertia_max_magnitude} (must be 0-1)"
        
        # Sleep debt
        assert self.baseline_sleep_need_hours > 0, \
            f"Sleep need must be positive: {self.baseline_sleep_need_hours}"
        assert 0 < self.sleep_debt_decay_rate < 1.0, \
            f"Decay rate must be (0,1): {self.sleep_debt_decay_rate}"


@dataclass
class SleepQualityParameters:
    """
    Sleep quality multipliers by environment
    NEW in V2.1: Extracted from hardcoded values to configuration
    
    Based on:
    - Tamaki et al. (2016) - First-night effect in unfamiliar environments
    - NASA Ames Fatigue Countermeasures Program - Inflight rest studies
    - Rosekind et al. (1995) - Cockpit naps effectiveness
    - Operational pilot feedback
    
    Note: These are evidence-based estimates, not EASA-validated values
    """
    
    # Environment quality factors (0-1 scale)
    quality_home: float = 1.0                    # Baseline (familiar, quiet, comfortable)
    quality_hotel_quiet: float = 0.85            # Good hotel, minimal disturbance
    quality_hotel_typical: float = 0.80          # Average hotel
    quality_hotel_airport: float = 0.75          # Airport hotel (more noise)
    quality_layover_unfamiliar: float = 0.78     # Unfamiliar location
    quality_crew_rest_facility: float = 0.65     # Inflight bunk (noise, vibration, altitude)
    
    # Circadian misalignment penalty (applied separately from environment)
    max_circadian_quality_penalty: float = 0.25  # Up to 25% reduction for severe misalignment
    
    # Time-of-sleep penalties
    early_wake_penalty_per_hour: float = 0.05    # 5% per hour waking before 06:00
    late_sleep_start_penalty_per_hour: float = 0.03  # 3% per hour starting after 24:00
    
    # Sleep opportunity duration efficiency
    short_sleep_penalty_threshold_hours: float = 4.0   # Below 4h = reduced efficiency
    short_sleep_efficiency_factor: float = 0.75        # 75% efficiency for short sleep
    long_sleep_penalty_threshold_hours: float = 9.0    # Above 9h = reduced efficiency
    long_sleep_efficiency_decay_rate: float = 0.03     # 3% per hour above 9h
    
    def __post_init__(self):
        """Validate all quality factors are plausible"""
        
        qualities = [
            ('home', self.quality_home),
            ('hotel_quiet', self.quality_hotel_quiet),
            ('hotel_typical', self.quality_hotel_typical),
            ('hotel_airport', self.quality_hotel_airport),
            ('layover_unfamiliar', self.quality_layover_unfamiliar),
            ('crew_rest_facility', self.quality_crew_rest_facility)
        ]
        
        for name, q in qualities:
            assert 0.4 <= q <= 1.0, \
                f"Sleep quality for {name} out of plausible range: {q} (must be 0.4-1.0)"
        
        # Home should be best quality
        assert self.quality_home >= max(q for _, q in qualities), \
            "Home quality should be >= all other environments"
        
        # Crew rest should be lowest (most challenging environment)
        assert self.quality_crew_rest_facility <= min(q for _, q in qualities), \
            "Crew rest facility should be <= all other environments"
        
        # Penalties should be reasonable
        assert 0 <= self.max_circadian_quality_penalty <= 0.5, \
            f"Circadian penalty too large: {self.max_circadian_quality_penalty} (max 0.5)"
        
        assert 0 <= self.early_wake_penalty_per_hour <= 0.2, \
            "Early wake penalty unrealistic"
        
        assert 0 <= self.late_sleep_start_penalty_per_hour <= 0.2, \
            "Late sleep penalty unrealistic"
        
        # Duration efficiency
        assert 0 < self.short_sleep_penalty_threshold_hours < 8, \
            "Short sleep threshold should be reasonable"
        assert 0.5 <= self.short_sleep_efficiency_factor <= 1.0, \
            "Short sleep efficiency factor out of range"


@dataclass
class AdaptationRates:
    """
    Circadian adaptation rates for timezone shifts
    
    Sources:
    - Aschoff J (1978). Ergonomics, 21(10), 739-754
    - Waterhouse J et al. (2007). Aviation Space Env Med
    - Czeisler et al. (1989). N Engl J Med - Circadian phase shifting
    """
    westward_hours_per_day: float = 1.5  # Phase delay (easier)
    eastward_hours_per_day: float = 1.0   # Phase advance (harder)
    
    def get_rate(self, timezone_shift_hours: float) -> float:
        """Return adaptation rate based on direction"""
        return self.westward_hours_per_day if timezone_shift_hours < 0 else self.eastward_hours_per_day
    
    def __post_init__(self):
        """Validate adaptation rates"""
        assert 0 < self.westward_hours_per_day <= 3.0, \
            f"Westward rate unrealistic: {self.westward_hours_per_day} (typical: 0.5-2.5 h/day)"
        assert 0 < self.eastward_hours_per_day <= 2.0, \
            f"Eastward rate unrealistic: {self.eastward_hours_per_day} (typical: 0.5-1.5 h/day)"
        
        # Westward should typically be faster (phase delay easier than advance)
        if self.eastward_hours_per_day > self.westward_hours_per_day:
            import warnings
            warnings.warn(
                f"Eastward rate ({self.eastward_hours_per_day}) > Westward rate ({self.westward_hours_per_day}). "
                "This is atypical - westward adaptation is usually faster."
            )


@dataclass
class RiskThresholds:
    """
    Performance score thresholds with EASA regulatory references
    
    Validated against:
    - Psychomotor Vigilance Task (PVT)
    - Operational error rates
    - Sleep deprivation equivalence studies
    """
    
    thresholds: Dict[str, Tuple[float, float]] = field(default_factory=lambda: {
        'low': (75, 100),
        'moderate': (65, 75),
        'high': (55, 65),
        'critical': (45, 55),
        'extreme': (0, 45)
    })
    
    actions: Dict[str, Dict[str, str]] = field(default_factory=lambda: {
        'low': {
            'action': 'None required',
            'easa_reference': None,
            'description': 'Well-rested state (7-8h quality sleep)'
        },
        'moderate': {
            'action': 'Enhanced monitoring recommended',
            'easa_reference': 'AMC1 ORO.FTL.120 - Awareness',
            'description': 'Equivalent to ~6h sleep or mild circadian misalignment'
        },
        'high': {
            'action': 'Mitigation: Controlled rest, crew augmentation, or duty adjustment',
            'easa_reference': 'GM1 ORO.FTL.235 - Disruptive duty mitigation',
            'description': 'Equivalent to ~5h sleep. Error rate increased 20-30%'
        },
        'critical': {
            'action': 'MANDATORY: Roster modification or crew augmentation required',
            'easa_reference': 'ORO.FTL.120(a) - Shall not assign if likely fatigued',
            'description': 'Equivalent to ~4h sleep. Impairment similar to BAC 0.05-0.08%'
        },
        'extreme': {
            'action': 'UNSAFE: Do not fly - file fatigue report immediately',
            'easa_reference': 'ORO.FTL.120(b) - Shall not undertake if fatigued',
            'description': 'Severe impairment. Safety compromised.'
        }
    })
    
    def classify(self, performance: float) -> str:
        """Classify performance score into risk category"""
        if performance is None:
            return 'unknown'
        for level, (low, high) in self.thresholds.items():
            if low <= performance < high:
                return level
        return 'extreme'
    
    def get_action(self, risk_level: str) -> Dict[str, str]:
        """Get recommended action for risk level"""
        return self.actions.get(risk_level, self.actions['extreme'])
    
    def __post_init__(self):
        """Validate risk thresholds"""
        
        # Check all thresholds are properly ordered
        levels_order = ['extreme', 'critical', 'high', 'moderate', 'low']
        prev_upper = 0
        
        for level in levels_order:
            lower, upper = self.thresholds[level]
            
            assert 0 <= lower < upper <= 100, \
                f"Threshold for {level} invalid: ({lower}, {upper})"
            
            assert lower == prev_upper, \
                f"Gap in thresholds at {level}: previous upper={prev_upper}, current lower={lower}"
            
            prev_upper = upper
        
        # Ensure all action info exists
        for level in self.thresholds.keys():
            assert level in self.actions, f"Missing action definition for {level}"
            assert 'action' in self.actions[level], f"Missing 'action' for {level}"
            assert 'description' in self.actions[level], f"Missing 'description' for {level}"


@dataclass
class ModelConfig:
    """
    Master configuration - allows switching between model variants
    """
    easa_framework: EASAFatigueFramework
    borbely_params: BorbelyParameters
    risk_thresholds: RiskThresholds
    adaptation_rates: AdaptationRates
    sleep_quality_params: SleepQualityParameters  # NEW in V2.1
    
    @classmethod
    def default_easa_config(cls):
        """
        Default configuration based on EASA research
        Balanced approach - suitable for most operational use
        """
        return cls(
            easa_framework=EASAFatigueFramework(),
            borbely_params=BorbelyParameters(),
            risk_thresholds=RiskThresholds(),
            adaptation_rates=AdaptationRates(),
            sleep_quality_params=SleepQualityParameters()
        )
    
    @classmethod
    def conservative_config(cls):
        """
        Conservative configuration for safety-critical operations
        - Stricter risk thresholds
        - Stronger non-linearity (steeper performance cliff)
        - More cautious sleep quality assumptions
        """
        config = cls.default_easa_config()
        
        # Shift risk thresholds higher (more conservative)
        config.risk_thresholds.thresholds = {
            'low': (80, 100),
            'moderate': (70, 80),
            'high': (60, 70),
            'critical': (50, 60),
            'extreme': (0, 50)
        }
        
        # Stronger non-linearity (performance cliff at high fatigue)
        config.borbely_params.interaction_exponent = 2.0
        
        # More pessimistic sleep quality
        config.sleep_quality_params.quality_hotel_typical = 0.75
        config.sleep_quality_params.quality_crew_rest_facility = 0.60
        
        return config
    
    @classmethod
    def liberal_config(cls):
        """
        Liberal configuration (mirrors typical airline assumptions)
        - More forgiving thresholds
        - Less aggressive non-linearity
        - Optimistic sleep quality
        
        WARNING: May underestimate fatigue risk
        """
        config = cls.default_easa_config()
        
        # More lenient thresholds
        config.risk_thresholds.thresholds = {
            'low': (70, 100),
            'moderate': (60, 70),
            'high': (50, 60),
            'critical': (40, 50),
            'extreme': (0, 40)
        }
        
        # Weaker non-linearity
        config.borbely_params.interaction_exponent = 1.2
        
        # Optimistic sleep quality
        config.sleep_quality_params.quality_hotel_typical = 0.85
        config.sleep_quality_params.quality_crew_rest_facility = 0.70
        
        return config
    
    @classmethod
    def research_config(cls):
        """
        Research configuration for academic/validation studies
        - Matches published research parameters exactly
        - No operational safety margins
        - Use for comparing against published case studies
        """
        config = cls.default_easa_config()
        
        # Pure Borbély parameters (Borbély & Achermann 1999)
        config.borbely_params.tau_i = 18.2
        config.borbely_params.tau_d = 4.2
        config.borbely_params.interaction_exponent = 1.0  # Linear (original model)
        
        # No safety margins on thresholds
        config.risk_thresholds.thresholds = {
            'low': (75, 100),
            'moderate': (65, 75),
            'high': (55, 65),
            'critical': (45, 55),
            'extreme': (0, 45)
        }
        
        return config
    
    def __post_init__(self):
        """Validate complete configuration"""
        
        # All components should have already validated themselves
        # This is just a final consistency check
        
        # Ensure circadian weights are sensible
        total_weight = (self.borbely_params.weight_circadian + 
                       self.borbely_params.weight_homeostatic)
        
        assert abs(total_weight - 1.0) < 0.001, \
            f"Circadian + Homeostatic weights must sum to 1.0, got {total_weight}"
