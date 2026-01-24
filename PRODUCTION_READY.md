# 🚀 EASA Fatigue Tool - Production Deployment

## ⚡ Quick Start (5 Minutes to Live)

```bash
# Step 1: Run the production launcher
python3 launch_production.py

# Or for Streamlit Cloud, follow the prompts to:
# - Push code to GitHub
# - Deploy on Streamlit Cloud
# - Get your live URL
```

Your web app will be live at: **`https://yourname-fatigue-tool.streamlit.app`**

---

## 📦 What You're Deploying

### Working Product Features
✅ **Roster Analysis** - Upload PDF/CSV rosters, analyze entire months
✅ **Risk Dashboard** - Interactive duty-by-duty fatigue risk assessment  
✅ **PDF Reports** - Download detailed fatigue analysis reports
✅ **EASA Compliance** - Regulatory references and SMS evidence
✅ **Pinch Detection** - Identifies dangerous fatigue-circadian combinations
✅ **Model Flexibility** - Test with 4 different model configurations

### User Inputs
- Qatar Airways CrewLink PDFs
- Generic CSV rosters
- Manual duty entry
- Custom airport/timezone data

### Output
- Risk classification (Low/Moderate/High/Critical/Extreme)
- Performance metrics (0-100 scale)
- Sleep debt predictions
- WOCL encroachment tracking
- SMS report templates

---

## 🎯 Deployment Options

### Option 1: Streamlit Cloud (⭐ RECOMMENDED)
**Best for:** First-time deployment, no technical setup

**Steps:**
1. Create GitHub account (free)
2. Push code to GitHub
3. Go to https://streamlit.io/cloud
4. Click "New app" and connect your repo
5. Done! ✅

**Pros:** FREE, 0 setup, custom domain, auto-updates
**Time:** ~5 minutes
**Cost:** $0

---

### Option 2: Heroku
**Best for:** Full control, more configuration

**Steps:**
1. Create Heroku account
2. Install Heroku CLI
3. `heroku login && heroku create yourapp && git push heroku main`
4. Done! ✅

**Pros:** Simple, familiar to developers
**Time:** ~10 minutes  
**Cost:** Free tier (sleeps) or $7/month

---

### Option 3: Custom Server
**Best for:** Production scaling, private deployment

Deploy on your own VPS/server with:
- Nginx reverse proxy
- SSL certificates
- Process manager (Gunicorn)
- Database integration

See server-deployment guides for details.

---

## 📋 Files in This Directory

```
fatigue_tool/
├── 🎯 LAUNCH HERE:
│   └── launch_production.py        ← Run this to deploy
│
├── 📱 WEB APP:
│   └── fatigue_app.py              ← The Streamlit app
│
├── 🔧 CORE ENGINE:
│   ├── core_model.py               ← Borbély model
│   ├── easa_utils.py               ← Risk scoring
│   ├── config.py                   ← Model parameters
│   ├── data_models.py              ← Data structures
│   └── roster_parser.py            ← PDF/CSV parsing
│
├── 🎨 VISUALIZATION:
│   └── visualization.py            ← Charts & graphs
│
├── 🚀 DEPLOYMENT:
│   ├── DEPLOYMENT.md               ← Full deployment guide
│   ├── Procfile                    ← For Heroku
│   ├── .streamlit/config.toml      ← Streamlit settings
│   ├── requirements.txt            ← Python dependencies
│   └── .gitignore                  ← Git settings
│
└── 📚 DOCUMENTATION:
    ├── README.md                   ← Usage guide
    ├── PROJECT_OVERVIEW.md         ← System overview
    └── SETUP.md                    ← Detailed setup
```

---

## ✅ Pre-Deployment Checklist

- [ ] `requirements.txt` includes all packages
- [ ] `fatigue_app.py` runs locally: `streamlit run fatigue_app.py`
- [ ] `.streamlit/config.toml` is configured
- [ ] `Procfile` is present (for Heroku)
- [ ] `.gitignore` is configured
- [ ] All Python imports resolve without errors
- [ ] Testing on local machine successful

---

## 🧪 Test Locally First

```bash
# Install dependencies
pip3 install -r requirements.txt

# Run test
python3 simple_example.py

# Start web app
streamlit run fatigue_app.py
```

Visit: http://localhost:8501

---

## 🔑 How to Deploy (Step-by-Step)

### For Streamlit Cloud (Easiest):

```bash
# 1. Initialize Git
cd /Users/andreacianfruglia/Desktop/fatigue_tool\ 2
git init
git add .
git commit -m "Production ready: EASA Fatigue Analysis Tool"

# 2. Create GitHub repo and push
git remote add origin https://github.com/YOUR_USERNAME/fatigue-tool.git
git branch -M main
git push -u origin main

# 3. Go to https://streamlit.io/cloud
# - Click "New app"
# - Select your repo
# - Select "fatigue_app.py"
# - Click "Deploy"
```

### For Heroku:

```bash
# 1. Login to Heroku
heroku login

# 2. Create app
heroku create your-app-name

# 3. Deploy
git push heroku main

# 4. View logs
heroku logs --tail
```

---

## 📊 Using Your Live App

Once deployed, users can:

1. **Upload Roster**
   - PDF (Qatar Airways CrewLink format)
   - CSV with flights and times

2. **Select Options**
   - Home base airport
   - Analysis month
   - Model configuration
   - Pilot ID for records

3. **View Results**
   - Risk dashboard (color-coded duties)
   - Detailed duty analysis
   - Pinch event warnings
   - EASA compliance summary

4. **Download Reports**
   - PDF with all analysis
   - SMS evidence templates
   - Monthly summary

---

## 🔒 Security Notes

Your app is deployed with:
- ✅ HTTPS/SSL encryption (automatic)
- ✅ No data stored (Streamlit Cloud)
- ✅ Input validation on all rosters
- ✅ Rate limiting available
- ⚠️  No login required (public access)

**For private deployment:**
- Add authentication via Streamlit secrets
- Deploy on private server
- Use password protection

---

## 📈 Post-Deployment

### Monitoring
- Check server logs regularly
- Monitor uptime (Streamlit Cloud is 99.9%)
- Track usage metrics

### Improvements
- Collect user feedback
- Add PDF export improvements
- Integrate with crew scheduling systems
- Add database for historical tracking

### Scaling
- Move to paid Heroku or AWS for high traffic
- Add caching for faster reloads
- Optimize PDF parsing for large rosters

---

## 🆘 Troubleshooting

### App won't start locally
```bash
# Check Python version
python3 --version  # Should be 3.8+

# Reinstall dependencies
pip3 install --upgrade -r requirements.txt

# Test imports
python3 -c "import streamlit; print('OK')"
```

### Module not found error
```bash
# Make sure requirements.txt is complete
pip3 install -r requirements.txt

# Check current packages
pip3 list
```

### Upload fails
- Check PDF format compatibility
- Ensure file size < 200MB
- Verify PDF isn't password protected

### Performance slow
- Streamlit Cloud has modest specs
- Upgrade to paid tier if needed
- Optimize PDF parsing

---

## 📞 Support

For issues:
1. Check DEPLOYMENT.md for detailed guide
2. See README.md for feature usage
3. Review PROJECT_OVERVIEW.md for system overview
4. Check Streamlit docs: https://docs.streamlit.io

---

## 🎉 You're Ready!

Your production web app is ready to launch. Follow the deployment steps above and you'll have a live fatigue analysis tool accessible to your colleagues worldwide.

**Questions?** Check the documentation files or modify `launch_production.py` for your specific needs.

---

**Last Updated:** 24 gennaio 2026
**Status:** ✅ Production Ready
