# Pool Instagram autopost

Every day at **6 pm India time** this posts a new 12-second **story video** to your Instagram.
On **Monday, Wednesday and Friday** it also posts a **feed picture** with a caption.
It runs free on GitHub's servers, so your laptop can be off.

**Your Instagram password is never used.** Posting goes through Instagram's official API with an access token that only allows posting and that you can cancel any time.

## What's in this folder

| File | What it does |
|---|---|
| `generate.py` | Makes the story video, feed picture and caption for a date |
| `post.py` | Publishes them to Instagram |
| `content.json` | **The text you can edit**: items and prices, student tips, hashtags |
| `assets/` | Fonts and the background music (Raja Vandhachu, original, so no copyright claims) |
| `.github/workflows/` | The daily schedule and the weekly token renewal |
| `out/` | A sample week (16–22 Nov 2026) so you can see what gets posted |

Stories rotate through 4 styles: **Buy vs Borrow**, **Student tip**, **Lend it**, **How Pool works**.

> **Check the prices in `content.json` before going live.** They're rough market prices, not prices from real Pool listings.

---

## One-time setup (about 30 minutes)

### 1. Put this folder on GitHub
1. Make a free account at github.com.
2. Click **New repository** → name it `pool-social` → choose **Public** (needed for free hosting of the media) → **Create**.
3. Click **uploading an existing file** and drag in **everything in this folder**, including the hidden `.github` folder.
   On a Mac, press **Cmd + Shift + .** in Finder to show hidden folders.
   You can leave out the `out` folder.

### 2. Turn on GitHub Pages (this hosts the videos so Instagram can fetch them)
Repository → **Settings → Pages → Source: GitHub Actions**.

### 3. Get your Instagram access token
1. Go to **developers.facebook.com** → log in with Facebook → **My Apps → Create app**.
2. Choose the use case **"Manage messaging & content on Instagram"**.
3. Open **Instagram → API setup with Instagram login**.
4. Under **Generate access tokens**, click **Add account** and log in to your Pool Instagram.
   Allow **instagram_business_basic** and **instagram_business_content_publish**.
5. Copy the token it shows. It lasts 60 days, and step 6 renews it automatically.

The app can stay in **Development mode**. It only needs to post to your own account.

### 4. Save the token in GitHub
Repository → **Settings → Secrets and variables → Actions → New repository secret**
- Name `IG_TOKEN`, value: the token from step 3.

### 5. Test it
Repository → **Actions → Daily Pool story → Run workflow**.
1. Tick **"Make the media but don't publish"** first. It should finish green.
2. Run it again without the tick. Today's story should appear on Instagram within a few minutes.

After that it runs by itself every day.

### 6. Automatic token renewal (recommended)
Without this, you'd have to repeat step 3 every 60 days.
1. GitHub → your profile picture → **Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token**.
2. Repository access: **only `pool-social`**. Permissions: **Secrets → Read and write**. Expiry: 1 year.
3. Save it as a repository secret named `GH_PAT`.

---

## Good to know

- **Stories on a Creator account:** Meta has allowed story posting through the API for Business accounts. If the first run fails with an error mentioning stories or media type, switch the Instagram to a **Business** account (Instagram → Settings → Account type and tools). It's free, and you keep your followers.
- **Change the posting time:** edit the `cron` line in `.github/workflows/daily.yml`. Times are in UTC: `30 12` is 6:00 pm India time, and `30 3` is 9:00 am.
- **Pause it:** Actions → Daily Pool story → **⋯ → Disable workflow**.
- **Preview on your computer** (needs Python, Pillow and ffmpeg): `python generate.py --week` makes the next 7 days in `out/`.
- **Without GitHub:** run `python generate.py --week` once a week and schedule the files yourself in **Meta Business Suite → Planner**. It's free and supports stories and posts.
- **Stop the access:** Instagram → Settings → **Apps and websites** → remove the app.
