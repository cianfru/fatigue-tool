# EASA Compliance - Corrected Implementation

## ✅ What Was Fixed

### **Previously INCORRECT:**
```python
# Old code (WRONG):
minimum_rest_hours = 12.0  # Fixed for all cases
```

### **Now CORRECT:**
```python
# Home base:
minimum_rest = max(previous_duty_duration, 12.0) + local_night_required

# Away from base:
minimum_rest = max(previous_duty_duration, 10.0) + 8h_sleep_opportunity
```

---

## 📋 EASA ORO.FTL.235 Requirements

### **Home Base Rest (ORO.FTL.235(c)(1))**

✅ **Duration:** 
- Minimum = `max(previous duty period, 12 hours)`
- Example: After 14h duty → need 14h rest (not just 12h)

✅ **Local Night:**
- Must include period 22:00-08:00 **in reference time** (home base for acclimatized crew)
- Not just local timezone where you are

✅ **Example:**
```
Duty: 08:00-22:00 DOH (14h)
Rest: 22:00-12:00+1 (14h) ✓ COMPLIANT
  - Duration: 14h ≥ max(14h, 12h) ✓
  - Includes 22:00-08:00 DOH time ✓
```

---

### **Away From Base Rest (ORO.FTL.235(c)(2))**

✅ **Duration:**
- Minimum = `max(previous duty period, 10 hours)`
- Example: After 12h duty → need 12h rest (not just 10h)

✅ **Sleep Opportunity:**
- Must provide at least 8 consecutive hours for sleep
- After accounting for:
  - Travel to/from hotel (~1h)
  - Preparation for next duty (~2h)

✅ **Example:**
```
Duty: 08:00-20:00, land LHR (12h)
Rest: 20:00-08:00+1 (12h) ✓ COMPLIANT
  - Duration: 12h ≥ max(12h, 10h) ✓
  - Sleep opportunity: 12h - 3h overhead = 9h ≥ 8h ✓
```

---

### **Recurrent Rest (ORO.FTL.235(e))**

✅ **Frequency:** At least once every 168 hours (7 days)

✅ **Duration:** Minimum 36 hours

✅ **Local Nights:** Must include 2 local nights
- Definition: Period 00:00-05:00 in reference time
- NOT the same as 22:00-08:00 (that's for minimum rest)

---

## 🆕 FDP Tracking

Now tracks **Flight Duty Period** separately from total duty:

```python
duty.duty_hours  # Total: report to release
duty.fdp_hours   # FDP: report to last landing + 30min
```

**Why it matters:**
- EASA FDP limits (ORO.FTL.205) apply to FDP, not total duty
- Rest calculation uses total duty duration
- Different regulations apply to different periods

---

## 🔍 Test Results

### ✅ Correct Detection Examples:

**Test 1: Home base - insufficient local night**
```
Duty: 8h
Rest: 12h (but doesn't include 22:00-08:00)
Result: ✗ NON-COMPLIANT
Reason: "Home base rest must include local night (22:00-08:00 Asia/Qatar)"
```

**Test 2: Home base - rest shorter than duty**
```
Duty: 14h
Rest: 12h
Result: ✗ NON-COMPLIANT
Reason: "Rest 12.0h < minimum 14.0h (previous duty 14.0h, home base)"
```

**Test 3: Away from base - insufficient sleep opportunity**
```
Duty: 8h
Rest: 10h
Sleep available: 10h - 3h overhead = 7h
Result: ✗ NON-COMPLIANT
Reason: "Away from base rest must provide 8h sleep opportunity (only 7.0h available)"
```

**Test 4: Away from base - rest shorter than duty**
```
Duty: 12h
Rest: 10h
Result: ✗ NON-COMPLIANT
Reason: "Rest 10.0h < minimum 12.0h (previous duty 12.0h, away from base)"
```

---

## 📊 Code Changes Made

### **File: `rest_period_analysis.py`**

1. **Added separate minimums:**
   ```python
   self.minimum_rest_hours_home = 12.0
   self.minimum_rest_hours_away = 10.0
   ```

2. **Added local night definitions:**
   ```python
   # For minimum rest requirement
   self.local_night_start = 22  # 22:00
   self.local_night_end = 8     # 08:00
   
   # For recurrent rest (different!)
   self.recurrent_night_start = 0   # 00:00
   self.recurrent_night_end = 5     # 05:00
   ```

3. **Rewrote `_check_easa_compliance()`:**
   - Takes previous duty duration as parameter
   - Checks home base vs away from base
   - Calculates: `max(previous_duty, base_minimum)`
   - Verifies local night (home) or sleep opportunity (away)

4. **Added helper methods:**
   - `_check_local_night_requirement()` - Verifies 22:00-08:00 in reference timezone
   - `_count_local_nights()` - Counts 00:00-05:00 periods for recurrent rest

### **File: `data_models.py`**

1. **Added FDP tracking to Duty class:**
   ```python
   @property
   def fdp_hours(self) -> float:
       """FDP = Report to last landing + 30min"""
       fdp_end = self.segments[-1].scheduled_arrival_utc + timedelta(minutes=30)
       return (fdp_end - self.report_time_utc).total_seconds() / 3600
   ```

---

## ✅ Verification

Run the test suite:
```bash
python test_easa_compliance.py
```

All scenarios now correctly identify EASA compliance/violations per ORO.FTL.235.

---

## 🎯 Key Takeaways

1. **Home ≠ Away:** Different minimums (12h vs 10h)
2. **Duty Matters:** Minimum rest = `max(duty, base_minimum)`
3. **Local Night:** Required at home base (22:00-08:00 reference time)
4. **Sleep Opportunity:** Required away from base (8h after overhead)
5. **Reference Time:** Use home base time for acclimatized crew
6. **FDP ≠ Duty:** Track both separately

**The system now correctly implements EASA ORO.FTL.235!** ✅
