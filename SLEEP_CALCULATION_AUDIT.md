# Sleep Calculation Scientific Audit Report

**Date:** 2026-02-01 (updated)
**Scope:** Verification of sleep calculation logic, sleep type classifications, and scientific citations in `core_model.py` and `data_models.py` against peer-reviewed literature and official regulatory documents.

---

## Architecture Overview

The tool implements 5 sleep strategies:

| Type | Trigger Condition | Pattern | Location |
|---|---|---|---|
| Normal | Report 07:00-19:59, no WOCL crossing | 23:00-07:00 (8h) | `core_model.py:~810-880` |
| Night Departure | Report ≥20:00 or <04:00 | Morning sleep + **2h** pre-duty nap | `core_model.py:~599-700` |
| Early Morning | Report <07:00 | **Roach regression** (4-6.6h), earliest bedtime 21:30 | `core_model.py:~688-760` |
| Anchor/WOCL | Report 07:00-19:59, crosses WOCL, >6h duty | 4.5h ending 1.5h before duty | `core_model.py:~763-810` |
| Recovery | Rest days between duties | 23:00-07:00 at 0.95 quality | `core_model.py:~1690-1740` |

Sleep quality uses 7 multiplicative factors. The Borbely two-process model integrates Process S (homeostatic), C (circadian), and W (sleep inertia) into a 0-100 performance score.

---

## Validated Parameters

| Parameter | Value | Cited Source | Verified Against | Status |
|---|---|---|---|---|
| tau_i (wake buildup) | 18.2h | Jewett & Kronauer (1999) | J. Biol. Rhythms 14:588-597 | **Correct** |
| tau_d (sleep decay) | 4.2h | Jewett & Kronauer (1999) | J. Biol. Rhythms 14:588-597 | **Correct** |
| S_max / S_min | 1.0 / 0.0 | Borbely (1982) | Hum. Neurobiol. 1:195-204 | **Correct** |
| Baseline sleep need | 8.0h | Van Dongen et al. (2003) | Sleep 26(2):117-126 | **Correct** |
| Sleep inertia duration | 30 min | Tassi & Muzet (2000) | Sleep Med. Rev. 4(4):341-353 | **Correct** |
| Jet lag adaptation W/E | 1.5 / 1.0 h/day | Waterhouse et al. (2007) | Lancet 369:1117-1129 | **Correct** |
| Circadian acrophase | 17:00 | CBT literature | Wright et al. (2002) | **Approximately correct** (17:00-19:00 range) |
| Anchor sleep concept | 4.5h block | Minors & Waterhouse (1981, 1983) | J. Physiol. 345:1-11 | **Well supported** (≥4h validated) |
| Inflight rest efficiency | 0.70 | Signal et al. (2013) | Sleep 36(1):109-118 | **Correct** |

---

## Issues Found and Resolutions

### 1. Early Morning Strategy Overestimated Sleep by 2-3 Hours [FIXED]

**Problem:** The original code assumed 8h sleep ending 1h before report, regardless of report time. Actigraphy data shows pilots cannot advance bedtime sufficiently due to the circadian wake maintenance zone.

**Evidence:**
- Roach et al. (2012) *Accid Anal Prev* 45 Suppl:22-26 — pilots lose ~15 min sleep per hour of duty advance before 09:00. Duty start 04:00-05:00 yields only 5.4h sleep.
- Arsintescu et al. (2022) *J Sleep Res* 31(3):e13521 — pilots do not sufficiently advance bedtime for early starts.

**Fix applied:** Replaced fixed 8h with Roach (2012) regression:
```
sleep_hours = max(4.0, 6.6 - 0.25 * max(0, 9.0 - report_hour))
```
Added earliest realistic bedtime of 21:30 (circadian opposition). Confidence reduced from 0.60 to 0.55.

### 2. Night Departure Nap Too Long [FIXED]

**Problem:** 3.5h "nap" exceeded typical pre-flight nap durations; morning sleep window extended to 08:00 (9h).

**Evidence:**
- Signal et al. (2014) *Aviat Space Environ Med* 85:1199-1208 — only 54% of crew napped before evening departures; typical nap duration 1-2h.
- Gander et al. (2014) *Aviat Space Environ Med* 85(8):833-40 — total pre-trip sleep ~7.8h including naps.

**Fix applied:** Reduced nap from 3.5h to 2.0h. Morning sleep end changed from 08:00 to 07:00. Confidence reduced from 0.70 to 0.60 (reflecting 54% nap uptake).

### 3. WOCL Boost Cited Wrong Mechanism [FIXED]

**Problem:** Comment claimed "enhanced slow-wave sleep" during WOCL.

**Evidence:** Dijk & Czeisler (1995) *J. Neuroscience* 15(5):3526-3538 showed SWA is primarily homeostatic, not circadian. The circadian system modulates sleep consolidation (fewer awakenings, higher efficiency) and REM sleep.

**Fix applied:** Changed comment to "improved sleep consolidation" with clarifying note.

### 4. Inflight Rest 70% Misattributed to NASA [FIXED]

**Problem:** Code comment said "NASA studies show ~70% effectiveness."

**Evidence:** The 70% figure comes from Signal et al. (2013) *Sleep* 36(1):109-118 (PSG-measured). Rosekind et al. (1994, NASA) studied 40-minute in-seat naps and reported performance outcomes, not sleep efficiency percentages.

**Fix applied:** Attribution corrected to Signal et al. (2013) in both `data_models.py` and `core_model.py`.

### 5. Roenneberg Citation Oversimplified [FIXED]

**Problem:** Cited "Roenneberg et al. 2007" for a single fixed 23:00 bedtime. The paper characterises chronotype distributions (avg free-day mid-sleep ~04:00-05:00), not a prescribed schedule.

**Fix applied:** Expanded comment to explain that 23:00 reflects alarm-constrained workday timing for pilots, with Signal et al. (2009) and Gander et al. (2013) as more appropriate aviation-specific references.

### 6. WOCL_END Dual Definition [FIXED]

**Problem:** `EASAFatigueFramework.wocl_end_hour=5` (correct, 02:00-05:59) vs `UnifiedSleepCalculator.WOCL_END=6` (hardcoded).

**Fix applied:** `UnifiedSleepCalculator` now derives WOCL boundaries from `EASAFatigueFramework` values. Documented that WOCL_END=6 is the exclusive upper bound (i.e., `hour < 6` = 02:00-05:59).

### 7. Sleep Debt Decay Rate Misattributed [FIXED]

**Problem:** `sleep_debt_decay_rate: float = 0.25` attributed to "Van Dongen 2003." That paper demonstrated cumulative deficits but did not specify an exponential decay constant.

**Fix applied:** Comment updated to document this as an operational estimate, noting possible origin in SAFTE/FAST model family (Hursh et al. 2004). Van Dongen (2003) retained for baseline sleep need only.

### 8. 60/40 Homeostatic/Circadian Weighting [FIXED]

**Problem:** Attributed to Åkerstedt & Folkard (1997), who use additive S+C combination, not a weighted average.

**Fix applied:** Documented as "operational adaptation, not directly from the literature." Performance integration docstring updated.

### 9. Circadian Peak Shift Undocumented [FIXED]

**Problem:** Code silently shifted acrophase from 17:00 to 16:00 and increased amplitude by 0.05, with no comment explaining why.

**Fix applied:** Added documentation explaining these are operational choices for aviation context. Referenced Wright et al. (2002) *Am. J. Physiol.* 283:R1370 for CBT acrophase context.

### 10. Duplicate Hotel Quality Definitions [FIXED]

**Problem:** `SleepQualityParameters.quality_hotel_typical=0.80` vs `LOCATION_EFFICIENCY['hotel']=0.85`.

**Fix applied:** Aligned `SleepQualityParameters` to Signal et al. (2013) PSG data: hotel quiet=0.88, typical=0.85, airport=0.82, crew rest=0.70. `LOCATION_EFFICIENCY['crew_rest']` corrected from 0.88 to 0.70 to match Signal et al. (2013).

### 11. Nap Efficiency and Recovery Boost Documented [FIXED]

**Problem:** Nap 0.88 multiplier and recovery 1.10 boost presented without noting they are engineering estimates.

**Evidence:**
- Dinges et al. (1987) *Sleep* 10:313-329 — found total sleep quantity matters more than division; nap sleep roughly equivalent per hour.
- Borbely (1982) — SWS rebound after extended wakefulness is well-documented, but no specific boost percentage published.

**Fix applied:** Both values documented as "operational estimates / modelling choices" in code comments, with relevant literature context.

### 12. WOCL Boost Inflated Effective Sleep — Double-counted Nighttime Advantage [FIXED]

**Problem:** A 3%/h WOCL overlap boost (capped at 15%) was applied ON TOP of `LOCATION_EFFICIENCY` values that already assume normal nighttime sleep. Normal home sleep: 0.90 × 1.15 = 1.035, clamped to 1.0 — making all nighttime home sleep "perfect."

**Evidence:**
- Dijk & Czeisler (1995) *J Neurosci* 15:3526 — SWA is primarily homeostatic; circadian modulation of SWS amplitude is low.
- Dijk & Czeisler (1994) *J Neurosci* 14:3522 — sleep consolidation is circadian: ~95% efficiency during biological night vs 80-85% during circadian day.

**Fix applied:** Replaced boost with circadian misalignment *penalty* — sleep outside the WOCL window is penalized up to 15% (fully daytime sleep), while WOCL-aligned sleep gets no modifier (it IS the baseline).

### 13. Recovery Boost Too High and Not Graded [FIXED]

**Problem:** Flat 10% boost for any sleep starting <3h after duty end. Not from a published value.

**Fix applied:** Graded: 5% if <2h post-duty, 3% if <4h, 0% otherwise. Capped to prevent combined efficiency exceeding 1.0.

### 14. Time Pressure Factor Bonus Inflated Quality [FIXED]

**Problem:** `time_pressure_factor = 1.03` for >6h until duty acted as a bonus, pushing combined efficiency above 1.0 before clamping.

**Fix applied:** Changed to 1.0 (neutral) for ≥6h. Penalties for imminent duty retained. Reference added: Kecklund & Åkerstedt (2004) *J Sleep Res* 13:1-6.

### 15. Pre-Duty Wakefulness Ignored in simulate_duty [FIXED]

**Problem:** `effective_wake_hours` started at 0.0 at duty report, regardless of how long the pilot had been awake. A pilot awake for 4h before report had the same homeostatic pressure as one who just woke up.

**Evidence:**
- Dawson & Reid (1997) *Nature* 388:235 — 17h awake ≈ 0.05% BAC equivalent. Pre-duty wake hours are critical.

**Fix applied:** `effective_wake_hours` now initializes with `(report_time - wake_time)`. Process S at duty start reflects actual time since last sleep.

### 16. Time-on-Task Linear Decrement Missing [FIXED]

**Problem:** No separate time-on-duty performance penalty. The model only had exponential homeostatic buildup, which saturates. Folkard & Åkerstedt (1999) identified a linear "time on shift" effect independent of S and C.

**Evidence:**
- Folkard et al. (1999) *J Biol Rhythms* 14(6):577-587 — ~0.7%/h decline in subjective alertness across 12-h shifts.

**Fix applied:** Added `time_on_task_rate = 0.008/h` (0.64%/h on the 20-100 scale) as a linear decrement in `integrate_performance()`, independent of homeostatic and circadian components.

### 17. Sleep Debt Accumulation Model: Three Compounding Bugs [FIXED]

**Problem:** Sleep debt accumulated to 31.6 h over a month with only ~15% recovery/day, producing unrealistic runaway debt. Three bugs compounded:
1. **Phantom rest-day debt**: effective_sleep_hours (7.6 h = 8 h × 0.95 quality) was compared against 8 h need, so every rest day *added* 0.4 h of debt instead of recovering.
2. **Double quality penalty**: quality factors reduced effective sleep for BOTH Process S recovery AND the debt model. Process S already degrades performance for poor-quality sleep — penalising debt as well double-counts.
3. **Unscaled multi-day need**: a multi-day rest gap compared total sleep against a flat 8 h need instead of 8 h × N days.
4. **Decay rate too slow**: 0.25/day (22 %/day) understated recovery vs. empirical data.

**Fix applied:**
- Debt now uses `duration_hours` (raw time asleep) instead of `effective_sleep_hours`.
- Period need scales with `days_since_last` (8 h × N days).
- Surplus sleep actively reduces existing debt 1:1.
- Decay rate increased to 0.50/day (half-life ≈ 1.4 d), calibrated against:
  - Kitamura et al. (2016): 1 h debt ≈ 4 d to fully recover → exp(-0.5×4) = 0.14 (86 % in 4 d)
  - Belenky et al. (2003): 3 × 8 h recovery nights incomplete → exp(-0.5×3) = 0.22 (78 % in 3 d)

---

## Remaining Known Gaps

These are not inconsistencies but **missing features** identified during the audit:

| Gap | Literature Support | Priority |
|---|---|---|
| **Layover/hotel sleep** (different TZ) | Signal et al. (2013): 88% efficiency, 7.2h/24h; timezone-dependent | High |
| **In-flight crew rest** strategy generation | Signal et al. (2013): 70% efficiency, 3.3-4.3h in bunk | High |
| **Split duty rest** | EASA-defined pattern, distinct from anchor sleep | Medium |
| **Post-flight recovery nap** | Documented in Signal (2014), UPS accident investigation | Low |
| **Chronotype variation** | Juda, Vetter & Roenneberg (2013) J Biol Rhythms 28:267-276 | Low |

---

## Full Reference List

1. Åkerstedt T (2003). Shift work and disturbed sleep/wakefulness. *Occup Med* 53:89-94.
2. Åkerstedt T & Folkard S (1997). The three-process model of alertness and its extension to performance. *Chronobiol Int* 14(2):115-124.
3. Arsintescu L et al. (2022). Early starts and late finishes both reduce alertness and performance. *J Sleep Res* 31(3):e13521.
4. Borbely AA (1982). A two process model of sleep regulation. *Hum Neurobiol* 1:195-204.
5. Borbely AA & Achermann P (1999). Sleep homeostasis and models of sleep regulation. *J Biol Rhythms* 14:557-568.
6. Belenky G et al. (2003). Patterns of performance degradation and restoration during sleep restriction and subsequent recovery: a sleep dose-response study. *J Sleep Res* 12:1-12.
7. Bourgeois-Bougrine S et al. (2003). Perceived fatigue for short- and long-haul flights. *Aviat Space Environ Med* 74(10):1072-1077.
8. Dawson D & Reid K (1997). Fatigue, alcohol and performance impairment. *Nature* 388:235.
8. Dijk DJ & Czeisler CA (1994). Direct evidence for independent circadian and sleep-dependent regulation. *J Neurosci* 14:3522-3530.
9. Dijk DJ & Czeisler CA (1995). Contribution of the circadian pacemaker and the sleep homeostat to sleep propensity, sleep structure, EEG slow waves, and spindle activity. *J Neurosci* 15(5):3526-3538.
9. Dinges DF et al. (1987). Temporal placement of a nap for alertness. *Sleep* 10(4):313-329.
10. Gander PH et al. (2013). In-flight sleep, pilot fatigue and PVT performance. *J Sleep Res* 22(6):697-706.
11. Gander PH et al. (2014). Pilot fatigue: relationships with departure and arrival times. *Aviat Space Environ Med* 85(8):833-40.
12. Folkard S, Åkerstedt T, Macdonald I, Tucker P & Spencer MB (1999). Beyond the three-process model of alertness: estimating phase, time on shift, and successive night effects. *J Biol Rhythms* 14(6):577-587.
13. Hursh SR et al. (2004). Fatigue models for applied research in warfighting. *Aviat Space Environ Med* 75(3 Suppl):A44-53.
14. Kecklund G & Åkerstedt T (2004). Apprehension of the subsequent working day is associated with a low amount of slow wave sleep. *J Sleep Res* 13:1-6.
15. Kitamura S et al. (2016). Estimating individual optimal sleep duration and potential sleep debt. *Sci Rep* 6:35812.
16. Jewett ME & Kronauer RE (1999). Interactive mathematical models of subjective alertness and cognitive throughput. *J Biol Rhythms* 14:588-597.
14. Juda M, Vetter C & Roenneberg T (2013). Chronotype modulates sleep duration, sleep quality, and social jet lag in shift-workers. *J Biol Rhythms* 28:267-276.
15. Minors DS & Waterhouse JM (1981). Anchor sleep as a synchronizer. *Int J Chronobiol* 8:165-88.
16. Minors DS & Waterhouse JM (1983). Does 'anchor sleep' entrain circadian rhythms? *J Physiol* 345:1-11.
17. Roach GD et al. (2012). Duty periods with early start times restrict sleep. *Accid Anal Prev* 45 Suppl:22-26.
18. Roenneberg T et al. (2007). Epidemiology of the human circadian clock. *Sleep Med Rev* 11:429-438.
19. Rosekind MR et al. (1994). Alertness management: strategic naps in operational settings. *J Sleep Res* 3:62-66; NASA Technical Report 19950006379.
20. Signal TL et al. (2013). In-flight sleep of flight crew during a 7-hour rest break. *Sleep* 36(1):109-118.
21. Signal TL et al. (2014). Mitigating and monitoring flight crew fatigue on ULR flights. *Aviat Space Environ Med* 85:1199-1208.
22. Tassi P & Muzet A (2000). Sleep inertia. *Sleep Med Rev* 4(4):341-353.
23. Van Dongen HP et al. (2003). The cumulative cost of additional wakefulness. *Sleep* 26(2):117-126.
24. Waterhouse J et al. (2007). Jet lag: trends and coping strategies. *Lancet* 369:1117-1129.
25. Wright KP, Hull JT & Czeisler CA (2002). Relationship between alertness, performance, and body temperature. *Am J Physiol* 283:R1370-R1377.
