#!/usr/bin/env python3
"""
=============================================================================
EASA FATIGUE ANALYSIS TOOL - PRODUCTION STARTUP GUIDE
=============================================================================

This script guides you through deploying your web app in 5 minutes.
"""

import os
import sys
import subprocess
import webbrowser
from pathlib import Path

def print_header(text):
    print("\n" + "="*70)
    print(f"  {text}")
    print("="*70 + "\n")

def print_section(text):
    print(f"\n{'='*70}")
    print(f"  {text}")
    print(f"{'='*70}\n")

def run_command(cmd, description):
    """Run a shell command and report status"""
    print(f"Running: {description}")
    try:
        result = subprocess.run(cmd, shell=True, cwd=str(Path(__file__).parent))
        return result.returncode == 0
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def option_1_streamlit_cloud():
    """Deploy to Streamlit Cloud"""
    print_section("OPTION 1: STREAMLIT CLOUD (⭐ RECOMMENDED)")
    
    print("""
    STREAMLIT CLOUD - FREE, EASY, FAST
    
    Pros:
    ✅ Completely FREE (up to 3 concurrent apps)
    ✅ No credit card required
    ✅ Custom domain: yourname.streamlit.app
    ✅ Automatic updates from GitHub
    ✅ Built-in SSL/HTTPS
    
    Cons:
    ⚠️  Requires GitHub account
    
    STEPS:
    """)
    
    print("""
    1️⃣  CREATE GITHUB ACCOUNT (if you don't have one)
        → https://github.com/signup
    
    2️⃣  PUSH CODE TO GITHUB
        Copy and run these commands:
        
        cd /Users/andreacianfruglia/Desktop/fatigue_tool\ 2
        git init
        git add .
        git commit -m "EASA Fatigue Analysis Tool - Production Ready"
        git remote add origin https://github.com/YOUR_USERNAME/fatigue-tool.git
        git branch -M main
        git push -u origin main
    
    3️⃣  DEPLOY ON STREAMLIT CLOUD
        → https://streamlit.io/cloud
        → Click "New app"
        → Connect to your GitHub repo
        → Select: fatigue_app.py
        → Click "Deploy"
    
    4️⃣  SHARE YOUR APP
        Your live URL: https://YOUR_USERNAME-fatigue-tool.streamlit.app
    
    ⏱️  Time needed: ~5 minutes
    💰 Cost: FREE
    """)
    
    input("\nPress Enter when ready to continue...")

def option_2_heroku():
    """Deploy to Heroku"""
    print_section("OPTION 2: HEROKU")
    
    print("""
    HEROKU - EASY ALTERNATIVE
    
    Pros:
    ✅ Simple deployment
    ✅ Custom domain available
    ✅ Automatic SSL/HTTPS
    
    Cons:
    ⚠️  Free tier sleeps after 30 min inactivity
    💰 $5-7/month for production
    
    STEPS:
    
    1️⃣  CREATE HEROKU ACCOUNT
        → https://www.heroku.com
    
    2️⃣  INSTALL HEROKU CLI
        → https://devcenter.heroku.com/articles/heroku-cli
        
        On macOS:
        brew tap heroku/brew && brew install heroku
    
    3️⃣  DEPLOY
        heroku login
        heroku create your-app-name
        git push heroku main
    
    ⏱️  Time needed: ~10 minutes
    💰 Cost: Free tier or $7/month
    """)
    
    input("\nPress Enter when ready to continue...")

def option_3_local_server():
    """Run locally"""
    print_section("OPTION 3: RUN LOCALLY (for testing)")
    
    print("""
    LOCAL DEVELOPMENT SERVER
    
    Perfect for:
    ✅ Testing before deployment
    ✅ Local use only
    ✅ Custom modifications
    
    COMMAND:
    """)
    
    cmd = "streamlit run fatigue_app.py"
    print(f"    {cmd}\n")
    print("Then visit: http://localhost:8501\n")
    
    start = input("Start local server now? (y/n): ").lower()
    if start == 'y':
        os.chdir(str(Path(__file__).parent))
        os.system(cmd)

def main():
    print_header("🚀 EASA FATIGUE TOOL - DEPLOY YOUR WEB APP")
    
    print("""
    Your fatigue analysis tool is READY TO DEPLOY!
    
    You have a fully functional Streamlit web app that allows:
    
    📊 FEATURES:
       • Upload rosters (PDF/CSV)
       • Analyze fatigue risk for entire month
       • Interactive duty-by-duty breakdown
       • Download PDF reports
       • Compare different model configurations
       • Real-time risk assessment
    
    🎯 CHOOSE YOUR DEPLOYMENT:
    """)
    
    print("""
    ┌──────────────────────────────────────────────────────────────────┐
    │  1) STREAMLIT CLOUD ⭐ (RECOMMENDED)                             │
    │     → Free, easy, 5 minutes                                       │
    │     → URL: yourname.streamlit.app                                 │
    │                                                                    │
    │  2) HEROKU                                                       │
    │     → Free tier available, alternative option                     │
    │     → More flexibility                                            │
    │                                                                    │
    │  3) RUN LOCALLY                                                  │
    │     → Test on your machine first                                  │
    │     → Debug and modify code                                       │
    │                                                                    │
    │  4) QUIT                                                         │
    └──────────────────────────────────────────────────────────────────┘
    """)
    
    choice = input("Select option (1-4): ").strip()
    
    if choice == "1":
        option_1_streamlit_cloud()
    elif choice == "2":
        option_2_heroku()
    elif choice == "3":
        option_3_local_server()
    elif choice == "4":
        print("\n✅ Setup complete! Run this script again when ready to deploy.\n")
        sys.exit(0)
    else:
        print("\n❌ Invalid choice\n")
        return
    
    # Final summary
    print_section("📋 NEXT STEPS")
    print("""
    ✅ Your app is deployment-ready!
    
    AFTER DEPLOYMENT:
    
    1️⃣  Test the web app
        • Upload a test roster
        • Analyze a duty
        • Download a report
    
    2️⃣  Share with colleagues
        • Send them the link
        • Get feedback
    
    3️⃣  Use for SMS evidence
        • Collect performance predictions
        • Document fatigue mitigation
        • File proactive reports
    
    📚 FOR MORE INFO:
       • See DEPLOYMENT.md for detailed steps
       • See README.md for usage guide
       • See PROJECT_OVERVIEW.md for system overview
    
    🆘 TROUBLESHOOTING:
       If deployment fails, check:
       • requirements.txt is complete
       • Python version is 3.8+
       • All imports work: python -m pytest
    """)
    
    print("\n" + "="*70)
    print("  🎉 Good luck! Your app will be live shortly!")
    print("="*70 + "\n")

if __name__ == "__main__":
    main()
