"""Publish today's Pool story (and feed post on Mon/Wed/Fri) through the official Instagram API.

No password is used. It needs an Instagram API access token (from your Meta developer app).

Environment variables:
  IG_TOKEN        Instagram long-lived access token  (required)
  MEDIA_BASE_URL  public web address where the out/ files are hosted, e.g. https://you.github.io/pool-social/  (required)
  IG_USER_ID      Instagram user id (optional: looked up automatically)
  POST_DATE       YYYY-MM-DD (optional: defaults to today in India time)
  DRY_RUN=1       check everything but don't publish
Only uses the Python standard library.
"""
import datetime as dt, json, os, sys, time, urllib.error, urllib.parse, urllib.request

HOST = os.environ.get("IG_HOST", "https://graph.instagram.com")
VER = os.environ.get("IG_API_VERSION", "v23.0")
TOKEN = os.environ.get("IG_TOKEN", "").strip()
BASE = os.environ.get("MEDIA_BASE_URL", "").rstrip("/") + "/"
DRY = os.environ.get("DRY_RUN") == "1"
HERE = os.path.dirname(os.path.abspath(__file__))


def api(method, path, **params):
    params["access_token"] = TOKEN
    url = f"{HOST}/{VER}/{path}"
    data = None
    if method == "GET": url += "?" + urllib.parse.urlencode(params)
    else: data = urllib.parse.urlencode(params).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=data, method=method), timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        sys.exit(f"Instagram API error on {path}: {e.code} {body}")


def wait_public(url, tries=20):
    """GitHub Pages can take a minute to go live; Instagram must be able to download the file."""
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=30) as r:
                if r.status == 200: return
        except Exception: pass
        time.sleep(15)
    sys.exit(f"Media isn't reachable at {url}")


def publish(ig_id, label, **container):
    c = api("POST", f"{ig_id}/media", **container)["id"]
    for _ in range(60):  # videos take a little while to process
        st = api("GET", c, fields="status_code,status").get("status_code")
        if st == "FINISHED": break
        if st in ("ERROR", "EXPIRED"):
            sys.exit(f"{label}: Instagram couldn't process the media ({st}).")
        time.sleep(10)
    else:
        sys.exit(f"{label}: timed out waiting for Instagram to process the media.")
    media = api("POST", f"{ig_id}/media_publish", creation_id=c)
    print(f"{label}: published (media id {media['id']})")


def main():
    if not TOKEN or BASE == "/": sys.exit("Set IG_TOKEN and MEDIA_BASE_URL.")
    ist = dt.timezone(dt.timedelta(hours=5, minutes=30))
    day = os.environ.get("POST_DATE") or dt.datetime.now(ist).date().isoformat()
    ig_id = os.environ.get("IG_USER_ID") or api("GET", "me", fields="user_id,username")["user_id"]

    story = f"story-{day}.mp4"
    post, cap = f"post-{day}.jpg", os.path.join(HERE, "out", f"caption-{day}.txt")
    jobs = [("Story", dict(media_type="STORIES", video_url=BASE + story))]
    if os.path.exists(os.path.join(HERE, "out", post)):
        jobs.append(("Feed post", dict(image_url=BASE + post, caption=open(cap, encoding="utf-8").read())))

    for label, params in jobs:
        url = params.get("video_url") or params.get("image_url")
        wait_public(url)
        if DRY: print(f"{label}: ready at {url} (dry run, not published)"); continue
        publish(ig_id, label, **params)


if __name__ == "__main__":
    main()
