# Telus OTP Automation - GitHub Actions Setup

## Overview
This setup allows you to run the Telus OTP bot on GitHub Actions for FREE (using public repo unlimited minutes).

## Files Created

| File | Purpose |
|------|---------|
| `telus_gh.py` | Modified script for Linux/GitHub Actions |
| `requirements.txt` | Python dependencies |
| `.github/workflows/automation.yml` | Matrix workflow (20 parallel jobs) |
| `vercel-frontend/` | Web interface to trigger automation |

---

## Setup Steps

### 1. Create GitHub Repository (MUST BE PUBLIC)
```
- Go to github.com/new
- Create a NEW public repository
- Name: telus-otp-bot (or any name)
- Important: MUST be PUBLIC for free minutes
```

### 2. Upload Files to Repo
Upload these files to your repo:
- `telus_gh.py`
- `requirements.txt`
- `accounts.json` (your existing file)
- `.github/workflows/automation.yml`

### 3. Create GitHub PAT Token
```
- Go to: github.com/settings/tokens
- Generate new token (classic)
- Scopes needed: repo, workflow
- Copy the token (starts with ghp_)
```

### 4. Deploy Vercel Frontend (Optional - Alternative: Manual Trigger)
```
- Go to: vercel.com
- Import this repository
- Deploy the vercel-frontend folder
- Enter your PAT token and repo name
- Click "Start Automation"
```

### 5. Or Trigger Manually via GitHub
```
- Go to your repo on GitHub
- Click: Actions tab
- Select "Telus OTP Automation"
- Click: Run workflow
- Leave defaults (20 jobs, 15 accounts each)
- Click: Run workflow
```

---

## How It Works

### Matrix Strategy
- **20 parallel runners** (each runs on separate server)
- **15 accounts per job** (20 × 15 = 300 accounts)
- **~60 minutes per job** (within 6-hour limit)

### Environment Variables
Each job gets:
- `JOB_INDEX`: 1-20
- `ACCOUNT_OFFSET`: (job_index - 1) × 15
- `ACCOUNT_LIMIT`: 15

### Xvfb Virtual Display
- Runs Chrome in "headful" mode virtually
- Bypasses Sumsub anti-headless detection

---

## Important Notes

1. **accounts.json** must be in the repo root
2. Repo MUST be PUBLIC for unlimited free minutes
3. Each job runs independently with its own Chrome instance
4. otp_tracking.json tracks cooldown across jobs (saved as artifact)

---

## Troubleshooting

### "Permission denied" errors
- Make sure repo is PUBLIC
- Check PAT has `repo` and `workflow` scopes

### Sumsub blocking
- The Xvfb should handle it
- If still failing, may need stealth-chromedriver

### Jobs taking too long
- Current estimate: ~60 min per job
- If hitting 6-hour limit, reduce accounts_per_job

---

## Cost: $0/month
- GitHub Actions: FREE (public repo)
- Vercel: FREE (hobby tier)
- Total: $0