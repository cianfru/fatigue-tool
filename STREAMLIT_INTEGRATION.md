# Streamlit Integration Guide - V2 Pro

## What Changed?

The fatigue_app.py now uses **interactive Plotly visualizations** instead of static matplotlib PNG images.

### Key Upgrades:

✅ **Live Interactive Charts**
- Hover tooltips showing flight number, performance %, sleep debt
- Zoom & pan capabilities
- Download chart as PNG directly from browser

✅ **Three-Component Visualization**
- Stacked area showing Sleep Pressure (S), Circadian (C), and Sleep Inertia (W)
- Neon cyan performance line overlay
- Risk threshold bands (critical/high/moderate/low) as background colors

✅ **WOCL Compliance Highlighting**
- Purple shaded areas show Window of Circadian Low (02:00-06:00)
- EASA ORO.FTL.105 compliance focus

✅ **Route Network Map**
- Geographic visualization of all flights
- Risk-based coloring (red = critical, orange = high, etc.)
- Opacity filtering for selected duties

✅ **Professional Aesthetics**
- Dark/light theme auto-sync with Streamlit
- Transparent backgrounds integrate seamlessly
- Okabe & Ito colorblind-friendly palette

---

## How to Run

### 1. Install Dependencies

```bash
pip install plotly streamlit pandas pytz
```

### 2. Start the App

```bash
cd /Users/andreacianfruglia/Desktop/fatigue_tool_CORRECTED
streamlit run fatigue_app.py
```

The app will open at: **http://localhost:8501**

### 3. Upload Your Roster

1. Select **Home Base** (DOH, LHR, JFK, DXB, etc.)
2. Upload a **PDF or CSV roster**
3. Click **"Analyze"**
4. Results will show interactive charts

---

## New Features in the UI

### Duty-by-Duty Analysis Tab

Each duty now shows:
- **Interactive Timeline Chart** with S/C/W stacking
- Hover over any point to see:
  - Performance percentage
  - Flight number
  - Sleep debt accumulation
- Risk bands highlight critical periods
- WOCL shading shows circadian low window

### Route Network Map

- **🌍 Full geographic map** showing all route segments
- **Color-coded by risk** (red=critical → green=safe)
- **Interactive selection** (hover for flight details)

### Monthly Summary

- **Bar chart** with duty performance
- **Marker overlay** for landing performance
- **Reference lines** for risk thresholds
- **Color-coded** by risk classification

---

## What the Visualizer Returns

### New Methods (V2 Pro)

```python
# Create interactive duty timeline
fig = visualizer.create_unified_timeline(duty_timeline)
st.plotly_chart(fig, use_container_width=True)

# Create route map
fig = visualizer.create_route_map(monthly_analysis)
st.plotly_chart(fig, use_container_width=True)

# Create monthly summary
fig = visualizer.plot_monthly_summary(monthly_analysis)
st.plotly_chart(fig, use_container_width=True)

# Create component breakdown
fig = visualizer.plot_component_breakdown(duty_timeline)
st.plotly_chart(fig, use_container_width=True)
```

---

## Backward Compatibility

Old matplotlib methods still work for PNG export:

```python
visualizer.plot_duty_timeline(duty, save_path="duty.html")  # Saves HTML
visualizer.plot_monthly_summary(analysis, save_path="monthly.html")  # Saves HTML
```

---

## Performance Notes

✅ **Faster Rendering**
- Plotly interactive charts load instantly
- No temporary file creation needed
- No image re-rendering on zoom/pan

✅ **Responsive Design**
- Charts scale to container width
- Mobile-friendly (works on tablets)
- Touch-friendly tooltips

---

## Troubleshooting

**Q: Charts not showing?**
- Ensure you installed plotly: `pip install plotly`
- Check browser console for errors (F12)
- Try reloading: `streamlit run fatigue_app.py`

**Q: Route map blank?**
- Verify segment coordinates exist in duty data
- Check airport database has lat/lon values

**Q: Tooltips not showing?**
- Hover over the chart, not the axis
- Check that PerformancePoint objects have flight_no and sleep_debt attributes

---

## Next Steps

1. ✅ Upload a test roster
2. ✅ Verify interactive charts render
3. ✅ Click & hover to explore data
4. ✅ Download charts as PNG (top-right of each Plotly chart)
5. ✅ Export analysis results

---

**Questions?** Check the git log for implementation details:
```bash
git log --oneline | head -5
```
