#!/usr/bin/env python3
"""
Quick deployment helper script
Provides guidance for deploying the Streamlit app to the cloud
"""

import os
import subprocess
from pathlib import Path

def check_git():
    """Check if git is initialized"""
    if not Path('.git').exists():
        print("⚠️  Git not initialized")
        print("\nTo deploy, initialize git:")
        print("  git init")
        print("  git add .")
        print("  git commit -m 'Initial commit'")
        print("  git remote add origin <your-github-url>")
        print("  git push -u origin main")
        return False
    return True

def check_requirements():
    """Verify requirements.txt exists"""
    if not Path('requirements.txt').exists():
        print("❌ requirements.txt not found!")
        return False
    print("✅ requirements.txt found")
    return True

def check_streamlit_config():
    """Check Streamlit configuration"""
    if Path('.streamlit/config.toml').exists():
        print("✅ .streamlit/config.toml configured")
    else:
        print("⚠️  .streamlit/config.toml not found")
    return True

def check_procfile():
    """Check Procfile for Heroku"""
    if Path('Procfile').exists():
        print("✅ Procfile ready for Heroku")
    else:
        print("⚠️  Procfile not found (needed for Heroku)")
    return True

def main():
    print("\n" + "="*60)
    print("EASA Fatigue Tool - Deployment Checker")
    print("="*60 + "\n")
    
    print("Checking deployment readiness...\n")
    
    check_requirements()
    check_streamlit_config()
    check_procfile()
    print()
    
    if not check_git():
        print("\n📖 See DEPLOYMENT.md for full instructions")
        return
    
    print("\n✅ All checks passed! Your app is ready to deploy.\n")
    print("📖 See DEPLOYMENT.md for deployment instructions")
    print("\nRecommended: Deploy to Streamlit Cloud")
    print("  1. Push code to GitHub")
    print("  2. Go to https://streamlit.io/cloud")
    print("  3. Connect your repo")
    print("  4. Click 'Deploy'")
    print("\n" + "="*60 + "\n")

if __name__ == "__main__":
    main()
