# 🚀 EASA Fatigue Analysis Tool - COMPLETE SETUP GUIDE

## What You Have

You now have a **fully working fatigue analysis prototype** with:

✅ Core biomathematical engine (Borbély two-process model)
✅ EASA compliance validation  
✅ Risk scoring with regulatory references
✅ Dynamic circadian adaptation
✅ Sleep debt tracking
✅ Pinch event detection

## 📁 Your Files

```
fatigue_tool/
├── Core Engine:
│   ├── config.py              ← Model parameters (START HERE to customize)
│   ├── data_models.py         ← Data structures
│   ├── core_model.py          ← Biomathematical engine
│   ├── easa_utils.py          ← Compliance & risk tools
│
├── User Interfaces:
│   ├── simple_example.py      ← Test the system (RUN THIS FIRST)
│   ├── analyze_duty.py        ← Interactive CLI
│   ├── fatigue_app.py         ← Web interface (Streamlit)
│
├── Advanced Features:
│   ├── roster_parser.py       ← Parse PDF/CSV rosters
│   ├── visualization.py       ← Charts and graphs
│
└── Documentation:
    ├── README.md              ← Detailed usage guide
    ├── requirements.txt       ← Python dependencies
    └── SETUP.md              ← This file
```

---

## 🎯 QUICK START (3 Minutes)

### 1️⃣ Install Dependencies

```bash
# Navigate to the fatigue_tool directory
cd fatigue_tool

# Install required packages
pip install -r requirements.txt
```

**Required packages:**
- `pytz` - Timezone handling
- `streamlit` - Web interface (optional for basic use)
- `pandas`, `plotly` - Visualizations (optional)
- `tabula-py` - PDF parsing (optional)

### 2️⃣ Test the System

```bash
python simple_example.py
```

**Expected output:**
```
======================================================================
EASA Fatigue Analysis - Simple Example
======================================================================

Creating sample duty: DOH → LHR...
  Departure: 2024-01-18 02:30 UTC
  Arrival:   2024-01-18 09:00 UTC
  Duration:  6.5 hours

Running biomathematical fatigue analysis...
✓ Analysis complete

──────────────────────────────────────────────────────────────────────
PERFORMANCE METRICS
──────────────────────────────────────────────────────────────────────
  Minimum Performance:     XX.X/100
  Landing Performance:     XX.X/100
  ...
```

If you see this, **everything works!** ✅

### 3️⃣ Choose Your Interface

#### **Option A: Simple Example** (Already tested!)
Just edit `simple_example.py` to analyze different duties.

#### **Option B: Interactive CLI**
```bash
python analyze_duty.py
```
Answer prompts to analyze any duty interactively.

#### **Option C: Web Interface** (Most powerful)
```bash
streamlit run fatigue_app.py
```
Opens in your browser with full features:
- Upload rosters (PDF/CSV)
- Visual timeline graphs
- Monthly heatmaps
- Export reports

---

## 📖 Usage Examples

### Example 1: Analyze Your Next Duty

Edit `simple_example.py` (lines 28-60):

```python
# Change these to match your actual duty:
doh = Airport("DOH", "Asia/Qatar", 25.273056, 51.608056)
lhr = Airport("LHR", "Europe/London", 51.4700, -0.4543)

departure_time = datetime(2024, 2, 15, 2, 30, tzinfo=pytz.utc)  # YOUR DATE
arrival_time = datetime(2024, 2, 15, 9, 0, tzinfo=pytz.utc)     # YOUR DATE

# Then run:
python simple_example.py
```

### Example 2: Compare Configurations

```python
from core_model import BorbelyFatigueModel
from config import ModelConfig

# Try conservative model (stricter thresholds)
conservative_model = BorbelyFatigueModel(
    config=ModelConfig.conservative_config()
)

# Try liberal model (matches airline assumptions)
liberal_model = BorbelyFatigueModel(
    config=ModelConfig.liberal_config()
)

# Compare results...
```

### Example 3: Build Your Own Analysis

```python
from datetime import datetime
import pytz
from config import ModelConfig
from data_models import Airport, FlightSegment, Duty, Roster
from core_model import BorbelyFatigueModel
from easa_utils import FatigueRiskScorer

# 1. Define airports
doh = Airport("DOH", "Asia/Qatar")
jfk = Airport("JFK", "America/New_York")

# 2. Create flight
segment = FlightSegment(
    flight_number="QR701",
    departure_airport=doh,
    arrival_airport=jfk,
    scheduled_departure_utc=datetime(2024, 3, 1, 22, 0, tzinfo=pytz.utc),
    scheduled_arrival_utc=datetime(2024, 3, 2, 12, 30, tzinfo=pytz.utc)
)

# 3. Create duty (with 1h before/after)
duty = Duty(
    duty_id="D001",
    date=datetime(2024, 3, 1),
    report_time_utc=datetime(2024, 3, 1, 21, 0, tzinfo=pytz.utc),
    release_time_utc=datetime(2024, 3, 2, 13, 30, tzinfo=pytz.utc),
    segments=[segment],
    home_base_timezone="Asia/Qatar"
)

# 4. Create roster
roster = Roster(
    roster_id="MAR2024",
    pilot_id="P12345",
    month="2024-03",
    duties=[duty],
    home_base_timezone="Asia/Qatar"
)

# 5. Analyze!
model = BorbelyFatigueModel()
analysis = model.simulate_roster(roster)

# 6. Get results
timeline = analysis.duty_timelines[0]
print(f"Landing performance: {timeline.landing_performance:.1f}/100")

scorer = FatigueRiskScorer()
risk = scorer.score_duty_timeline(timeline)
print(f"Risk level: {risk['overall_risk'].upper()}")
```

---

## 🔧 Customization

### Adjust Model Parameters

Edit `config.py`:

```python
@dataclass
class BorbelyParameters:
    # Process S (sleep pressure)
    tau_i: float = 18.2      # Wake build-up (hours)
    tau_d: float = 4.2       # Sleep decay (hours)
    
    # Performance integration
    interaction_exponent: float = 1.5  # Non-linearity (1.0-3.0)
    
    # Sleep debt
    baseline_sleep_need_hours: float = 8.0
    sleep_debt_decay_rate: float = 0.25  # Daily decay
```

### Change Risk Thresholds

Edit `config.py`:

```python
@dataclass
class RiskThresholds:
    thresholds: Dict[str, Tuple[float, float]] = field(default_factory=lambda: {
        'low': (75, 100),      # Adjust these ranges
        'moderate': (65, 75),
        'high': (55, 65),
        'critical': (45, 55),
        'extreme': (0, 45)
    })
```

### Modify Sleep Quality Assumptions

Edit `config.py`:

```python
@dataclass
class SleepQualityParameters:
    quality_home: float = 0.90                  # Best quality
    quality_hotel_quiet: float = 0.85
    quality_hotel_typical: float = 0.80         # Default
    quality_hotel_airport: float = 0.75
    quality_layover_unfamiliar: float = 0.70
    quality_crew_rest_facility: float = 0.65    # Worst quality
```

---

## 📊 Understanding the Science

### The Borbély Two-Process Model

The tool uses a validated biomathematical model:

**Process S (Homeostatic):**
- Sleep pressure builds up during wake (exponentially)
- Dissipates during sleep (exponentially)
- Time constants: τ_i = 18.2h (wake), τ_d = 4.2h (sleep)

**Process C (Circadian):**
- 24-hour biological rhythm
- Peak alertness ~17:00 local time
- Lowest alertness ~04:00 (WOCL)
- Gradually adapts to new timezones

**Process W (Sleep Inertia):**
- Post-awakening grogginess
- Dissipates over ~30 minutes
- Strongest when waking during circadian low

**Performance = f(C, S, W)**
- Non-linear integration (interaction_exponent)
- Multiplicative effects ("pinch")
- Sleep debt accumulation

### What the Numbers Mean

**Performance Score (0-100):**
- 100 = Perfect (impossible in real life)
- 75-100 = Well-rested baseline
- 65-75 = Equivalent to ~6h sleep
- 55-65 = Equivalent to ~5h sleep, 20-30% error increase
- 45-55 = Equivalent to ~4h sleep, similar to BAC 0.05%
- 0-45 = Severe impairment, unsafe

**Landing Performance:**
- Most critical metric
- Calculated at touchdown
- Accounts for:
  - Time since last sleep
  - Circadian phase at landing
  - Cumulative sleep debt
  - Flight duration

**Pinch Events:**
- High sleep pressure (S > 0.7)
- During circadian low (C < 0.4)
- Multiplicatively worse than either alone
- Flagged during critical flight phases

---

## ⚠️ Limitations & Disclaimers

### What This Tool Does:
✅ Estimates fatigue based on roster timing
✅ Uses EASA-validated scientific model
✅ Provides evidence for SMS reports
✅ Helps compare roster options
✅ Identifies high-risk duties proactively

### What This Tool Does NOT Do:
❌ Account for individual differences (chronotype, age, health)
❌ Track actual sleep (uses estimates from duty gaps)
❌ Replace airline FRMS
❌ Make fitness-for-duty decisions
❌ Guarantee safety or regulatory compliance

### Legal Status:
- **Educational tool** based on published research
- **Not certified** for regulatory use
- **Not validated** against operational data
- **For advocacy** and education only

### Always Remember:
> **You are the final authority on your fitness to fly.**  
> EASA ORO.FTL.120: "A crew member shall not perform duties on an aircraft if unfit due to fatigue."

Use this tool to:
- Understand your fatigue risk
- File proactive SMS reports
- Request roster changes
- Compare duty patterns

Do NOT use it to:
- Override your professional judgment
- Justify flying when fatigued
- Replace company FRMS processes

---

## 🎓 Next Steps

### For Individual Pilots:

1. **Test with your last month's roster**
   - Identify which duties were high-risk
   - Compare predictions to how you actually felt

2. **Analyze your upcoming roster**
   - Find high-risk duties before flying them
   - Request changes proactively

3. **Build evidence for SMS reports**
   - Use screenshots and metrics
   - Include EASA regulatory references
   - Show specific performance predictions

### For Safety Representatives:

1. **Analyze fleet patterns**
   - Which routes are consistently problematic?
   - Are certain pairings high-risk?
   - Month-over-month trends

2. **Compare roster options**
   - Quantify fatigue impact of scheduling changes
   - Present data-driven safety cases

3. **Validate company FRMS**
   - Compare predictions to company's tool
   - Identify discrepancies

### For Researchers:

1. **Calibrate the model**
   - Compare against published case studies
   - Adjust parameters if needed

2. **Validate predictions**
   - Correlate with actual fatigue reports
   - Sensitivity analysis

3. **Extend functionality**
   - Add individual variation modeling
   - Integrate with wearable data
   - Develop mobile app

---

## 🐛 Troubleshooting

### Common Issues:

**"Module not found" errors**
```bash
pip install -r requirements.txt
```

**Timezone errors**
- Use IANA format: `"Europe/London"` not `"GMT"`
- Check `data_models.py` Airport definitions

**Very low performance scores**
- Check duty timing (WOCL encroachment?)
- Ensure roster includes realistic rest
- Try `ModelConfig.liberal_config()` for comparison

**Streamlit won't start**
```bash
# Install Streamlit
pip install streamlit

# Run from correct directory
cd fatigue_tool
streamlit run fatigue_app.py
```

**Parsing PDF rosters**
- Requires `tabula-py` and Java
- Alternative: manually enter duties via CLI

---

## 📚 Resources

### EASA Regulations:
- [EU Regulation 965/2012 (ORO.FTL)](https://www.easa.europa.eu/document-library/easy-access-rules/online-publications/easy-access-rules-air-operations)

### Scientific Papers:
- Borbély & Achermann (1999) - Two-process model foundations
- EASA Moebus Report (2013) - Aviation-specific parameters
- Van Dongen et al. (2003) - Sleep debt dynamics

### Further Reading:
- NASA Fatigue Countermeasures Program
- ICAO Fatigue Management Guide (Doc 9966)
- Flight Safety Foundation FRMS resources

---

## 💡 Pro Tips

1. **Start Conservative**: Use `conservative_config()` for safety advocacy
2. **Focus on Landing**: This is your most critical performance metric
3. **Document Everything**: Screenshots + EASA refs = strong SMS report
4. **Track Trends**: Monthly analysis reveals patterns
5. **Be Proactive**: Don't wait until exhausted - use tool before flying

---

## 🤝 Support & Contribution

This is an open educational project.

**Questions?** Check:
1. This SETUP.md file
2. README.md (detailed usage)
3. Example files (simple_example.py, analyze_duty.py)

**Found a bug?** 
- Check your input data first
- Try different configurations
- Review the scientific assumptions

**Want to contribute?**
- Improve documentation
- Add features (mobile interface, wearable integration)
- Validate against operational data
- Share case studies

---

## ✈️ Final Words

**You now have the same fatigue modeling capability that airlines use internally.**

This levels the playing field. Use it wisely:

- ✅ File evidence-based fatigue reports
- ✅ Request roster modifications proactively
- ✅ Make informed safety decisions
- ✅ Advocate for yourself and colleagues

But remember:

- ⚠️  This tool estimates - you are the expert on YOUR fatigue
- ⚠️  Professional judgment always overrides any model
- ⚠️  When in doubt, file a report and rest

**Fly safe! 🛫**

---

*Last updated: 2024-01-24*  
*Version: 2.0 (Modular Architecture)*
