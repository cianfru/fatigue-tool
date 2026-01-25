# 📅 Aviation Calendar - Integration Complete

The aviation calendar is now integrated into the Streamlit app!

## How to Use

### 1. Upload Your Roster
- Click "Upload Roster" (Step 1)
- Select PDF or CSV file
- Click "Analyze Roster" button

### 2. View Results
- App processes the roster
- Shows summary statistics
- Displays monthly calendar heatmap
- Shows duty-by-duty analysis with performance timelines

### 3. Download Aviation Calendar
- Scroll to **"Step 4: Download Reports"**
- Click **"📥 Download Calendar PNG"** button
- Calendar generates showing:
  - All duties spanning multiple days
  - Route information (DEP → ARR)
  - Report time on first day
  - Landing indicator on last day
  - Risk-based coloring (green/yellow/orange/red)
  - Performance scores
  - Dark/light theme matching your selection

## What the Calendar Shows

### Duty Display
**Report Date** (First day of duty):
- Route: DEP→ARR (e.g., DOH→LHR)
- Report time in local timezone (e.g., 02:30)
- Risk color based on landing performance
- Performance score (e.g., 78/100)

**Middle Dates** (Multi-day duties):
- Continuation bar showing "━━ IN FLIGHT ━━"
- Same risk color for context
- Lighter transparency for intermediate days

**Landing Date** (Last day of duty):
- "⬇ LANDING" indicator
- Risk color consistent with duty
- Shows arrival completion

### OFF Days
- "OFF" label for non-duty days
- Rest opportunity calculation:
  - Shows hours available between previous landing and next report
  - Quality assessment:
    - ✅ **Good** (≥36h): Full recurrent rest
    - ✓ **Adequate** (24-36h): Sufficient rest
    - ⚠️ **Minimal** (12-24h): Limited rest
    - ❌ **Poor** (<12h): Insufficient rest

### Risk Colors
- 🟢 **Green (Low)**: ≥75 performance - Optimal
- 🟡 **Yellow (Moderate)**: 65-74 - Acceptable
- 🟠 **Orange (High)**: 55-64 - Monitor fatigue
- 🔴 **Red (Critical)**: <55 - Intervention needed

## Technical Details

**File Location**: [aviation_calendar.py](aviation_calendar.py)

**Module**: `AviationCalendar` class
- Supports light and dark themes
- Colorblind-friendly color palette
- High-DPI PNG output (150 dpi)
- Professional publication quality

**Integration**: [fatigue_app.py](fatigue_app.py) (lines ~575-605)

**Generated Output**:
- Format: PNG image
- Size: ~20" wide × ~2.5" per week height
- Includes title, legend, and statistics
- Filename: `aviation_calendar_{pilot_id}_{month}.png`

## Example Workflow

```
1. Upload: qatar_roster_feb2026.pdf
   ↓
2. System parses 22 duties, 45 sectors
   ↓
3. Analyze button → runs simulation
   ↓
4. Results show performance scores
   ↓
5. Click "Download Calendar PNG"
   ↓
6. Save: aviation_calendar_P12345_2026-02.png
   ↓
7. Share with crew planning/compliance
```

## Features

✅ Multi-day duties display correctly  
✅ Report and landing dates clearly marked  
✅ Route information (DEP→ARR)  
✅ Time-of-day shown (local timezone)  
✅ Risk-based coloring system  
✅ Performance scores visible  
✅ OFF day rest quality assessment  
✅ Dark/light theme support  
✅ Publication-quality PNG export  
✅ Professional for compliance reports  

## Troubleshooting

**Calendar doesn't generate:**
- Check that duties were parsed correctly (check "Step 3" results)
- Verify flight segments have valid airports
- Look for error message with technical details

**Colors don't match risk:**
- Colors are based on landing performance (0-100 scale)
- Check that performance scores are being calculated
- Verify config parameters are correct

**Text is hard to read:**
- Try switching theme (dark/light) in sidebar
- Download at full resolution (150 dpi)
- Adjust zoom when viewing

## Integration Status

✅ **COMPLETE**
- Aviation calendar fully imported
- Button integrated in UI
- Error handling in place
- Theme support working
- Download functionality ready

**Status**: 🟢 **PRODUCTION READY**

Latest commit: 14021cb "Integrate aviation_calendar into Streamlit app"
