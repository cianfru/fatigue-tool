# 🚀 Web App Deployment Guide

## Quick Start - Deploy in 5 Minutes

Your Streamlit app is ready to deploy! Choose your platform:

---

## Option 1: Streamlit Cloud (⭐ RECOMMENDED - FREE)

### Requirements
- GitHub account
- Push code to GitHub

### Steps

1. **Initialize Git & Push to GitHub**
   ```bash
   cd fatigue_tool
   git init
   git add .
   git commit -m "Initial commit: EASA Fatigue Analysis Tool"
   git remote add origin https://github.com/YOUR_USERNAME/fatigue-tool.git
   git branch -M main
   git push -u origin main
   ```

2. **Deploy on Streamlit Cloud**
   - Go to https://streamlit.io/cloud
   - Click "New app"
   - Select your GitHub repo
   - Branch: `main`
   - Main file path: `fatigue_app.py`
   - Click "Deploy"

3. **Your app will be live at**
   ```
   https://fatigue-tool.streamlit.app/
   ```

**Time to deploy:** ~2 minutes
**Cost:** FREE (includes 1 concurrent app)

---

## Option 2: Heroku (ALTERNATIVE)

### Requirements
- Heroku account
- Heroku CLI

### Steps

1. **Create Procfile**
   ```bash
   echo "web: streamlit run fatigue_app.py --logger.level=error" > Procfile
   ```

2. **Create `.streamlit/config.toml`** (already done)

3. **Deploy**
   ```bash
   heroku create your-app-name
   git push heroku main
   ```

**Time to deploy:** ~5 minutes
**Cost:** Free tier available (sleeps after 30 mins idle)

---

## Option 3: PythonAnywhere (EASIEST FOR BEGINNERS)

1. Upload code to pythonanywhere.com
2. Configure web app settings
3. Reload

**Time to deploy:** ~5 minutes
**Cost:** $5/month

---

## Testing Locally Before Deploy

```bash
# Test the app locally first
streamlit run fatigue_app.py
```

Then visit: http://localhost:8501

---

## What Users Get

### Features
✅ Upload roster (PDF/CSV)
✅ Analyze fatigue risk for entire month
✅ View individual duty analysis
✅ Interactive risk dashboard
✅ Download PDF reports
✅ Compare different configurations

### Supported Inputs
- Qatar Airways CrewLink PDF rosters
- Generic CSV format
- Manual duty entry

### Output
- Risk classification (Low/Moderate/High/Critical/Extreme)
- Performance predictions (0-100 scale)
- Pinch event detection
- EASA regulatory compliance
- SMS reportability flags

---

## Post-Deployment Checklist

- [ ] App loads without errors
- [ ] Can upload roster
- [ ] Analysis runs successfully
- [ ] Results display correctly
- [ ] Download PDF report works
- [ ] Mobile responsive (test on phone)
- [ ] Share URL with friends/colleagues

---

## Troubleshooting

### "ModuleNotFoundError"
Make sure `requirements.txt` includes all imports

### "Streamlit not found"
Ensure `requirements.txt` is in root directory

### "Port already in use"
```bash
streamlit run fatigue_app.py --server.port 8502
```

### PDF upload fails
- Check file size (max 200MB on Streamlit Cloud)
- Ensure PDF format is supported by tabula-py

---

## Next Steps

1. ✅ Deploy the app (follow Option 1 above)
2. 📝 Test with your real roster
3. 📢 Share the link with colleagues
4. 💾 Collect feedback
5. 🔄 Iterate on features

---

**Questions?** Check the main README.md or PROJECT_OVERVIEW.md

**Ready to deploy?** Go to https://streamlit.io/cloud and deploy!
