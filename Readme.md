# Keploy Sitemap Generator - Setup Guide

## Overview
This solution automatically crawls keploy.io, generates an up-to-date sitemap, tracks changes, and maintains version history—all for free using GitHub Actions.

## 📋 Features
- Handles Next.js rendered content
- Asynchronous crawling (fast, 10 concurrent requests)
- Generates valid XML sitemaps
- Tracks URL changes between runs (new, removed, updated)
- Maintains historical records
- Automatic scheduling (runs weekly)
- Manual trigger capability

## 🚀 Setup Instructions

### Step 1: Create Repository Structure
Create a new GitHub repo (or add to existing one) with:
```
your-repo/
├── .github/
│   └── workflows/
│       └── sitemap.yml          # (GitHub Actions workflow)
├── sitemap_generator.py         # (Main Python script)
├── sitemaps/                    # (Output directory - created automatically)
└── README.md
```

### Step 2: Add Files to GitHub

1. **Create `.github/workflows/sitemap.yml`**
   - Copy the GitHub Actions workflow code into this file

2. **Create `sitemap_generator.py`**
   - Copy the Python script into this file at the repo root

3. **Commit and push to main branch**

### Step 3: Enable GitHub Actions
- Go to your GitHub repo → Settings → Actions → General
- Under "Actions permissions", select "Allow all actions and reusable workflows"
- Save

### Step 4: First Run
- Go to "Actions" tab in your repo
- Click "Generate Sitemap" workflow
- Click "Run workflow" → "Run workflow"
- Wait 5-10 minutes for completion

### Step 5: Verify Output
- Check the "sitemaps/" folder in your repo
- You should see:
  - `sitemap.xml` - Current XML sitemap
  - `sitemap_YYYYMMDD_HHMMSS.json` - JSON version with metadata
  - `changes_YYYYMMDD_HHMMSS.json` - What changed since last run

## 📅 Scheduling
The workflow runs automatically every **Sunday at 2 AM UTC**. To change:
1. Edit `.github/workflows/sitemap.yml`
2. Modify the cron line: `- cron: '0 2 * * 0'`
   - Format: `minute hour day month day-of-week`
   - Examples:
     - `0 0 * * 0` = Every Sunday at midnight
     - `0 12 * * 1` = Every Monday at noon
     - `0 2 1 * *` = 1st of each month at 2 AM

## 🔄 Manual Triggers
- Go to Actions → Generate Sitemap
- Click "Run workflow"
- It executes immediately

## 📊 Interpreting Output

### sitemap.xml
Standard XML sitemap format, ready to:
- Upload to `public/sitemap.xml` on your website
- Submit to Google Search Console
- Use in robots.txt

### sitemap_YYYYMMDD_HHMMSS.json
Contains:
- `generated_at` - Timestamp
- `total_urls` - Total count
- `urls` - Each URL with lastmod and priority

### changes_YYYYMMDD_HHMMSS.json
Shows differences from previous run:
```json
{
  "new_urls": ["https://keploy.io/new-page"],
  "removed_urls": ["https://keploy.io/old-page"],
  "updated_urls": ["https://keploy.io/blog/post"],
  "url_count_change": 5
}
```

## 🎯 Next Steps

### Option A: Deploy Sitemap to Your Website
Create another workflow to:
1. Generate sitemap (already done)
2. Commit to repo
3. Deploy to your website's public folder

### Option B: Send Notifications
Add Slack/Discord notifications when URLs change significantly:
```yaml
- name: Notify on changes
  if: steps.changes.outputs.new_urls > 10
  uses: slackapi/slack-github-action@v1
```

### Option C: Submit to Search Engines
Add a step to automatically ping Google/Bing when sitemap updates

## 🛠️ Customization

### Change crawl speed
In `sitemap_generator.py`, modify:
```python
await generator.crawl(max_concurrent=10)  # Default: 10, max: 20
```

### Exclude URL patterns
Add to excluded_patterns list:
```python
self.excluded_patterns = ['.pdf', '.jpg', '/admin', '/private']
```

### Adjust priorities
Modify the `get_priority()` method to score different content types

### Change timing
Modify cron expression in `sitemap.yml`

## ⚠️ Troubleshooting

**"Action failed to run"**
- Check Python version support
- Ensure dependencies installed: `pip install aiohttp beautifulsoup4 lxml`

**"Workflow not triggering"**
- Verify `.github/workflows/sitemap.yml` path is correct
- Check GitHub Actions are enabled in repo settings

**"No URLs found"**
- Check if keploy.io is blocking automated requests
- Add User-Agent header if needed
- Verify network connectivity

**"Timeout errors"**
- Reduce `max_concurrent` value
- Increase timeout in `aiohttp.ClientTimeout`

## 📈 Monitoring

Track sitemap growth over time by:
1. Checking `changes_*.json` files periodically
2. Reviewing `total_urls` metric
3. Monitoring which pages are new/removed

## 💡 Pro Tips

1. **Pin sitemap version**: Create releases for important milestones
2. **Slack integration**: Set up notifications for significant URL changes
3. **Backup**: GitHub keeps 30 days of artifacts automatically
4. **Analytics**: Use `changes_*.json` to understand content growth
5. **Validation**: Use online validators to check XML syntax

## Need Help?
- Check GitHub Actions logs: Actions tab → Your run → Job details
- Review script output in "Generate sitemap" step
- Verify URLs are being crawled correctly

---

**That's it!** Your sitemap will now be auto-generated every week, completely free. 🎉