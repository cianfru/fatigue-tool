# Aerowake - Aviation Fatigue Prediction System

## What is Aerowake?

Aerowake is a biomathematical fatigue prediction system built for airline pilots. It models the cognitive performance degradation that accumulates across multi-day rosters, using the same class of sleep-physiology models that underpin EASA's Flight Time Limitation (FTL) regulatory framework (EU Regulation 965/2012).

The tool takes a pilot's roster as input --- a sequence of duties, flights, and rest periods --- and produces a continuous performance timeline at 30-minute resolution. It identifies the duties where fatigue risk is highest, explains *why* through decomposed process scores, and maps each risk level to the specific EASA regulatory provisions that apply.

Aerowake is an **educational and advocacy tool**. It is not certified for regulatory compliance and must not be used for fitness-for-duty determination. Its purpose is to give individual pilots transparent, evidence-based fatigue analysis --- the same class of information that airlines derive from commercial FRMS platforms, but available independently and with full methodological visibility.

---

## Core Model: The Borbely Two-Process Framework

Aerowake's predictions rest on the **Borbely Two-Process Model** of sleep regulation (Borbely, 1982; Borbely & Achermann, 1999), the most widely validated framework in sleep physiology. The model treats alertness as the output of two independent biological processes operating on different timescales:

### Process S --- Homeostatic Sleep Pressure

Process S represents the body's accumulating need for sleep. It rises exponentially during wakefulness and decays exponentially during sleep:

- **During wake:** S(t) = S_max - (S_max - S_0) * exp(-t / tau_i), where tau_i = 18.2 hours
- **During sleep:** S(t) = S_min + (S_0 - S_min) * exp(-t / tau_d), where tau_d = 4.2 hours

The time constants are drawn from Jewett & Kronauer (1999). After 18 hours awake, homeostatic pressure has risen to roughly 63% of its range. After 4.2 hours of sleep, it has recovered by the same proportion. This asymmetry --- slow buildup, faster recovery --- matches the empirical observation that a full night of sleep can largely restore performance after a long day, but extended wakefulness produces accelerating impairment.

### Process C --- Circadian Rhythm

Process C is the 24-hour biological clock that modulates alertness independently of how long you have been awake. It is modelled as a cosine oscillation:

- C(t) = mesor + amplitude * cos(2 * pi * (hour - acrophase) / 24)
- Mesor = 0.5, Amplitude = 0.25, Acrophase = 17:00

This produces a peak in alertness during the late afternoon (16:00--18:00) and a trough during the early morning hours (03:00--05:00). The trough aligns with the EASA-defined **Window of Circadian Low (WOCL)**: 02:00--05:59 in the pilot's acclimatized timezone (AMC1 ORO.FTL.105(10)).

The circadian process does not reset with sleep. It free-runs on a near-24-hour period and shifts gradually when the pilot crosses timezones --- westward at approximately 1.5 hours/day (phase delay) and eastward at approximately 1.0 hours/day (phase advance), following Waterhouse et al. (2007).

### Process W --- Sleep Inertia

A third short-duration process captures **sleep inertia**: the transient grogginess immediately after waking. It decays exponentially over approximately 30 minutes from a maximum magnitude of 0.30 (Tassi & Muzet, 2000). This is operationally significant when a pilot wakes from controlled rest during cruise and must be prepared for approach and landing shortly after.

### Time-on-Task Decrement

Aerowake also incorporates a linear **time-on-task** fatigue component (Folkard & Akerstedt, 1999), modelling the gradual decline in sustained attention that occurs independently of sleep and circadian state. The rate is 0.003 per hour on duty (approximately 0.24% per hour on the 0--100 performance scale), calibrated for aviation operations where structured crew coordination partially mitigates continuous vigilance demands.

### Integration into a Performance Score

The processes combine into a single performance score on a 0--100 scale:

```
alertness   = (1 - S) * 0.50 + ((C + 1) / 2) * 0.50
alertness  *= (1 - W)                                  # sleep inertia
alertness  -= time_on_task_rate * hours_on_duty        # linear decrement
alertness  *= 1 - (workload - 1) * workload_sensitivity # flight-phase demand
performance = 20 + 80 * alertness
```

The score floor of 20 prevents mathematically impossible zero-performance predictions. A score of 100 represents a fully rested pilot at circadian peak. The 50/50 weighting between homeostatic and circadian components is an operational adaptation; the research configuration provides pure additive Borbely parameters for academic comparison.

Workload scales the performance *output* rather than the homeostatic input. Process S remains a function of time awake and time asleep alone, as in Borbely (1982) --- a demanding approach consumes spare cognitive capacity in the moment, it does not make the pilot's sleep pressure accumulate faster.

> **Detailed mathematics** --- including the full differential equations, parameter derivations, sensitivity analysis, and validation against published laboratory data --- will be covered in a dedicated **Science & Mathematics** module.

---

## Sleep Estimation: Predicting What the Pilot Actually Gets

A fatigue model is only as good as its sleep inputs. Since Aerowake analyses rosters prospectively (before they are flown), it must *estimate* how much sleep a pilot is likely to obtain between duties. This is handled by the **Unified Sleep Calculator**, which selects from five empirically-grounded sleep strategies based on duty timing and context:

| Strategy | Trigger | Typical Sleep | Rationale |
|---|---|---|---|
| **Normal** | Standard daytime duties | ~8 hours (23:00--07:00 home time) | Default circadian-aligned sleep |
| **Early Morning** | Report before 07:00 | 4.0--6.6 hours | Regression model: early alarm truncates sleep; pilots rarely compensate with earlier bedtime |
| **Night Departure** | Report after 20:00 or before 04:00 | Morning block + pre-duty nap | Split sleep pattern observed in night-flying crews (Roach et al., 2012) |
| **WOCL Anchor** | Duty encroaching WOCL + duration > 6 hours | ~4.5 hours anchor sleep | Preserves circadian alignment during disrupted schedules (Gander et al., 2013) |
| **Recovery** | Post-duty rest period | Extended sleep opportunity | Elevated homeostatic drive accelerates debt repayment |

### Sleep Quality Modelling

Raw sleep duration is adjusted by a **quality multiplier** that accounts for sleep environment and timing. The base efficiency values are anchored to polysomnography data from Signal et al. (2013):

- **Home sleep:** 90--100% efficiency
- **Hotel sleep:** 82--88% efficiency (depending on noise environment)
- **Crew rest facility (in-flight bunk):** ~70% efficiency

Seven multiplicative factors then modify the base efficiency:

1. Location-based efficiency (home, hotel, crew rest)
2. WOCL timing bonus (sleep aligned with circadian low is deeper and more restorative)
3. Late-onset penalty (difficulty initiating sleep after 01:00)
4. Recovery boost (elevated homeostatic drive after extended duty)
5. Time pressure penalty (sleep curtailed by proximity to next duty)
6. Insufficient duration penalty (sleep episodes under 6 hours)
7. Final clamping to the range 0.65--1.0 (prevents unrealistic extremes)

The product of these factors converts raw sleep hours into **effective sleep hours**, which is what drives Process S recovery.

> **Full methodology** --- including the regression models for early-start sleep prediction, the derivation of quality factors, and comparison to PSG validation data --- will be detailed in the **Sleep Science** module.

---

## Cumulative Sleep Debt

Aerowake tracks **cumulative sleep debt** across the entire roster, measured in *effective* (quality-weighted) sleep hours against a restorative baseline of 7.4 hours per day. Effective hours are used because they already account for fragmentation, poor environments and circadian misalignment --- a five-hour night plus an afternoon nap is not the same as a consolidated eight-hour night, even though the raw totals are close.

Debt accumulates whenever the sleep obtained across an inter-duty gap falls short of the need for that gap. When the need is met, debt repays by exponential decay:

- Debt recovery follows: debt(t) = debt_0 * exp(-0.35 * days)
- Half-life of approximately 2.0 days

Recovery is deliberately incomplete. Banks et al. (2010) found that a single ten-hour sleep opportunity did not restore baseline performance after chronic restriction, and Kitamura et al. (2016) found that an hour of debt requires roughly four days of optimal sleep to clear. Decay is the sole repayment mechanism --- crediting surplus hours separately, as an earlier version did, recovered debt about twice as fast as the evidence supports.

### Why this matters for roster prediction

Sleep debt is settled **before** each duty is simulated and raises the starting value of Process S for that duty. This is the mechanism that makes consecutive early starts, night flights and short-rest turnarounds compound rather than being scored as independent events. A pilot carrying a week of truncated nights starts each duty further up the homeostatic curve than a rested pilot flying the identical schedule --- which is precisely the effect Van Dongen et al. (2003) documented, where fourteen nights at six hours produced impairment comparable to two nights of total sleep deprivation despite normal sleep the preceding night.

The contribution is capped, so debt alone cannot saturate the homeostat and drive predictions to the performance floor.

---

## EASA Regulatory Alignment

Every risk classification that Aerowake produces maps directly to EASA FTL provisions:

| Performance Score | Risk Level | EASA Reference | Required Action |
|---|---|---|---|
| 75--100 | Low | --- | No action required |
| 65--75 | Moderate | AMC1 ORO.FTL.120 | Enhanced monitoring |
| 55--65 | High | GM1 ORO.FTL.235 | Mitigation required |
| 45--55 | Critical | ORO.FTL.120(a) | Mandatory roster modification |
| 0--45 | Extreme | ORO.FTL.120(b) | Unsafe --- do not fly |

The tool also validates against specific FTL limits:

- **Maximum FDP:** 13 hours basic (ORO.FTL.205), with up to 2 hours commander discretion
- **Minimum rest:** 12 hours including 8 hours sleep opportunity (ORO.FTL.235)
- **WOCL encroachment:** Total hours of duty falling within 02:00--05:59 home time
- **Acclimatization state:** Tracked per AMC1 ORO.FTL.105(1) --- a pilot is acclimatized after 3 local nights within a 2-hour timezone band of their reference point
- **Disruptive duty classification:** Duties that cross the WOCL or involve early starts / late finishes (GM1 ORO.FTL.235)

### Pinch Events

Aerowake identifies **pinch events**: operationally dangerous moments where high homeostatic sleep pressure coincides with a circadian trough. These represent the highest-risk points in a roster, where both biological fatigue drivers are working against the pilot simultaneously. Pinch events are flagged with their Process S and Process C values and mapped to the duty and time at which they occur.

> **Regulatory detail** --- including the full text of relevant EASA provisions, worked examples of FDP limit calculations, and guidance on using Aerowake outputs in SMS fatigue reports --- will be covered in the **Regulatory Framework** module.

---

## What Aerowake Analyses

### Input

Aerowake accepts rosters in multiple formats:

- **PDF rosters** --- parsed via the generic PDF roster parser (supports common airline formats)
- **CSV rosters** --- structured tabular input with defined column mappings
- **Qatar Airways CrewLink** --- dedicated parser for the CrewLink roster format
- **Programmatic input** --- direct construction of Duty and Roster objects via the Python API

Each duty consists of one or more flight segments with departure/arrival airports, times, and flight numbers. The tool resolves airport timezones automatically from a database of approximately 7,800 airports.

### Output

For each duty in the roster, Aerowake produces:

- **Performance timeline** at 30-minute resolution, decomposed into Process S, Process C, sleep inertia, and time-on-task contributions
- **Landing performance** --- the predicted cognitive performance score at touchdown, the single most safety-critical metric
- **Minimum performance** --- the lowest score reached during the entire duty
- **Risk classification** with mapped EASA regulatory reference and recommended action
- **WOCL encroachment** --- hours of duty falling within the Window of Circadian Low
- **Pinch events** --- timestamps where homeostatic pressure and circadian trough overlap
- **Sleep debt** --- cumulative debt entering the duty and projected debt after recovery sleep

At the roster level, the tool produces:

- **Monthly analysis summary** with aggregate statistics across all duties
- **Chronogram** --- a high-resolution timeline visualization showing performance, sleep, duty, and circadian state across the full roster period
- **Aviation calendar** --- a monthly calendar view with colour-coded risk levels and multi-day duty rendering

---

## Workload Integration

Not all phases of flight demand the same cognitive load. Aerowake applies a **task-weighted workload model** that adjusts the effective fatigue impact based on flight phase:

| Flight Phase | Relative Workload |
|---|---|
| Landing | Highest |
| Approach, Takeoff | High |
| Climb, Descent | Moderate |
| Cruise | Lower |
| Taxi, Ground | Lowest |

This means the model is most conservative in its predictions for the phases that matter most: approach and landing, where cognitive demand peaks and the consequences of impairment are highest. Landing performance is reported as the primary risk metric precisely because it represents the intersection of accumulated fatigue with peak task demand.

---

## Configuration Profiles

Aerowake provides four configuration profiles that adjust model parameters and risk thresholds for different use cases:

| Profile | Use Case | Key Differences |
|---|---|---|
| **Default EASA** | General-purpose analysis | Balanced parameters from EASA research |
| **Conservative** | Safety advocacy, SMS reports | Faster fatigue buildup, tighter thresholds (+5 points), slower adaptation |
| **Liberal** | Experienced-crew / low-risk routes | Slower buildup, looser thresholds, faster adaptation |
| **Research** | Academic comparison | Pure Borbely parameters (Jewett & Kronauer 1999), no operational adjustments |

All profiles share the same underlying model architecture. The differences are in parameter values (time constants, quality multipliers, risk thresholds), not in methodology.

---

## Architecture

Aerowake is structured in three layers:

```
 Presentation          API & Visualization
                       FastAPI REST endpoints, Chronogram,
                       Aviation Calendar, SMS report generation

 Engine                BorbelyFatigueModel
                       Unified Sleep Calculator (5 strategies),
                       Circadian adaptation tracker,
                       Workload model, EASA compliance validator

 Data                  Roster, Duty, FlightSegment, SleepBlock,
                       DutyTimeline, MonthlyAnalysis, PinchEvent
```

The engine layer (`core/`) contains the fatigue model (`fatigue_model.py`), the sleep estimation system (`sleep_calculator.py`, `sleep_strategies.py`, `sleep_quality.py`), regulatory validation (`compliance.py`), the workload model (`workload.py`) and all tunable parameters with their citations (`parameters.py`). The data layer (`models/data_models.py`) defines typed structures for all domain objects. The presentation layer provides a REST API (`api/api_server.py`) with endpoints for roster upload, analysis retrieval, and visualization generation.

Parser modules (`parsers/roster_parser.py`, `parsers/qatar_crewlink_parser.py`) handle the conversion of airline-specific roster formats into the standardized Duty/Roster structures that the engine consumes.

---

## Intended Use and Limitations

### Aerowake is designed for:

- **Education** --- understanding how fatigue accumulates across rosters and why certain duty patterns are riskier than others
- **Advocacy** --- generating evidence-based fatigue reports for Safety Management System (SMS) submissions
- **Roster comparison** --- objectively comparing two roster options using the same fatigue model
- **Research** --- exploring biomathematical fatigue modelling with transparent, inspectable parameters

### Aerowake is not:

- A certified FRMS (Fatigue Risk Management System)
- A replacement for airline fatigue monitoring programmes
- A tool for operational go/no-go decisions
- Validated against operational in-flight performance data
- A medical fitness assessment

Pilots must always exercise professional judgment per EASA ORO.FTL.120 and comply with their airline's fatigue management policies. Aerowake provides information to support decision-making; it does not make decisions.

---

## What Comes Next

This overview introduces Aerowake's capabilities and the scientific framework on which it operates. The following modules provide detailed treatment of specific domains:

- **Science & Mathematics** --- full derivation of the two-process model equations, parameter sensitivity, and validation methodology
- **Sleep Science** --- sleep estimation strategies, quality modelling, debt dynamics, and comparison to polysomnography data
- **Regulatory Framework** --- EASA ORO.FTL provisions in detail, compliance validation logic, and guidance on SMS reporting
- **User Guide** --- practical instructions for roster upload, analysis interpretation, and report generation

---

## Primary Scientific References

| Domain | Reference |
|---|---|
| Core model | Borbely, A.A. (1982). A two process model of sleep regulation. *Human Neurobiology*, 1(3), 195--204 |
| Model refinement | Borbely, A.A. & Achermann, P. (1999). Sleep homeostasis and models of sleep regulation. *Journal of Biological Rhythms*, 14(6), 559--570 |
| Time constants | Jewett, M.E. & Kronauer, R.E. (1999). Interactive mathematical models of subjective alertness and cognitive throughput. *American Journal of Physiology*, 277, R493--R514 |
| Sleep debt | Van Dongen, H.P.A. et al. (2003). The cumulative cost of additional wakefulness. *Sleep*, 26(2), 117--126 |
| Debt recovery | Belenky, G. et al. (2003). Patterns of performance degradation and restoration during sleep restriction and subsequent recovery. *Journal of Sleep Research*, 12, 1--12 |
| Incomplete recovery | Banks, S. et al. (2010). Neurobehavioral dynamics following chronic sleep restriction. *Sleep*, 33(8), 1013--1026 |
| Recovery timescale | Kitamura, S. et al. (2016). Estimating individual optimal sleep duration and potential sleep debt. *Scientific Reports*, 6, 35812 |
| Workload capacity | Wickens, C.D. (2008). Multiple resources and mental workload. *Human Factors*, 50(3), 449--455 |
| Sleep quality | Signal, T.L. et al. (2013). Sleep duration and quality in healthy volunteers. *Sleep*, 36(1), 109--118 |
| Circadian adaptation | Waterhouse, J. et al. (2007). Jet lag: trends and coping strategies. *Lancet*, 369, 1117--1129 |
| Sleep inertia | Tassi, P. & Muzet, A. (2000). Sleep inertia. *Sleep Medicine Reviews*, 4(4), 341--353 |
| Time-on-task | Folkard, S. & Akerstedt, T. (1999). Trends in the risk of accidents and injuries. *Journal of Biological Rhythms*, 14(6), 577--587 |
| EASA evidence base | Gander, P.H. et al. (2013). Moebus Report: Scientific and medical evaluation of FTL. EASA |
| Aviation fatigue | Bourgeois-Bougrine, S. et al. (2003). Perceived fatigue for short- and long-haul flights. *Aviation, Space, and Environmental Medicine*, 74(11), 1154--1162 |
| Regulatory framework | European Commission (2014). EU Regulation 965/2012, Subpart FTL (ORO.FTL) |
