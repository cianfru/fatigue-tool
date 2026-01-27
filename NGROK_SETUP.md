# Quick Setup: Expose Backend with ngrok

Your Lovable frontend runs in the cloud, so it can't reach localhost:8000. 
You need to expose your backend publicly using ngrok (free).

## Step 1: Sign up for ngrok (Free, 2 minutes)

1. Go to: https://dashboard.ngrok.com/signup
2. Sign up with Google/GitHub (fastest)
3. You'll see your authtoken on the dashboard

## Step 2: Configure ngrok

Copy your authtoken and run:

```bash
ngrok config add-authtoken YOUR_AUTHTOKEN_HERE
```

## Step 3: Start the tunnel

```bash
ngrok http 8000
```

You'll see output like:
```
Forwarding   https://abc123.ngrok.io -> http://localhost:8000
```

## Step 4: Copy the public URL

Copy the URL (e.g., `https://abc123.ngrok.io`)

## Step 5: Update your Lovable frontend

In Lovable, go to your project settings and set:

**Environment Variable:**
```
VITE_API_URL=https://abc123.ngrok.io
```

Or directly in `src/lib/api-client.ts`, change:
```typescript
const API_BASE_URL = 'https://abc123.ngrok.io';
```

## Step 6: Test it!

1. Open your Lovable preview
2. Upload a roster file
3. Click "Run Analysis"
4. Watch it work! 🎉

---

## Alternative: Deploy Backend to Cloud (No ngrok needed)

If you prefer not to use ngrok, you can deploy your backend to:

### Option A: Railway (Easiest)
1. Go to https://railway.app
2. Connect your GitHub repo (fatigue-tool)
3. Railway will auto-detect Python and deploy
4. Copy the deployment URL
5. Use that URL in VITE_API_URL

### Option B: Render
1. Go to https://render.com
2. New Web Service → Connect fatigue-tool repo
3. Use these settings:
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `uvicorn api_server:app --host 0.0.0.0 --port 8000`
4. Copy the deployment URL

---

## Current Status

✅ Backend running locally at http://localhost:8000
✅ Backend is healthy and working
❌ Not publicly accessible (Lovable can't reach it)

Once you complete ngrok setup or cloud deployment, your frontend will connect! 🚀
