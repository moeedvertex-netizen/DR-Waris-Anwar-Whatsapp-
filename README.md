# Dr. Waris Anwar Aesthetics — WhatsApp AI Agent

AI-powered WhatsApp receptionist that handles patient queries, provides clinic info, and books appointments with Google Calendar integration.

---

## DEPLOYMENT GUIDE (Railway.app — 10 Minutes)

### Step 1: Supabase Setup (2 min)

1. Go to **supabase.com** → Create free account → Create new project
2. Go to **SQL Editor** → Paste everything from `supabase_setup.sql` → Click **Run**
3. Go to **Settings > API** → Copy:
   - **Project URL** (e.g. `https://abc123.supabase.co`)
   - **service_role key** (under "Project API keys" — the secret one, NOT anon)

### Step 2: Railway Deploy (3 min)

1. Go to **railway.app** → Sign up with GitHub
2. Click **"New Project"** → **"Deploy from GitHub Repo"**
3. If code is not on GitHub yet:
   - Click **"Empty project"** → **"Add a service"** → **"GitHub Repo"**
   - OR use CLI: push this folder to a GitHub repo first
4. Railway will auto-detect Python and build

### Step 3: Environment Variables in Railway (2 min)

Go to your Railway service → **Variables** tab → Add these:

| Variable | Value |
|----------|-------|
| `WHATSAPP_TOKEN` | Your permanent token from Meta |
| `PHONE_NUMBER_ID` | Your registered phone number ID |
| `VERIFY_TOKEN` | `drwaris_verify_token_2026` |
| `GEMINI_API_KEY` | Your Google Gemini API key |
| `SUPABASE_URL` | `https://your-project.supabase.co` |
| `SUPABASE_KEY` | Supabase service_role key |
| `GOOGLE_CALENDAR_ID` | Client Gmail (e.g. `drwarisanwar@gmail.com`) |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | Full JSON of service account key |

### Step 4: Get Railway URL (1 min)

After deploy, Railway gives you a URL like:
`https://whatsapp-ai-agent-production.up.railway.app`

### Step 5: Meta Webhook Setup (2 min)

1. Go to **Meta Developer Console** → Your app → **Step 2. Production setup**
2. In **Configure Webhooks**:
   - **Callback URL**: `https://YOUR-RAILWAY-URL/webhook`
   - **Verify token**: `drwaris_verify_token_2026`
   - Click **Verify and save**
3. Subscribe to **messages** webhook field

### Step 6: TEST IT!

Send a WhatsApp message to the registered business number → AI will reply!

---

## Google Calendar Setup (Optional but Recommended)

1. Go to **console.cloud.google.com**
2. Create project → Enable **Google Calendar API**
3. Go to **IAM & Admin > Service Accounts** → Create service account
4. Click on service account → **Keys** → **Add Key** → **JSON** → Download
5. Open client's Google Calendar → **Settings** → **Share with specific people**
6. Add service account email (from JSON) → Permission: **Make changes to events**
7. Paste full JSON content in Railway env var `GOOGLE_SERVICE_ACCOUNT_JSON`
8. Set `GOOGLE_CALENDAR_ID` to client's Gmail

---

## Files

| File | Purpose |
|------|---------|
| `app.py` | Main application — webhook handler, AI, calendar |
| `requirements.txt` | Python dependencies |
| `Procfile` | Railway/Heroku deployment config |
| `supabase_setup.sql` | Database tables setup |
| `.env.example` | Environment variables template |

---

## How It Works

1. Patient sends WhatsApp message → Meta webhook → Railway server
2. Server gets AI response from Gemini with clinic context
3. AI replies naturally as receptionist
4. If appointment is booked → auto-creates Google Calendar event
5. All conversations + appointments saved to Supabase
6. Dashboard (Lovable) reads from Supabase in real-time

---

## Costs

| Service | Cost |
|---------|------|
| Railway | $5/month (Starter plan) |
| Supabase | Free tier (sufficient) |
| WhatsApp API | First 1000 conversations/month free |
| Gemini API | Free tier (15 RPM) |
| Google Calendar | Free |
| **Total** | **~$5/month** |
