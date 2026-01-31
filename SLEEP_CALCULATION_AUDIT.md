# Sleep Calculation Scientific Audit Report

**Date:** 2026-01-31
**Scope:** Verification of sleep calculation logic, sleep type classifications, and scientific citations in `core_model.py` and `data_models.py` against peer-reviewed literature and official regulatory documents.

---

## Architecture Overview

The tool implements 5 sleep types:

| Type | Trigger Condition | Pattern | Location |
|---|---|---|---|
| Normal | Report 07:00-19:59, no WOCL crossing | 23:00-07:00 (8h) | `core_model.py:792-862` |
| Night Departure | Report ≥20:00 or <04:00 | Morning sleep + 3.5h nap | `core_model.py:599-686` |
| Early Morning | Report <07:00 | 8h ending 1h before duty | `core_model.py:688-739` |
| Anchor/WOCL | Report 07:00-19:59, crosses WOCL, >6h duty | 4.5h ending 1.5h before duty | `core_model.py:741-790` |
| Recovery | Rest days between duties | 23:00-07:00 at 0.95 quality | `core_model.py:1630-1673` |

Sleep quality uses 7 multiplicative factors (`core_model.py:396-501`). The Borbely two-process model integrates Process S (homeostatic), C (circadian), and W (sleep inertia) into a 0-100 performance score (`core_model.py:1086-1240`).

---

## Validated Parameters

| Parameter | Value | Cited Source | Verified Against | Status |
|---|---|---|---|---|
| tau_i (wake buildup) | 18.2h | Jewett & Kronauer (1999) | J. Biol. Rhythms 14:588-597 | **Correct** |
| tau_d (sleep decay) | 4.2h | Jewett & Kronauer (1999) | J. Biol. Rhythms 14:588-597 | **Correct** |
| S_max / S_min | 1.0 / 0.0 | Borbely (1982) | Hum. Neurobiol. 1:195-204 | **Correct** (standard non-dimensional form) |
| Baseline sleep need | 8.0h | Van Dongen et al. (2003) | Sleep 26(2):117-126 | **Correct** |
| Sleep inertia duration | 30 min | Tassi & Muzet (2000) | Sleep Med. Rev. 4(4):341-353 | **Correct** |
| Jet lag adaptation W/E | 1.5 / 1.0 h/day | Waterhouse et al. (2007) | Lancet 369:1117-1129 | **Correct** |
| Circadian acrophase | 17:00 | CBT literature | Wright et al. (2002) | **Approximately correct** (17:00-19:00 range) |
| Anchor sleep concept | 4.5h block | Minors & Waterhouse (1981, 1983) | J. Physiol. 345:1-11 | **Well supported** (≥4h validated) |
| Inflight rest efficiency | 0.70 | Signal et al. (2013) | Sleep 36(1):109-118 | **Correct value** (attribution issue, see below) |

---

## Inconsistent Findings

### HIGH SEVERITY (affects model accuracy or traceability)

#### 1. Sleep Debt Decay Rate Misattributed
- **Code:** `sleep_debt_decay_rate: float = 0.25` (line 96) — comment: "Van Dongen 2003"
- **Finding:** Van Dongen et al. (2003) is an experimental study demonstrating cumulative cognitive deficits from chronic sleep restriction. It does **not** contain a mathematical decay rate constant of 0.25. The paper showed sleep debt accumulates but did not formulate an exponential decay model with a rate parameter. This value may originate from McCauley et al. (2013) or the SAFTE/FAST model.
- **Reference:** Van Dongen et al. (2003), *Sleep* 26(2):117-126

#### 2. 60/40 Homeostatic/Circadian Weighting Not From Cited Source
- **Code:** `weight_homeostatic: float = 0.6`, `weight_circadian: float = 0.4` (lines 86-87); citation at line 1223: "Akerstedt & Folkard (1997), Dawson & Reid (1997)"
- **Finding:** The Akerstedt-Folkard three-process model uses an additive combination of S and C components with their amplitudes determining relative contribution — not a weighted average with explicit 60/40 split. This ratio does not appear in either cited paper. The `research_config` preset (lines 272-273) uses 50/50, implicitly acknowledging this is an operational adjustment.
- **Reference:** Akerstedt & Folkard (1997), *Chronobiology International* 14(2):115-124

#### 3. Effective Circadian Peak Silently Shifted to 16:00
- **Code:** `self.c_amplitude = self.params.circadian_amplitude + 0.05` and `self.c_peak_hour = self.params.circadian_acrophase_hours - 1.0` (lines 1115-1116)
- **Finding:** The configured acrophase of 17:00 is shifted to an effective value of 16:00 without documentation or scientific justification. Literature consensus places peak alertness at ~17:00-19:00 (Wright et al. 2002; forced desynchrony studies). The +0.05 amplitude adjustment is also undocumented.
- **Reference:** Wright, Hull & Czeisler (2002), *Am. J. Physiol. Regul. Integr. Comp. Physiol.* 283(6):R1370-R1377

### MEDIUM SEVERITY (incorrect scientific citations)

#### 4. WOCL Sleep Quality Boost: Wrong Mechanism Cited
- **Code:** Lines 419-421 claim "Dijk & Czeisler (1995), Borbely (1999)" support that "Sleep during WOCL is circadian-aligned → enhanced slow-wave sleep"
- **Finding:** Dijk & Czeisler (1995) showed that slow-wave activity (SWA) has **low-amplitude circadian modulation**. SWA is primarily driven by the homeostatic process (prior wake duration), not circadian phase. The circadian system modulates **sleep consolidation** (fewer awakenings, higher sleep efficiency) and REM sleep. The direction of the boost is correct (WOCL-aligned sleep is better), but the mechanism should be cited as improved sleep consolidation, not enhanced SWS.
- **Reference:** Dijk & Czeisler (1995), *J. Neuroscience* 15(5):3526-3538

#### 5. Inflight Rest 70% Misattributed to NASA
- **Code:** Line 416 comment: "NASA studies show ~70% effectiveness"
- **Finding:** The 70% figure comes from **Signal et al. (2013)**, who measured inflight bunk sleep efficiency at 70% via polysomnography. Rosekind et al. (1994, the "NASA Nap Study") studied 40-minute in-seat rest opportunities and reported performance outcomes (alertness improvement, microsleep elimination), not sleep efficiency percentages.
- **Reference:** Signal et al. (2013), *Sleep* 36(1):109-118; Rosekind et al. (1994), NASA Technical Report 19950006379

#### 6. Roenneberg Citation Oversimplified
- **Code:** Line 342 cites "Roenneberg et al. 2007" for `NORMAL_BEDTIME_HOUR = 23`
- **Finding:** Roenneberg et al. (2007) analyzed >55,000 MCTQ responses to characterize **chronotype distributions**. The average mid-sleep on free days was ~04:00-05:00 AM (implying sleep onset ~midnight-01:00 AM, not 23:00). The 23:00 bedtime is a reasonable workday assumption for airline pilots but the paper is about individual variation in free-day timing, not a prescribed "normal" schedule. A more appropriate citation would be airline-specific studies (e.g., Signal et al. 2009, Gander et al. 2013).
- **Reference:** Roenneberg et al. (2007), *Sleep Medicine Reviews* 11:429-438

### LOW SEVERITY (internal code consistency)

#### 7. WOCL End Time: Dual Definition
- `EASAFatigueFramework` (lines 42-43): `wocl_end_hour=5, wocl_end_minute=59` → **02:00-05:59** (correct per EASA ORO.FTL.105(28))
- `UnifiedSleepCalculator` (line 353): `self.WOCL_END = 6` → used in overlap calculations
- The `_duty_crosses_wocl` check (`hour < 6`) is functionally equivalent to 02:00-05:59 for integer hour comparisons. However, `_calculate_wocl_overlap` uses floating-point hour comparison against 6.0, which would include the 05:59-06:00 minute outside the regulatory WOCL.
- **Reference:** EASA ORO.FTL.105(28); UK CAA Regulatory Library

#### 8. Duplicate Hotel Quality Definitions
- `SleepQualityParameters.quality_hotel_typical = 0.80` (line 109)
- `LOCATION_EFFICIENCY['hotel'] = 0.85` (line 358)
- Two different quality values for "hotel" coexist. The `SleepQualityParameters` class appears unused in actual sleep calculation (which only uses `LOCATION_EFFICIENCY`).

#### 9. Nap Efficiency Multiplier: Engineering Estimate
- **Code:** `base_efficiency *= 0.88` for naps (line 417)
- **Finding:** Dinges et al. (1987) found performance was "primarily a function of total time in bed per 24h regardless of how sleep was divided," suggesting nap sleep is roughly equivalent per hour to anchor sleep. The 12% penalty is an engineering estimate without a specific literature source. Acceptable if documented as an operational assumption.
- **Reference:** Dinges et al. (1987), *Sleep* 10(4):313-329

#### 10. Recovery Sleep 10% Boost: Engineering Estimate
- **Code:** `recovery_boost = 1.10 if hours_since_duty < 3` (line 441)
- **Finding:** SWS rebound after extended wakefulness is well-documented (Borbely 1982), supporting higher recovery efficiency conceptually. However, the specific 10% figure and 3-hour threshold are not from any published study. The magnitude depends on prior sleep debt, duty duration, and circadian timing.

---

## Recommendations

1. **Correct the sleep debt decay rate attribution** — either find the actual source for 0.25 or document it as an operational estimate
2. **Document the 60/40 weighting** as an operational choice rather than attributing it to Akerstedt & Folkard
3. **Add justification for the circadian peak shift** from 17:00 to 16:00, or remove the undocumented adjustment
4. **Fix the WOCL boost comment** — change "enhanced slow-wave sleep" to "improved sleep consolidation and efficiency"
5. **Correct the inflight rest attribution** from "NASA studies" to "Signal et al. (2013)"
6. **Unify the WOCL end definition** — use the `EASAFatigueFramework` values in `UnifiedSleepCalculator`
7. **Remove or unify duplicate hotel quality parameters**
8. **Document engineering estimates** (nap 0.88, recovery 1.10) as operational assumptions rather than implying literature derivation
